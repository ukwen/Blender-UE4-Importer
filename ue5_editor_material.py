"""Tagged UE5 editor material graph, global instance overrides and bounded PBR subset.
No execution of custom HLSL, engine functions or particle/runtime expressions.
"""
import json, math, struct
from pathlib import Path
from skeleton_native import Reader
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags,read_tag_stream,read_tags


def read_material(path):
    from package_inspector import inspect_package
    if inspect_package(path).get('ue5')==1004:
        from ue5_legacy_editor import read_material as legacy_material
        return legacy_material(path)
    m,b,im,ex,ref,pkg=read_tables(path); names=m['names']
    roots=[(i,e) for i,e in enumerate(ex,1) if not e['outer'] and e['kind'] in ('Material','MaterialInstanceConstant','MaterialFunction')];require(len(roots)==1,'Expected one material root');i,e=roots[0]
    t=export_tags(b,e,names)
    def val(tags,k,typ,fmt,default=None):
        if k not in tags:return default
        x=tags[k];require(x['type']==typ and len(x['data'])==struct.calcsize('<'+fmt),'Invalid '+k);v=struct.unpack('<'+fmt,x['data']);require(all(math.isfinite(f) for f in v),'Non-finite '+k);return v[0] if len(v)==1 else list(v)
    def name(tags,k,default=''):
        if k not in tags:return default
        x=tags[k];require(x['type'][0] in ('NameProperty','ByteProperty') and len(x['data'])==8,'Invalid name '+k);return Reader(x['data']).name(names)
    def object_index(tags,k):return val(tags,k,['ObjectProperty'],'i',0)
    def imported(tags,k,classes):
        j=object_index(tags,k);require(j<0 and ref(j)['kind'] in classes and pkg(j),'Invalid '+k+' import');return pkg(j)
    def boolval(tags,k):
        x=tags.get(k);return bool(x and x['type']==['BoolProperty'] and x['flags']&16)
    if e['kind']=='MaterialInstanceConstant':
        out=dict(name=e['name'],kind='instance',parent=imported(t,'Parent',('Material','MaterialInstanceConstant')),parameters=[],unsupported=[])
        for k,kind,sub,typ,fmt in [('ScalarParameterValues','scalar','ScalarParameterValue',['FloatProperty'],'f'),('VectorParameterValues','vector','VectorParameterValue',['StructProperty','LinearColor','/Script/CoreUObject'],'4f'),('TextureParameterValues','texture','TextureParameterValue',['ObjectProperty'],'i')]:
            if k not in t:continue
            require(t[k]['type']==['ArrayProperty','StructProperty',sub,'/Script/Engine'],'Invalid parameter array');r=Reader(t[k]['data'])
            for _ in range(r.count(4096)):
                p=read_tag_stream(r,names);info=read_tags(p['ParameterInfo']['data'],names);nm=name(info,'Name');assoc=name(info,'Association');index=val(info,'Index',['IntProperty'],'i',-1);require(nm and assoc=='GlobalParameter' and index==-1,'Unsupported material parameter association')
                v=val(p,'ParameterValue',typ,fmt,0 if kind!='vector' else [0,0,0,0]);
                if kind=='texture':v=imported(p,'ParameterValue',('Texture2D',)) if v else None
                out['parameters'].append(dict(name=nm,kind=kind,value=v,guid=p['ExpressionGUID']['data'].hex() if 'ExpressionGUID' in p else ''))
            require(r.pos==len(r.data),'Unexpected parameter array tail')
        require(len({(p['name'],p['kind']) for p in out['parameters']})==len(out['parameters']),'Duplicate parameter override')
        if 'StaticParametersRuntime' in t:
            static=read_tags(t['StaticParametersRuntime']['data'],names)
            if set(static)-{'StaticSwitchParameters'}:out['unsupported'].append('Unsupported static parameter fields')
            if 'StaticSwitchParameters' in static:
                v=static['StaticSwitchParameters'];require(v['type']==['ArrayProperty','StructProperty','StaticSwitchParameter','/Script/Engine'],'Invalid static switch array');r=Reader(v['data'])
                for _ in range(r.count(4096)):
                    p=read_tag_stream(r,names);info=read_tags(p['ParameterInfo']['data'],names);nm=name(info,'Name');require(nm and name(info,'Association')=='GlobalParameter' and val(info,'Index',['IntProperty'],'i',-1)==-1,'Unsupported static association')
                    if boolval(p,'bOverride'):out['parameters'].append(dict(name=nm,kind='switch',value=boolval(p,'Value'),guid=p['ExpressionGUID']['data'].hex()))
                require(r.pos==len(r.data),'Unexpected static switch array tail')
        if 'BasePropertyOverrides' in t:
            overrides=read_tags(t['BasePropertyOverrides']['data'],names);out['base_overrides']={k:dict(type=v['type'],flags=v['flags'],data=v['data'].hex()) for k,v in overrides.items()}
            if any(k.startswith('bOverride') and boolval(overrides,k) for k in overrides):out['unsupported'].append('BasePropertyOverrides')
        require(len({(p['name'],p['kind']) for p in out['parameters']})==len(out['parameters']),'Duplicate parameter override')
        return out
    def edge(data):
        require(len(data)>=36,'Truncated expression input'); r=Reader(data); j,slot=r.unpack('2i');nm=r.name(names);mask=r.unpack('5i');require(0<=j<=len(ex) and (0<=slot<64 or (j==0 and slot==-1)) and all(v in (0,1) for v in mask),'Invalid expression reference');return dict(index=j,output=slot,mask=list(mask),input_name=nm)
    nodes={}
    for j,x in enumerate(ex,1):
        if x['outer']!=i or not x['kind'].startswith('MaterialExpression') or x['kind'].endswith('Comment'):continue
        p=export_tags(b,x,names);kind=x['kind'].removeprefix('MaterialExpression');node=dict(kind=kind,name=x['name'],parameter=name(p,'ParameterName'),guid=p.get('ExpressionGUID',{}).get('data',b'').hex(),position=[val(p,'MaterialExpressionEditorX',['IntProperty'],'i',0),val(p,'MaterialExpressionEditorY',['IntProperty'],'i',0)],inputs={k:edge(v['data']) for k,v in p.items() if v['type']==['StructProperty','ExpressionInput','/Script/Engine'] and len(v['data'])==36})
        if kind=='ScalarParameter':node['value']=val(p,'DefaultValue',['FloatProperty'],'f',0.)
        if kind=='VectorParameter':node['value']=val(p,'DefaultValue',['StructProperty','LinearColor','/Script/CoreUObject'],'4f',[0.,0.,0.,1.])
        if kind=='Constant':node['value']=val(p,'R',['FloatProperty'],'f',0.)
        if kind=='Constant3Vector':node['value']=val(p,'Constant',['StructProperty','LinearColor','/Script/CoreUObject'],'4f',[0.,0.,0.,1.])
        if kind=='MaterialFunctionCall':
            node['function']=imported(p,'MaterialFunction',('MaterialFunction','MaterialFunctionInstance'))
            for key,sub,idkey,result in [('FunctionInputs','FunctionExpressionInput','ExpressionInputId','function_inputs'),('FunctionOutputs','FunctionExpressionOutput','ExpressionOutputId','function_outputs')]:
                v=p.get(key);node[result]=[]
                if not v:continue
                require(v['type']==['ArrayProperty','StructProperty',sub,'/Script/Engine'],'Invalid function call array');r=Reader(v['data'])
                for _ in range(r.count(256)):
                    entry=read_tag_stream(r,names);g=entry[idkey];require(g['type']==['StructProperty','Guid','/Script/CoreUObject'] and len(g['data'])==16,'Invalid function interface GUID')
                    record={'guid':g['data'].hex()}
                    if key=='FunctionInputs':record['edge']=edge(entry['Input']['data'])
                    else:
                        output=entry['Output'];require(output['type']==['StructProperty','ExpressionOutput','/Script/Engine'],'Invalid function output descriptor');record['descriptor_hex']=output['data'].hex()
                    node[result].append(record)
                require(r.pos==len(r.data) and len({v['guid'] for v in node[result]})==len(node[result]),'Invalid function interface extent or duplicate GUID')
        if kind in ('FunctionInput','FunctionOutput'):
            g=p['Id'];require(g['type']==['StructProperty','Guid','/Script/CoreUObject'] and len(g['data'])==16,'Invalid function interface ID');node['interface_guid']=g['data'].hex();node['interface_name']=name(p,'InputName' if kind=='FunctionInput' else 'OutputName')
            if kind=='FunctionInput':node['input_type']=name(p,'InputType');node['preview_default']=boolval(p,'bUsePreviewValueAsDefault')
        if kind=='StaticBool':node['value']=boolval(p,'Value')
        if kind=='If':node['threshold']=val(p,'EqualsThreshold',['FloatProperty'],'f',.00001);node['defaults']={'B':val(p,'ConstB',['FloatProperty'],'f',0.)}
        if kind=='Transform':node['transform_source']=name(p,'TransformSourceType','TRANSFORMSOURCE_Tangent');node['transform_target']=name(p,'TransformType','TRANSFORM_World')
        if kind in ('TextureSample','TextureSampleParameter2D'):node['sampler_source']=name(p,'SamplerSource','SSM_FromTextureAsset');node['sampler_type']=name(p,'SamplerType','SAMPLERTYPE_Color')
        if kind=='TextureCoordinate':node['uv_index']=val(p,'CoordinateIndex',['IntProperty'],'i',0);node['uv_scale']=[val(p,k,['FloatProperty'],'f',1.) for k in ('UTiling','VTiling')]
        if kind=='ComponentMask':node['mask']=[1]+[int(boolval(p,k)) for k in ('R','G','B','A')]
        if kind in ('TextureSample','TextureSampleParameter2D') and 'Texture' in p:node['texture']=imported(p,'Texture',('Texture2D',))
        if kind=='NamedRerouteUsage':node['declaration']=object_index(p,'Declaration')
        if kind=='StaticSwitchParameter':node['value']=boolval(p,'DefaultValue')
        if kind=='LinearInterpolate':node['defaults']={k:val(p,'Const'+k,['FloatProperty'],'f',d) for k,d in [('A',0.),('B',1.),('Alpha',.5)]}
        if kind in ('Multiply','Add','Subtract','Divide'):node['defaults']={k:val(p,'Const'+k,['FloatProperty'],'f',1. if kind in ('Multiply','Divide') else 0.) for k in ('A','B')}
        nodes[j]=node
    for n in nodes.values():
        for a in list(n['inputs'].values())+[v['edge'] for v in n.get('function_inputs',[])]:require(not a['index'] or a['index'] in nodes,'Expression input outside graph')
        if 'declaration' in n:require(n['declaration'] in nodes and nodes[n['declaration']]['kind']=='NamedRerouteDeclaration','Invalid named reroute')
    if e['kind']=='MaterialFunction':
        interfaces=[n['interface_guid'] for n in nodes.values() if n['kind'] in ('FunctionInput','FunctionOutput')];require(len(set(interfaces))==len(interfaces),'Duplicate function interface GUID')
        return dict(name=e['name'],kind='function',nodes=nodes,unsupported=[])
    ed=object_index(t,'EditorOnlyData');require(ed>0 and ref(ed)['kind']=='MaterialEditorOnlyData' and ref(ed)['outer']==i,'Invalid material editor data');x=ref(ed);r=Reader(b[x['offset']+x['script_start']:x['offset']+x['script_end']]);props=read_tag_stream(r,names,control=True,indexed=True);require(r.pos==len(r.data),'Invalid editor property extent')
    outputs={}
    for k,v in props.items():
        if len(v['type'])==3 and v['type'][1].endswith('MaterialInput') and len(v['data'])>=40:
            a=edge(v['data']);a['use_constant']=struct.unpack_from('<i',v['data'],36)[0];require(a['use_constant'] in (0,1),'Invalid material constant flag');a['constant']=list(struct.unpack('<'+'f'*((len(v['data'])-40)//4),v['data'][40:]));outputs[str(k)]=a
    for n in nodes.values():
        for a in n['inputs'].values():require(not a['index'] or a['index'] in nodes,'Expression input outside material')
        if 'declaration' in n:require(n['declaration'] in nodes and nodes[n['declaration']]['kind']=='NamedRerouteDeclaration','Invalid named reroute')
    require(all(not a['index'] or a['index'] in nodes for a in outputs.values()),'Material output outside graph')
    return dict(name=e['name'],kind='material',blend=name(t,'BlendMode','BLEND_Opaque'),nodes=nodes,outputs=outputs,unsupported=['UseMaterialAttributes'] if boolval(t,'bUseMaterialAttributes') else [])


def expand_local_functions(data,content,unsupported):
    """Flatten local calls by serialized interface GUID, never positional guessing.
    External function definitions remain explicit dependencies. All copied nodes
    retain source package and export index for inspection.
    """
    from copy import deepcopy
    nodes=data['nodes'];next_id=max(nodes,default=0)+1;catalog={}
    def expand(call,stack):
        nonlocal next_id
        p=call['function']
        if not p.startswith('/Game/'):return
        require(p not in stack and len(stack)<12,'Material function cycle or depth limit')
        f=(content/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(content) and f.is_file(),'Missing material function '+p)
        if p not in catalog:catalog[p]=read_material(f)
        source=catalog[p];require(source['kind']=='function','Invalid material function class')
        original=source['nodes'];require(len(nodes)+len(original)<=8192,'Material function graph limit')
        idmap={i:next_id+j for j,i in enumerate(original)};next_id+=len(original)
        inputs={v['guid']:v['edge'] for v in call['function_inputs']};outputs={v['interface_guid']:i for i,v in original.items() if v['kind']=='FunctionOutput'}
        fninputs={v['interface_guid']:i for i,v in original.items() if v['kind']=='FunctionInput'}
        require(set(inputs)<=set(fninputs) and all(v['guid'] in outputs for v in call['function_outputs']),'Material function interface GUID mismatch '+p)
        def remap(a):
            a=deepcopy(a)
            if a['index']:a['index']=idmap[a['index']]
            return a
        new={}
        for i,v in original.items():
            n=deepcopy(v);n['source_function']=p;n['source_export_index']=i;n['inputs']={k:remap(a) for k,a in v['inputs'].items()}
            if 'declaration' in n:n['declaration']=idmap[n['declaration']]
            if n['kind']=='FunctionInput':
                a=inputs.get(n['interface_guid']);n['bound_input']=deepcopy(a) if a and a['index'] else n['inputs'].get('Preview') if n['preview_default'] else None
                require(n['bound_input'] is not None,'Unbound material function input '+n['interface_name'])
            for a in n.get('function_inputs',[]):a['edge']=remap(a['edge'])
            new[idmap[i]]=n
        nodes.update(new)
        call['expanded_outputs']=[idmap[outputs[v['guid']]] for v in call['function_outputs']]
        for n in new.values():
            if n['kind']=='MaterialFunctionCall' and n['function'].startswith('/Game/'):expand(n,(*stack,p))
    for n in list(nodes.values()):
        if n['kind']=='MaterialFunctionCall' and n['function'].startswith('/Game/'):
            try:expand(n,())
            except (ValueError,KeyError,NotImplementedError) as exc:unsupported.append('Material function expansion: '+str(exc))
    data['function_packages']=sorted(catalog)


def apply_overrides(nodes,overrides,unsupported):
    groups={}
    for n in nodes.values():
        kind={'ScalarParameter':'scalar','VectorParameter':'vector','TextureSampleParameter2D':'texture','StaticSwitchParameter':'switch'}.get(n['kind'])
        if kind and n['parameter']:groups.setdefault((kind,n['parameter']),[]).append(n)
    for key,group in groups.items():
        v=overrides.get(key)
        if not v:continue
        guid=v['guid'];field='texture' if key[0]=='texture' else 'value'
        if guid and any(bytes.fromhex(guid)) and not any(n['guid']==guid for n in group):
            unsupported.append('Parameter GUID mismatch: '+key[1]);continue
        for n in group:
            n[field]=v['value'];n['override_guid']=guid;n['override_resolution']='exact_guid' if n['guid']==guid else 'shared_global_parameter'


def resolve_material(content,package):
    content=Path(content).resolve();seen=set();chain=[];overrides={};unsupported=[]
    def path(p):
        require(p.startswith('/Game/'),'Material dependency is outside project: '+p);f=(content/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(content) and f.is_file(),'Missing material package '+p);return f
    p=package
    while True:
        require(p not in seen and len(seen)<32,'Material inheritance cycle or depth limit');seen.add(p);data=read_material(path(p));chain.append(p);unsupported.extend(data['unsupported'])
        if data['kind']=='material':break
        require(data['kind']=='instance','Expected material or instance')
        for v in data['parameters']:overrides.setdefault((v['kind'],v['name']),v)
        p=data['parent']
    # A global parameter with identical name and type is shared by all its
    # expressions (Epic Material Expressions Reference). Accept duplicate
    # GUIDs only when the override GUID matches a member of that exact group.
    expand_local_functions(data,content,unsupported)
    apply_overrides(data['nodes'],overrides,unsupported)
    data.update(package=package,chain=chain,parameters=list(overrides.values()),unsupported=unsupported);return data


def build_material(content,package,allow_partial=False):
    import bpy
    from texture_blender import load_editor_texture
    data=resolve_material(content,package);mat=bpy.data.materials.new(package.rsplit('/',1)[-1]);mat.use_nodes=True;mat['UE_material_package']=package
    mat['UE_editor_graph']=json.dumps(data,sort_keys=True); nt=mat.node_tree;nodes=nt.nodes;links=nt.links;bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');bs.location=(650,0);built={};active=set();issues=list(data['unsupported']);connected=[]
    def node(typ,label):
        n=nodes.new(typ);n.label=label;n.location=(-600+(len(nodes)%4)*220,-240*(len(nodes)//4));return n
    def constant(value,label):
        n=node('ShaderNodeRGB' if isinstance(value,list) else 'ShaderNodeValue',label);n.outputs[0].default_value=value;return n.outputs[0]
    def mathop(op,x,y=None,label='Source arithmetic'):
        n=node('ShaderNodeMath',label);n.operation=op
        for j,v in enumerate((x,y)):
            if v is None:continue
            if isinstance(v,(int,float)):n.inputs[j].default_value=v
            else:links.new(v,n.inputs[j])
        return n.outputs[0]
    def components(sock):
        if sock.type=='VALUE':return (sock,sock,sock)
        n=node('ShaderNodeSeparateXYZ','Source vector components');links.new(sock,n.inputs[0]);return tuple(n.outputs)
    def combine(values,label='Source vector'):
        n=node('ShaderNodeCombineXYZ',label)
        for j,v in enumerate(values):
            if isinstance(v,(int,float)):n.inputs[j].default_value=v
            else:links.new(v,n.inputs[j])
        return n.outputs[0]
    def swap_xy(sock,scale=1.):
        x,y,z=components(sock);return combine([mathop('MULTIPLY',q,scale) if scale!=1. else q for q in (y,x,z)],'Blender ↔ Unreal basis')
    def vectorop(op,a,b=None,label='Source vector arithmetic'):
        n=node('ShaderNodeVectorMath',label);n.operation=op;links.new(a,n.inputs[0])
        if b is not None:links.new(b,n.inputs[1])
        return n.outputs['Value' if op=='DOT_PRODUCT' else 'Vector']
    def select(sock,mask):
        if not mask[0] or mask[1:]==[1,1,1,0]:return sock
        if mask[1:]==[0,0,0,1] and sock.node.type=='TEX_IMAGE':return sock.node.outputs['Alpha']
        if not mask[4] and 1<=sum(mask[1:])<=2:
            selected=[v for v,m in zip(components(sock),mask[1:4]) if m]
            return selected[0] if len(selected)==1 else combine([*selected,0.],'Serialized two-channel mask')
        raise NotImplementedError('Unsupported output channel mask')
    def static_value(i,seen=()):
        require(i not in seen and i>0,'Cyclic static input');d=data['nodes'][i]
        if d['kind']=='StaticBool' and 'value' in d:return d['value']
        if d['kind']=='FunctionInput':return static_value(d['bound_input']['index'],(*seen,i))
        raise NotImplementedError('Nonconstant static switch input')
    def mix(a,b,f,label):
        if a.type==b.type=='VALUE':return mathop('ADD',a,mathop('MULTIPLY',mathop('SUBTRACT',b,a),f),label)
        n=node('ShaderNodeMixRGB',label);n.blend_type='MIX';n.use_clamp=False
        for j,v in enumerate((f,a,b)):links.new(v,n.inputs[j])
        return n.outputs[0]
    def configure_sampler(n):
        image=n.image;x=image.get('UE_address_x','TA_Wrap');y=image.get('UE_address_y','TA_Wrap')
        n.interpolation='Closest' if image.get('nearest',False) else 'Linear'
        if x==y and x in ('TA_Wrap','TA_Clamp','TA_Mirror'):
            n.extension={'TA_Wrap':'REPEAT','TA_Clamp':'EXTEND','TA_Mirror':'MIRROR'}[x]
        else:issues.append('Unsupported mixed texture address modes: '+image.name)
    def edge(a):
        require(a['index']>0,'Missing expression input');return select(emit(a['index'],a['output']),a['mask'])
    def emit(i,output=0):
        key=(i,output)
        if key in built:return built[key]
        require(i not in active,'Material expression cycle');active.add(i)
        try:
            d=data['nodes'][i];kind=d['kind'];label=d['parameter'] or d['name'];ins=d['inputs']
            if kind in ('ScalarParameter','VectorParameter','Constant','Constant3Vector') and output==0:s=constant(d['value'],label)
            elif kind=='FunctionInput' and output==0:s=edge(d['bound_input'])
            elif kind=='FunctionOutput' and output==0:s=edge(ins['A'])
            elif kind=='StaticSwitch' and output==0:s=edge(ins['A' if static_value(ins['Value']['index']) else 'B'])
            elif kind=='If' and output==0:
                a=edge(ins['A']);b=edge(ins['B']) if 'B' in ins else constant(d['defaults']['B'],'If B');require(a.type==b.type=='VALUE','Non-scalar If comparison')
                g,l=edge(ins['AGreaterThanB']),edge(ins['ALessThanB']);s=mix(l,g,mathop('GREATER_THAN',a,b),label)
                if 'AEqualsB' in ins and ins['AEqualsB']['index']:
                    eq=mathop('LESS_THAN',mathop('ABSOLUTE',mathop('SUBTRACT',a,b)),d['threshold']);s=mix(s,edge(ins['AEqualsB']),eq,label+' equality')
                else:issues.append('If equality boundary is a preview; no Unreal-evaluated reference')
            elif kind in ('WorldPosition','ActorPositionWS','VertexNormalWS') and output==0:
                if kind=='ActorPositionWS':n=node('ShaderNodeObjectInfo',label);sock=n.outputs['Location'];issues.append('Actor origin approximated by Blender object origin')
                else:n=node('ShaderNodeNewGeometry',label);sock=n.outputs['Position' if kind=='WorldPosition' else 'Normal']
                s=swap_xy(sock,100. if kind!='VertexNormalWS' else 1.)
                if kind=='VertexNormalWS':issues.append('VertexNormalWS approximated by Blender interpolated shading normal')
            elif kind=='PreSkinnedNormal' and output==0:
                n=node('ShaderNodeNewGeometry',label);t=node('ShaderNodeVectorTransform','Rest-normal preview');t.vector_type='NORMAL';t.convert_from='WORLD';t.convert_to='OBJECT';links.new(n.outputs['Normal'],t.inputs[0]);s=swap_xy(t.outputs[0]);issues.append('PreSkinnedNormal uses current object normal; rest/deformed equivalence not verified')
            elif kind=='VertexInterpolator' and output==0:s=edge(ins['Input']);issues.append('VertexInterpolator evaluated per shading point as a preview')
            elif kind=='Transform' and output==0 and d['transform_source']=='TRANSFORMSOURCE_Local' and d['transform_target']=='TRANSFORM_World':
                n=node('ShaderNodeVectorTransform',label);n.vector_type='VECTOR';n.convert_from='OBJECT';n.convert_to='WORLD';links.new(swap_xy(edge(ins['Input'])),n.inputs[0]);s=swap_xy(n.outputs[0]);issues.append('Object-to-world transform preview not independently verified')
            elif kind=='AppendVector' and output==0:
                a,b=edge(ins['A']),edge(ins['B']);require(a.type==b.type=='VALUE','Unsupported AppendVector widths');s=combine([a,b,0.],label)
            elif kind=='TextureCoordinate' and output==0:
                n=node('ShaderNodeUVMap',label);n.uv_map='UV'+str(d['uv_index']);u,v,_=components(n.outputs['UV']);s=combine([mathop('MULTIPLY',u,d['uv_scale'][0]),mathop('MULTIPLY',mathop('SUBTRACT',1.,v),d['uv_scale'][1]),0.],label)
            elif kind=='Normalize' and output==0:s=vectorop('NORMALIZE',edge(ins['VectorInput']),label=label)
            elif kind=='DotProduct' and output==0:s=vectorop('DOT_PRODUCT',edge(ins['A']),edge(ins['B']),label)

            elif kind=='NamedRerouteUsage' and output==0:s=emit(d['declaration'])
            elif kind in ('NamedRerouteDeclaration','Reroute') and output==0:s=edge(ins['Input'])
            elif kind=='ComponentMask' and output==0:s=select(edge(ins['Input']),d['mask'])
            elif kind in ('OneMinus','Saturate','Abs','Sign') and output==0:
                a=edge(ins['Input']);require(a.type=='VALUE','Unsupported non-scalar '+kind)
                n=node('ShaderNodeMath',label);n.operation={'OneMinus':'SUBTRACT','Saturate':'ADD','Abs':'ABSOLUTE','Sign':'SIGN'}[kind]
                if kind=='OneMinus':n.inputs[0].default_value=1.;links.new(a,n.inputs[1])
                else:
                    links.new(a,n.inputs[0]);n.inputs[1].default_value=0.;n.use_clamp=kind=='Saturate'
                s=n.outputs[0]
            elif kind in ('Add','Subtract','Divide') and output==0:
                a,b=[edge(ins[k]) if k in ins and ins[k]['index'] else constant(d['defaults'][k],k) for k in ('A','B')];op={'Add':'ADD','Subtract':'SUBTRACT','Divide':'DIVIDE'}[kind]
                s=mathop(op,a,b,label) if a.type==b.type=='VALUE' else vectorop(op,a,b,label)
            elif kind in ('TextureSampleParameter2D','TextureSample') and 0<=output<=4 and not any(v['index'] for k,v in ins.items() if k!='Coordinates'):
                if (i,0) not in built:
                    coordinates=None
                    if 'Coordinates' in ins and ins['Coordinates']['index']:
                        x,y,z=components(edge(ins['Coordinates']));coordinates=combine([x,mathop('SUBTRACT',1.,y),0.],'Unreal V origin')
                    p=d.get('texture');require(p and p.startswith('/Game/'),'Missing local texture reference');root=Path(content).resolve();f=(root/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(root) and f.is_file(),'Missing texture '+p);n=node('ShaderNodeTexImage',label);n.image=load_editor_texture(f);n['UE_texture_package']=p;configure_sampler(n);built[i,0]=n.outputs['Color']
                    if n.image.get('UE_texture_profile')=='UE5 1004 editor PNG':issues.append('Legacy PNG channel interpretation not independently verified')
                    if coordinates is not None:links.new(coordinates,n.inputs['Vector'])
                    if d['sampler_source'] in ('SSM_Wrap_WorldGroupSettings','SSM_Clamp_WorldGroupSettings'):n.extension='REPEAT' if d['sampler_source']=='SSM_Wrap_WorldGroupSettings' else 'EXTEND';issues.append('World-group sampler filtering preview')
                    elif d['sampler_source']!='SSM_FromTextureAsset':issues.append('Unsupported sampler source '+d['sampler_source'])
                s=built[i,0];s=s.node.outputs['Alpha'] if output==4 else s
                if 1<=output<=3:s=select(s,[1]+[int(k==output) for k in range(1,5)])
            elif kind=='LinearInterpolate' and output==0:
                a,b,f=[edge(ins[k]) if k in ins else constant(d['defaults'][k],k) for k in ('A','B','Alpha')]
                s=mix(a,b,f,label)
            elif kind=='Multiply' and output==0:
                a,b=[edge(ins[k]) if k in ins else constant(d['defaults'][k],k) for k in ('A','B')];color=any(x.type in ('RGBA','VECTOR') for x in (a,b));n=node('ShaderNodeMixRGB' if color else 'ShaderNodeMath',label)
                if color and (a.type=='VECTOR' or b.type=='VECTOR'):
                    nodes.remove(n);s=vectorop('MULTIPLY',a,b,label);built[key]=s;return s
                elif color:n.blend_type='MULTIPLY';n.inputs[0].default_value=1.;links.new(a,n.inputs[1]);links.new(b,n.inputs[2])
                else:n.operation='MULTIPLY';links.new(a,n.inputs[0]);links.new(b,n.inputs[1])
                s=n.outputs[0]
            elif kind=='StaticSwitchParameter' and output==0 and not any('Unsupported static parameter' in x for x in issues):s=edge(ins['A' if d['value'] else 'B'])
            elif kind=='MaterialFunctionCall':
                if 'expanded_outputs' in d:
                    require(output<len(d['expanded_outputs']),'Invalid function output slot');s=emit(d['expanded_outputs'][output])
                elif d['function']=='/Engine/Functions/Engine_MaterialFunctions02/Utility/MakeFloat3' and output==0:
                    args={v['edge']['input_name']:v['edge'] for v in d['function_inputs']};require(set(args)=={'X','Y','Z'},'Unexpected MakeFloat3 signature');s=combine([edge(args[k]) for k in ('X','Y','Z')],label);issues.append('Engine MakeFloat3 implemented by semantic equivalent; source package absent')
                elif d['function']=='/Engine/Functions/Engine_MaterialFunctions02/Utility/BreakOutFloat3Components' and output in (0,1,2):
                    args={v['edge']['input_name']:v['edge'] for v in d['function_inputs']};require(set(args)=={'Float3'},'Unexpected BreakOutFloat3Components signature');s=components(edge(args['Float3']))[output];issues.append('Engine BreakOutFloat3Components semantic preview; source package absent')
                elif d['function']=='/Engine/Functions/Engine_MaterialFunctions01/Opacity/CameraDepthFade' and output==0:
                    args={v['edge']['input_name']:v['edge'] for v in d['function_inputs']};require(set(args)=={'Fade Length','Fade Offset','For Vertex Shader'} and not args['For Vertex Shader']['index'],'Unsupported CameraDepthFade signature');length,offset=edge(args['Fade Length']),edge(args['Fade Offset']);require(length.type==offset.type=='VALUE','Invalid camera fade parameters');n=node('ShaderNodeCameraData',label);s=mathop('DIVIDE',mathop('SUBTRACT',mathop('MULTIPLY',n.outputs['View Z Depth'],100.),offset),length,label);s.node.use_clamp=True;issues.append('Engine CameraDepthFade formula preview; source package absent')
                elif d['function']=='/Engine/Functions/Engine_MaterialFunctions01/Texturing/ScaleUVsByCenter' and output==0:
                    args={v['edge']['input_name']:v['edge'] for v in d['function_inputs']};require(set(args)=={'UVs','Texture Scale'},'Unexpected ScaleUVsByCenter signature');u,v,_=components(edge(args['UVs']));scale=edge(args['Texture Scale']);require(scale.type=='VALUE','Non-scalar centered UV scale');s=combine([mathop('ADD',mathop('DIVIDE',mathop('SUBTRACT',q,.5),scale),.5) for q in (u,v)]+[0.],label);issues.append('Engine ScaleUVsByCenter preview; source package absent')
                elif d['function']=='/Engine/Functions/Engine_MaterialFunctions01/ImageAdjustment/CheapContrast' and output==0:
                    args={v['edge']['input_name']:v['edge'] for v in d['function_inputs']};require(set(args)=={'In','Contrast'},'Unexpected CheapContrast signature');x,c=edge(args['In']),edge(args['Contrast']);require(x.type==c.type=='VALUE','Non-scalar CheapContrast');s=mathop('SUBTRACT',mathop('MULTIPLY',x,mathop('ADD',1.,mathop('MULTIPLY',2.,c))),c,label);s.node.use_clamp=True;issues.append('Engine CheapContrast formula preview; source package absent')
                else:raise NotImplementedError('Unresolved material function '+d['function'])
            else:raise NotImplementedError('Unsupported expression '+kind)
            built[key]=s;return s
        finally:active.remove(i)
    for k,socket in [('BaseColor','Base Color'),('Metallic','Metallic'),('Roughness','Roughness'),('Specular','Specular IOR Level'),('Normal','Normal'),('EmissiveColor','Emission Color')]:
        a=data['outputs'].get(k)
        if not a:continue
        try:
            if a['index']:
                s=edge(a)
                if k=='Specular':issues.append('Unreal specular to Principled IOR mapping not independently verified')
                if k=='Normal':
                    n=node('ShaderNodeNormalMap','Unreal tangent normal (Blender basis preview)');links.new(s,n.inputs['Color']);s=n.outputs[0];issues.append('Tangent-space normal basis not independently verified')
                if k=='EmissiveColor':bs.inputs['Emission Strength'].default_value=1.
                links.new(s,bs.inputs[socket]);connected.append(k)
            elif a['use_constant'] and k!='Normal':
                v=a['constant'];bs.inputs[socket].default_value=v[0] if len(v)==1 else v;connected.append(k)
        except Exception as exc:issues.append(k+': '+str(exc))
    # Preserve AO as an editable data branch without multiplying base color or
    # claiming Principled has an equivalent Unreal ambient-occlusion input.
    ao=data['outputs'].get('AmbientOcclusion');preserved=[]
    if ao and ao['index']:
        try:
            s=edge(ao);n=node('ShaderNodeMath','Unreal Ambient Occlusion (unconnected data)');n.operation='ADD';n.inputs[1].default_value=0.;links.new(s,n.inputs[0]);preserved.append('AmbientOcclusion');issues.append('Ambient Occlusion preserved; no equivalent Principled input')
        except Exception as exc:issues.append('AmbientOcclusion: '+str(exc))
    for k,a in data['outputs'].items():
        if a['index'] and k not in connected and k not in preserved:issues.append('Untranslated output '+k)
    if data['blend']!='BLEND_Opaque':issues.append('Untranslated blend mode '+data['blend'])
    status='partial' if issues else 'supported_pbr_subset';mat['UE_editor_material_status']=status;mat['UE_unresolved_material']=bool(issues);mat['UE_editor_material_issues']=json.dumps(sorted(set(issues)));mat['UE_editor_connected_outputs']=json.dumps(connected);mat['UE_editor_preserved_outputs']=json.dumps(preserved)
    if issues and not allow_partial:
        # Do not connect an incomplete shader without explicit opt-in. Preserve graph metadata.
        for link in list(links):
            if link.to_node==bs:links.remove(link)
        nodes.remove(bs);bs=nodes.new('ShaderNodeBsdfPrincipled');bs.location=(650,0);out=next(n for n in nodes if n.type=='OUTPUT_MATERIAL');links.new(bs.outputs[0],out.inputs['Surface'])
        mat['UE_editor_material_status']='metadata_only'
    return mat


def bind_slots(objects,content,allow_partial=False,cache=None):
    """Resolve exact package identities; retain failed source slots, never guess names.
    Cache is scoped to this import invocation and only contains new material IDs.
    """
    if cache is None:cache={}
    records={}
    for obj in objects:
        if obj.type!='MESH':continue
        for slot in obj.material_slots:
            old=slot.material;package=old.get('UE_material_package','') if old else ''
            if not package:continue
            if package not in cache:
                try:cache[package]=(build_material(content,package,allow_partial),'')
                except Exception as exc:cache[package]=(None,f'{type(exc).__name__}: {exc}')
            mat,error=cache[package]
            if mat:
                slot.material=mat;records[package]={'status':mat['UE_editor_material_status'],'issues':json.loads(mat['UE_editor_material_issues']),'outputs':json.loads(mat['UE_editor_connected_outputs'])}
            else:records[package]={'status':'unresolved','detail':error}
    return records
