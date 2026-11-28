"""Bounded UE4.27 layer-function subset, independent of legacy property objects.

Uses the existing typed package/property readers and documented expression-input
layout (MIT UAssetAPI reference, see third_party/UAssetAPI-LICENSE.txt).
Only bundle inputs, make/blend attributes, scalar constants/parameters and a
bundle output are supported. No runtime shader or arbitrary function claim.
"""
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID
import json
from classic_material import require, unsupported, property_map, name, scalar, integer
from classic_material_graph import edge, guid
from package_records import read_package, ExportRecord
from skeleton_native import Reader
from material_attributes import FIELDS, interface_bundle, by_id


@dataclass(frozen=True)
class Expression:
    index: int
    kind: str
    label: str
    inputs: tuple
    value: float = 0.
    identity: str = ''
    priority: int = 0
    parameter: str = ''


@dataclass(frozen=True)
class Function:
    name: str
    usage: str
    expressions: tuple


USAGES = {'MaterialFunctionMaterialLayer': 'MaterialLayer',
          'MaterialFunctionMaterialLayerBlend': 'MaterialLayerBlend'}
COMMON = {'Material', 'Function', 'MaterialExpressionEditorX', 'MaterialExpressionEditorY',
          'MaterialExpressionGuid', 'ExpressionGUID', 'Desc', 'Group', 'SortPriority'}


def decode_expression(index, kind, label, p, names):
    allowed = set(); value = 0.; identity = parameter = ''; priority = 0
    if kind == 'FunctionInput':
        allowed = {'Id', 'InputName', 'InputType', 'SortPriority'}
        unsupported(name(p, 'InputType', names, '') == 'FunctionInput_MaterialAttributes', 'Non-bundle layer input')
        identity = str(UUID(bytes_le=bytes.fromhex(guid(p['Id'])))); label = name(p, 'InputName', names, '')
        priority = integer(p, 'SortPriority')
    elif kind == 'FunctionOutput':
        allowed = {'Id', 'OutputName', 'A', 'bLastPreviewed'}
        identity = str(UUID(bytes_le=bytes.fromhex(guid(p['Id'])))); label = name(p, 'OutputName', names, '')
    elif kind == 'MakeMaterialAttributes':
        allowed = set(FIELDS)
    elif kind == 'BlendMaterialAttributes':
        allowed = {'A', 'B', 'Alpha', 'PixelAttributeBlendType'}
        unsupported(name(p, 'PixelAttributeBlendType', names, 'Blend').split('::')[-1] == 'Blend', 'Unsupported attribute blend mode')
    elif kind in ('Constant', 'ScalarParameter'):
        allowed = {'R'} if kind == 'Constant' else {'DefaultValue', 'ParameterName'}
        value = scalar(p, 'R' if kind == 'Constant' else 'DefaultValue')
        if kind == 'ScalarParameter':
            parameter = name(p, 'ParameterName', names, ''); require(bool(parameter), 'Missing scalar parameter name')
    else:
        raise NotImplementedError('Unsupported layer expression: '+kind)
    unsupported(set(p) <= COMMON | allowed, 'Unsupported layer expression fields: '+', '.join(sorted(set(p)-COMMON-allowed)))
    if kind in ('FunctionInput', 'FunctionOutput'):
        require(bool(label) and UUID(identity).int != 0, 'Invalid function interface')
    links = []
    for key in allowed & set(p):
        record = p[key]
        if key not in (set(FIELDS) if kind == 'MakeMaterialAttributes' else {'A','B','Alpha'} if kind == 'BlendMaterialAttributes' else {'A'} if kind == 'FunctionOutput' else set()):
            continue
        require(record.kind == 'StructProperty' and record.parameters == ('ExpressionInput',), 'Invalid layer edge '+key)
        e = edge(record.data, names)
        unsupported(e['output'] in (0,-1) and not any(e['mask']), 'Masked or indexed layer edge unsupported')
        if e['index']: links.append((key, e['index']))
    return Expression(index, kind, label, tuple(sorted(links)), value, identity, priority, parameter)


def read_function(path):
    meta, raw, table = read_package(path)
    unsupported(meta.get('ue4') == 522 and meta.get('ue5') is None and meta.get('licensee') == 0, 'Unsupported layer function profile')
    roots = [(i,e) for i,e in enumerate(table.exports,1) if not e.outer and e.kind in USAGES]
    unsupported(len(roots) == 1, 'Expected one layer or blend function')
    root, entry = roots[0]; p = property_map(raw, entry, table.names)
    allowed = {'FunctionExpressions','bExposeToLibrary','FunctionEditorComments','DependentFunctionExpressionCandidates','StateId','CombinedOutputTypes','ThumbnailInfo','MaterialFunctionUsage','Description','LibraryCategories'}
    unsupported(set(p) <= allowed, 'Unsupported layer function root fields')
    record = p.get('FunctionExpressions')
    require(record is not None and record.kind == 'ArrayProperty' and record.parameters == ('ObjectProperty',), 'Missing layer expression array')
    r = Reader(record.data); indices = [r.i() for _ in range(r.count(4096))]
    require(r.pos == len(r.data) and len(set(indices)) == len(indices), 'Invalid layer expression array')
    expressions = []
    for i in indices:
        e = table.reference(i)
        require(isinstance(e, ExportRecord) and e.outer == root and e.kind.startswith('MaterialExpression'), 'Invalid layer expression ownership')
        kind = e.kind.removeprefix('MaterialExpression')
        if kind == 'Comment': continue
        expressions.append(decode_expression(i,kind,e.name,property_map(raw,e,table.names),table.names))
    fn = Function(entry.name, USAGES[entry.kind], tuple(expressions)); validate(fn); return fn


def validate(fn):
    require(fn.usage in USAGES.values(), 'Invalid function usage')
    nodes = {n.index:n for n in fn.expressions}
    require(len(nodes)==len(fn.expressions) and all(i>0 for i in nodes), 'Duplicate expression identity')
    inputs = [n for n in nodes.values() if n.kind=='FunctionInput']; outputs = [n for n in nodes.values() if n.kind=='FunctionOutput']
    require(len(outputs)==1 and (len(inputs)<=1 if fn.usage=='MaterialLayer' else len(inputs)==2), 'Invalid bundle function arity')
    require(len({n.identity for n in inputs+outputs})==len(inputs)+1 and len({n.priority for n in inputs})==len(inputs), 'Ambiguous function interface')
    bundles = {'FunctionInput','MakeMaterialAttributes','BlendMaterialAttributes'}; scalars = {'Constant','ScalarParameter'}
    for n in nodes.values():
        links = dict(n.inputs); require(len(links)==len(n.inputs), 'Duplicate edge')
        require(n.kind in bundles|scalars|{'FunctionOutput'}, 'Unsupported expression')
        if n.kind=='FunctionOutput': require(set(links)=={'A'}, 'Missing bundle output')
        elif n.kind=='BlendMaterialAttributes': require({'A','B'}<=set(links)<= {'A','B','Alpha'}, 'Invalid blend inputs')
        elif n.kind=='MakeMaterialAttributes': require(set(links)<=set(FIELDS), 'Invalid attribute input')
        else: require(not links, 'Unexpected inputs')
        for key,source in links.items():
            expect = bundles if n.kind=='FunctionOutput' or n.kind=='BlendMaterialAttributes' and key in ('A','B') else scalars
            require(source in nodes and nodes[source].kind in expect, 'Invalid layer edge type or identity')
            if n.kind=='MakeMaterialAttributes': unsupported(not isinstance(FIELDS[key],tuple), 'Scalar-to-vector attribute unsupported')
    visiting=set(); done=set()
    def visit(i):
        require(i not in visiting, 'Layer expression cycle')
        if i in done:return
        require(len(visiting)<128, 'Layer expression depth limit')
        visiting.add(i)
        for _,j in nodes[i].inputs:visit(j)
        visiting.remove(i);done.add(i)
    for i in nodes:visit(i)
    return nodes, sorted(inputs,key=lambda n:n.priority), outputs[0]


def compile_function(fn):
    """Build editable nodes with stable logical socket IDs; rollback on failure."""
    nodes,inputs,output=validate(fn)
    import bpy
    group=bpy.data.node_groups.new(fn.name,'ShaderNodeTree')
    try:
        input_ids={n.identity:interface_bundle(group,n.label,'INPUT') for n in inputs}
        output_ids={output.identity:interface_bundle(group,output.label,'OUTPUT')}
        inp=group.nodes.new('NodeGroupInput');out=group.nodes.new('NodeGroupOutput')
        registry={}; compiled={}
        for n in inputs:compiled[n.index]={k:by_id(inp.outputs,v) for k,v in input_ids[n.identity].items()}
        def emit(i):
            if i in compiled:return compiled[i]
            n=nodes[i]; links={k:emit(j) for k,j in n.inputs}
            if n.kind in ('Constant','ScalarParameter'):
                v=group.nodes.new('ShaderNodeValue');v.label=n.parameter or n.label;v.outputs[0].default_value=n.value;result=v.outputs[0]
                if n.parameter:registry.setdefault(n.parameter,[]).append(SimpleNamespace(classname='MaterialExpressionScalarParameter',node=v))
            elif n.kind=='MakeMaterialAttributes':
                result={}
                for k,default in FIELDS.items():
                    if k in links:result[k]=links[k];continue
                    v=group.nodes.new('ShaderNodeCombineXYZ' if isinstance(default,tuple) else 'ShaderNodeValue');v.label=k
                    if isinstance(default,tuple):
                        for socket,value in zip(v.inputs,default):socket.default_value=value
                    else:v.outputs[0].default_value=default
                    result[k]=v.outputs[0]
            elif n.kind=='BlendMaterialAttributes':
                result={}
                for k,default in FIELDS.items():
                    v=group.nodes.new('ShaderNodeMix');vec=isinstance(default,tuple);v.data_type='VECTOR' if vec else 'FLOAT';v.clamp_factor=False;v.clamp_result=False
                    if 'Alpha' in links:group.links.new(links['Alpha'],v.inputs[0])
                    else:v.inputs[0].default_value=0.
                    group.links.new(links['A'][k],v.inputs[4 if vec else 2]);group.links.new(links['B'][k],v.inputs[5 if vec else 3]);result[k]=v.outputs[1 if vec else 0]
            else:raise ValueError('Unexpected compiled expression')
            compiled[i]=result;return result
        result=emit(dict(output.inputs)['A'])
        for k,v in output_ids[output.identity].items():group.links.new(result[k],by_id(out.inputs,v))
        group['UE_function_usage']=fn.usage;group['UE_input_ids']=json.dumps(input_ids);group['UE_output_ids']=json.dumps(output_ids);group['UE_input_order']=json.dumps(list(input_ids));group['UE_typed_layer_function']=True
        return group,SimpleNamespace(param_nodes=registry)
    except Exception:
        bpy.data.node_groups.remove(group);raise


def load_function(path):
    return compile_function(read_function(path))
