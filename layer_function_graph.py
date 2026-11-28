"""Bounded UE4.27 layer-function subset, independent of legacy property objects.

Uses the existing typed package/property readers and documented expression-input
layout (MIT UAssetAPI reference, see third_party/UAssetAPI-LICENSE.txt).
Supports bundle inputs/outputs, make/blend attributes, typed scalar arithmetic,
RGB/vector constants and parameters, and default-UV color textures. No arbitrary function or runtime shader claim.
"""
from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID
import json
from classic_material import require, unsupported, property_map, name, scalar, integer, linear_color
from classic_material_graph import edge, guid, imported
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
    color: tuple = (0., 0., 0., 1.)
    defaults: tuple = ()
    texture: str = ''
    sampler: str = ''


@dataclass(frozen=True)
class Function:
    name: str
    usage: str
    expressions: tuple


USAGES = {'MaterialFunctionMaterialLayer': 'MaterialLayer',
          'MaterialFunctionMaterialLayerBlend': 'MaterialLayerBlend'}
SCALAR_OPS = {'Add': 'ADD', 'Subtract': 'SUBTRACT', 'Multiply': 'MULTIPLY',
              'LinearInterpolate': None, 'OneMinus': None}
TEXTURES = {'TextureSample', 'TextureSampleParameter2D'}
VECTORS = {'Constant3Vector', 'VectorParameter'} | TEXTURES

COMMON = {'Material', 'Function', 'MaterialExpressionEditorX', 'MaterialExpressionEditorY',
          'MaterialExpressionGuid', 'ExpressionGUID', 'Desc', 'Group', 'SortPriority'}


def decode_expression(index, kind, label, p, names, table=None):
    allowed = set(); value = 0.; identity = parameter = ''; priority = 0
    color = (0., 0., 0., 1.); defaults = (); edge_keys = set(); texture = sampler = ''
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
    elif kind in TEXTURES:
        allowed = {'Texture','SamplerType','SamplerSource','Coordinates'}
        if kind == 'TextureSampleParameter2D':
            allowed.add('ParameterName'); parameter = name(p,'ParameterName',names,''); require(bool(parameter), 'Missing texture parameter name')
        require(table is not None, 'Missing texture reference table')
        texture = imported(p,'Texture',table,('Texture2D',))
        sampler = name(p,'SamplerType',names,'SAMPLERTYPE_Color')
        unsupported(sampler in ('SAMPLERTYPE_Color','SAMPLERTYPE_LinearColor'), 'Unsupported layer texture sampler')
        unsupported(name(p,'SamplerSource',names,'SSM_FromTextureAsset')=='SSM_FromTextureAsset', 'Unsupported layer sampler source')
        if 'Coordinates' in p:
            record=p['Coordinates'];require(record.kind=='StructProperty' and record.parameters==('ExpressionInput',), 'Invalid texture coordinates')
            unsupported(not edge(record.data,names)['index'], 'Explicit layer texture coordinates unsupported')
    elif kind in VECTORS:
        key = 'DefaultValue' if kind == 'VectorParameter' else 'Constant'
        allowed = {key, 'ParameterName'} if kind == 'VectorParameter' else {key}
        color = linear_color(p, key)
        if kind == 'VectorParameter':
            parameter = name(p, 'ParameterName', names, ''); require(bool(parameter), 'Missing vector parameter name')
    elif kind in SCALAR_OPS:
        if kind == 'OneMinus':
            edge_keys = {'Input'}; allowed = edge_keys
        else:
            values = {'A':0., 'B':1., 'Alpha':.5} if kind == 'LinearInterpolate' else {k:1. if kind == 'Multiply' else 0. for k in ('A','B')}
            edge_keys = set(values); allowed = edge_keys | {'Const'+k for k in values}
            defaults = tuple((k, scalar(p,'Const'+k,v)) for k,v in values.items())
    else:
        raise NotImplementedError('Unsupported layer expression: '+kind)
    unsupported(set(p) <= COMMON | allowed, 'Unsupported layer expression fields: '+', '.join(sorted(set(p)-COMMON-allowed)))
    if kind in ('FunctionInput', 'FunctionOutput'):
        require(bool(label) and UUID(identity).int != 0, 'Invalid function interface')
    edge_keys |= set(FIELDS) if kind == 'MakeMaterialAttributes' else {'A','B','Alpha'} if kind == 'BlendMaterialAttributes' else {'A'} if kind == 'FunctionOutput' else set()
    links = []
    for key in allowed & set(p):
        record = p[key]
        if key not in edge_keys:
            continue
        require(record.kind == 'StructProperty' and record.parameters == ('ExpressionInput',), 'Invalid layer edge '+key)
        e = edge(record.data, names)
        unsupported(e['output'] in (0,-1) and not any(e['mask']), 'Masked or indexed layer edge unsupported')
        if e['index']: links.append((key, e['index']))
    if kind in SCALAR_OPS and kind!='OneMinus':
        unsupported(all(k in dict(links) or 'Const'+k in p for k,_ in defaults), 'Unserialized layer arithmetic default unsupported')
    return Expression(index, kind, label, tuple(sorted(links)), value, identity, priority, parameter, color, defaults, texture, sampler)


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
        expressions.append(decode_expression(i,kind,e.name,property_map(raw,e,table.names),table.names,table))
    fn = Function(entry.name, USAGES[entry.kind], tuple(expressions)); validate(fn); return fn


def validate(fn):
    require(fn.usage in USAGES.values(), 'Invalid function usage')
    nodes = {n.index:n for n in fn.expressions}
    require(len(nodes)==len(fn.expressions) and all(i>0 for i in nodes), 'Duplicate expression identity')
    inputs = [n for n in nodes.values() if n.kind=='FunctionInput']; outputs = [n for n in nodes.values() if n.kind=='FunctionOutput']
    require(len(outputs)==1 and (len(inputs)<=1 if fn.usage=='MaterialLayer' else len(inputs)==2), 'Invalid bundle function arity')
    require(len({n.identity for n in inputs+outputs})==len(inputs)+1 and len({n.priority for n in inputs})==len(inputs), 'Ambiguous function interface')
    bundles = {'FunctionInput','MakeMaterialAttributes','BlendMaterialAttributes'}; scalars = {'Constant','ScalarParameter'} | set(SCALAR_OPS)
    for n in nodes.values():
        links = dict(n.inputs); require(len(links)==len(n.inputs), 'Duplicate edge')
        require(n.kind in bundles|scalars|VECTORS|{'FunctionOutput'}, 'Unsupported expression')
        if n.kind=='FunctionOutput': require(set(links)=={'A'}, 'Missing bundle output')
        elif n.kind=='BlendMaterialAttributes': require({'A','B'}<=set(links)<= {'A','B','Alpha'}, 'Invalid blend inputs')
        elif n.kind=='MakeMaterialAttributes': require(set(links)<=set(FIELDS), 'Invalid attribute input')
        elif n.kind in SCALAR_OPS:
            expected = {'Input'} if n.kind == 'OneMinus' else {'A','B','Alpha'} if n.kind == 'LinearInterpolate' else {'A','B'}
            require(set(links)<=expected and (n.kind!='OneMinus' or set(links)==expected), 'Invalid math inputs')
            import math
            require(len(dict(n.defaults))==len(n.defaults) and set(dict(n.defaults))==(set() if n.kind=='OneMinus' else expected) and all(math.isfinite(v) for _,v in n.defaults), 'Invalid math defaults')
        else: require(not links, 'Unexpected inputs')
        if n.kind in TEXTURES: require(bool(n.texture) and n.sampler in ('SAMPLERTYPE_Color','SAMPLERTYPE_LinearColor'), 'Invalid layer texture record')
        for key,source in links.items():
            expect = bundles if n.kind=='FunctionOutput' or n.kind=='BlendMaterialAttributes' and key in ('A','B') else scalars
            if n.kind=='MakeMaterialAttributes' and isinstance(FIELDS[key],tuple): expect=VECTORS
            require(source in nodes, 'Invalid layer edge identity')
            src=nodes[source].kind
            if n.kind in SCALAR_OPS or n.kind=='MakeMaterialAttributes':
                if src not in bundles and (src not in expect or n.kind=='MakeMaterialAttributes' and key=='Normal' and src in TEXTURES):
                    raise NotImplementedError('Unsupported layer value conversion')
            require(src in expect, 'Invalid layer edge type')
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


def compile_function(fn, texture_loader=None):
    """Build editable nodes with stable logical socket IDs; rollback on failure."""
    nodes,inputs,output=validate(fn)
    import bpy
    from project_session import new_ids, rollback_new
    previous=set(new_ids())
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
            elif n.kind in TEXTURES:
                from uv_semantics import uv_source
                from shader_texture_binding import assign_image
                require(texture_loader is not None, 'No layer texture resolver')
                image=texture_loader(n.texture)
                require(image is not None and image.packed_file, 'Missing packed layer texture: '+n.texture)
                expected='sRGB' if n.sampler=='SAMPLERTYPE_Color' else 'Non-Color'
                unsupported(image.colorspace_settings.name==expected, 'Layer sampler color-space mismatch')
                v=group.nodes.new('ShaderNodeTexImage');v.label=n.parameter or n.label
                v['UE_texture_package']=n.texture;v['UE_sampler_source']='SSM_FromTextureAsset';v['UE_typed_layer_sampler']=expected
                group.links.new(uv_source(group),v.inputs['Vector']);assign_image(v,image)
                if n.parameter:registry.setdefault(n.parameter,[]).append(SimpleNamespace(classname='MaterialExpressionTextureSampleParameter2D',node=v))
                result=v.outputs['Color']
            elif n.kind in VECTORS:
                from generated_shader_groups import get
                v=group.nodes.new('ShaderNodeGroup');v.node_tree=get('RGBA' if n.kind=='VectorParameter' else 'Const3');v.label=n.parameter or n.label
                v.inputs['RGB'].default_value=n.color
                if n.kind=='VectorParameter':
                    v.inputs['A'].default_value=n.color[3]
                    registry.setdefault(n.parameter,[]).append(SimpleNamespace(classname='MaterialExpressionVectorParameter',node=v))
                result=v.outputs['RGB']
            elif n.kind in SCALAR_OPS:
                defaults=dict(n.defaults)
                def connect(key,socket):
                    if key in links:group.links.new(links[key],socket)
                    else:socket.default_value=defaults[key]
                if n.kind=='LinearInterpolate':
                    v=group.nodes.new('ShaderNodeMix');v.data_type='FLOAT';v.clamp_factor=False;v.clamp_result=False
                    for key,i in (('Alpha',0),('A',2),('B',3)):connect(key,v.inputs[i])
                    result=v.outputs[0]
                else:
                    v=group.nodes.new('ShaderNodeMath');v.use_clamp=False
                    if n.kind=='OneMinus':
                        v.operation='SUBTRACT';v.inputs[0].default_value=1.;connect('Input',v.inputs[1])
                    else:
                        v.operation=SCALAR_OPS[n.kind];connect('A',v.inputs[0]);connect('B',v.inputs[1])
                    result=v.outputs[0]
                v.label=n.label
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
        rollback_new(previous);raise


def load_function(path, project=None):
    fn=read_function(path)
    if not any(n.kind in TEXTURES for n in fn.expressions):return compile_function(fn)
    from project_paths import ProjectPaths
    from texture_blender import load_editor_texture
    project=project or ProjectPaths(path)
    return compile_function(fn,lambda package:load_editor_texture(project.resolve_package(package),project))
