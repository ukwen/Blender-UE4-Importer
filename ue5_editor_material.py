"""Tagged UE5 editor material graph, global instance overrides and bounded PBR subset.
No execution of custom HLSL, engine functions or particle/runtime expressions.
"""
import json, math, struct
from pathlib import Path
from skeleton_native import Reader
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags,read_tag_stream,read_tags

EDITOR_MATERIAL_REVISION = "editor_material_084"


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
            # Active flags are resolved after traversing the complete instance chain.
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
        if kind=='Constant2Vector':node['value']=[val(p,k,['FloatProperty'],'f',0.) for k in ('R','G')]
        if kind=='Power':node['exponent']=val(p,'ConstExponent',['FloatProperty'],'f',2.)
        if kind=='SphereMask':
            node['radius']=val(p,'AttenuationRadius',['FloatProperty'],'f',256.);node['hardness_percent']=val(p,'HardnessPercent',['FloatProperty'],'f',100.)
        if kind=='Panner':
            node['speed']=[val(p,k,['FloatProperty'],'f',0.) for k in ('SpeedX','SpeedY')];node['fractional']=boolval(p,'bFractionalPart');node['uv_index']=val(p,'ConstCoordinate',['IntProperty'],'i',0)
        if kind=='Time':node['period']=val(p,'Period',['FloatProperty'],'f',0.) if boolval(p,'bOverride_Period') else None;node['ignore_pause']=boolval(p,'bIgnorePause')
        if kind=='WorldPosition':node['world_offset']=name(p,'WorldPositionShaderOffset','default_not_serialized')
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
    # A single explicit unlit shading model is required for the transparent
    # surface preview. Preserve unfamiliar fields without guessing their meaning.
    shading=name(t,'ShadingModel','not_serialized');domain=name(t,'MaterialDomain','MD_Surface')
    shading_field=None
    if 'ShadingModels' in t:
        x=t['ShadingModels']
        if x['type']==['StructProperty','MaterialShadingModelField','/Script/Engine'] and not x['flags']&0x28:
            try:
                sub=read_tags(x['data'],names);f=sub.get('ShadingModelField',{})
                if set(sub)=={'ShadingModelField'} and f.get('type')==['UInt16Property'] and len(f['data'])==2 and not f['flags']&0x28:shading_field=struct.unpack('<H',f['data'])[0]
            except (ValueError,KeyError,struct.error):pass
    return dict(name=e['name'],kind='material',blend=name(t,'BlendMode','BLEND_Opaque'),shading_model=shading,shading_model_field=shading_field,material_domain=domain,tangent_space_normal=boolval(t,'TangentSpaceNormal') if 'TangentSpaceNormal' in t else True,opacity_mask_clip=val(t,'OpacityMaskClipValue',['FloatProperty'],'f'),nodes=nodes,outputs=outputs,unsupported=['UseMaterialAttributes'] if boolval(t,'bUseMaterialAttributes') else [])


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
    audit=[]
    for key,v in overrides.items():
        group=groups.get(key,[])
        entry=dict(kind=key[0],name=key[1],source_package=v.get('source_package'),guid=v['guid'],value=v['value'],matched_nodes=[])
        audit.append(entry)
        if not group:
            # This serialized engine bias is not a graph parameter in the
            # tested materials; retain it without inventing a graph binding.
            intrinsic=(key==('scalar','RefractionDepthBias') and v['guid']=='00'*16)
            entry['status']='engine_parameter_not_translated' if intrinsic else 'unmatched'
            if not intrinsic:unsupported.append('Unmatched material parameter: '+key[1])
            continue
        guid=v['guid'];field='texture' if key[0]=='texture' else 'value'
        if guid and any(bytes.fromhex(guid)) and not any(n['guid']==guid for n in group):
            entry['status']='guid_mismatch';unsupported.append('Parameter GUID mismatch: '+key[1]);continue
        entry['status']='applied'
        for n in group:
            previous=n.get(field);n[field]=v['value'];n['override_guid']=guid;n['override_resolution']='exact_guid' if n['guid']==guid else 'shared_global_parameter';n['override_source_package']=v.get('source_package')
            entry['matched_nodes'].append(dict(name=n['name'] if 'name' in n else n['parameter'],guid=n['guid'],resolution=n['override_resolution'],previous_value=previous,source_function=n.get('source_function'),source_export_index=n.get('source_export_index')))
    return audit


def resolve_material(content,package):
    content=Path(content).resolve();seen=set();chain=[];overrides={};unsupported=[];history=[];base_override_history=[]
    def path(p):
        require(p.startswith('/Game/'),'Material dependency is outside project: '+p);f=(content/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(content) and f.is_file(),'Missing material package '+p);return f
    p=package
    while True:
        require(p not in seen and len(seen)<32,'Material inheritance cycle or depth limit');seen.add(p);data=read_material(path(p));chain.append(p);unsupported.extend(data['unsupported'])
        if data['kind']=='material':break
        require(data['kind']=='instance','Expected material or instance')
        if data.get('base_overrides'):base_override_history.append(dict(source_package=p,properties=data['base_overrides']))
        for v in data['parameters']:
            v=dict(v,source_package=p);key=(v['kind'],v['name']);history.append(dict(v,selected=key not in overrides));overrides.setdefault(key,v)
        p=data['parent']
    # A global parameter with identical name and type is shared by all its
    # expressions (Epic Material Expressions Reference). Accept duplicate
    # GUIDs only when the override GUID matches a member of that exact group.
    expand_local_functions(data,content,unsupported)
    audit=apply_overrides(data['nodes'],overrides,unsupported)
    from ue5_material_semantics import base_property_audit
    base_audit,base_issues=base_property_audit(base_override_history,data)
    if base_issues:unsupported.extend(['BasePropertyOverrides',*base_issues])
    data.update(package=package,chain=chain,parameters=list(overrides.values()),parameter_history=history,parameter_audit=audit,base_override_history=base_override_history,base_property_audit=base_audit,unsupported=unsupported);return data


def unlit_translucent_profile(data):
    return (data.get('blend')=='BLEND_Translucent' and data.get('shading_model')=='MSM_Unlit'
            and data.get('shading_model_field')==1 and data.get('material_domain')=='MD_Surface'
            and not data.get('unsupported') and not any(a.get('index') for k,a in data['outputs'].items()
                if k in ('ShadingModel','WorldPositionOffset','PixelDepthOffset','Refraction','MaterialAttributes')))


def masked_surface_profile(data):
    """Bounded default-lit surface mask preview."""
    clip=data.get('opacity_mask_clip')
    return (data.get('blend')=='BLEND_Masked' and data.get('material_domain')=='MD_Surface'
            and (data.get('shading_model'),data.get('shading_model_field')) in
                (('not_serialized',None),('MSM_DefaultLit',2))
            and (clip is None or 0.<clip<=1.) and not data.get('unsupported')
            and not any(a.get('index') for k,a in data['outputs'].items()
                if k in ('ShadingModel','WorldPositionOffset','PixelDepthOffset','Refraction','MaterialAttributes')))


def build_material(content,package,allow_partial=False):
    import bpy
    from texture_blender import load_editor_texture
    data=resolve_material(content,package);mat=bpy.data.materials.new(package.rsplit('/',1)[-1]);mat.use_nodes=True;mat['UE_material_package']=package
    mat['UE_editor_graph']=json.dumps(data,sort_keys=True);mat['UE_parameter_audit']=json.dumps(data['parameter_audit'],sort_keys=True); nt=mat.node_tree;nodes=nt.nodes;links=nt.links;bs=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');bs.location=(650,0);built={};texture_nodes={};texture_alpha={};active=set();issues=list(data['unsupported']);connected=[];surface_inputs={}
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
    def uv_coordinates(index,scale=(1.,1.),label='Unreal UV'):
        require(0<=index<64 and all(math.isfinite(v) for v in scale),'Invalid UV coordinate profile')
        n=node('ShaderNodeUVMap',label);n.uv_map='UV'+str(index);u,v,_=components(n.outputs['UV']);return combine([mathop('MULTIPLY',u,scale[0]),mathop('MULTIPLY',mathop('SUBTRACT',1.,v),scale[1]),0.],label)
    preview_time=None
    def time_input():
        nonlocal preview_time
        if preview_time is None:
            preview_time=constant(0.,'Unreal preview time (seconds; edit manually)');preview_time.node['UE_preview_time_seconds']=True;issues.append('Material time is an editable preview input; Unreal runtime clock not evaluated')
        return preview_time
    def swap_xy(sock,scale=1.):
        x,y,z=components(sock);return combine([mathop('MULTIPLY',q,scale) if scale!=1. else q for q in (y,x,z)],'Blender ↔ Unreal basis')
    def vectorop(op,a,b=None,label='Source vector arithmetic'):
        n=node('ShaderNodeVectorMath',label);n.operation=op;links.new(a,n.inputs[0])
        if b is not None:links.new(b,n.inputs[1])
        return n.outputs['Value' if op=='DOT_PRODUCT' else 'Vector']
    def select(sock,mask):
        if not mask[0] or mask[1:]==[1,1,1,0]:return sock
        if mask[1:]==[0,0,0,1]:
            if sock.as_pointer() in texture_alpha:return texture_alpha[sock.as_pointer()]
            if sock.node.type=='TEX_IMAGE':return sock.node.outputs['Alpha']
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
        from ue5_material_semantics import rgb_lerp
        if f.type!='VALUE':issues.append('RGB vector interpolation preview; float4 alpha and exact vector width not verified')
        return rgb_lerp(a,b,f,components=components,combine=combine,mathop=mathop,label=label)
    def configure_sampler(n,d,coordinates):
        from uv_semantics import uv_source,set_address,connect_sample
        image=n.image;n['UE_sampler_source']=d['sampler_source']
        n.interpolation='Closest' if image.get('nearest',False) else 'Linear'
        set_address(n,image)
        connect_sample(nt,n,coordinates if coordinates is not None else uv_source(nt,0))
        if n.get('UE_address_unsupported'):issues.append('Unsupported texture address modes: '+image.name)
        if n.get('UE_address_approximation'):issues.append('Mixed texture address base-level preview: '+image.name)
        if d['sampler_source'] in ('SSM_Wrap_WorldGroupSettings','SSM_Clamp_WorldGroupSettings'):issues.append('World-group sampler filtering preview')
        elif d['sampler_source']!='SSM_FromTextureAsset':issues.append('Unsupported sampler source '+d['sampler_source'])
    def edge(a):
        require(a['index']>0,'Missing expression input');sock=emit(a['index'],a['output'])
        # A serialized texture output slot already selects its channel. UE often
        # repeats the same one-hot mask on the edge, including Alpha. Do not
        # apply that mask again to the resulting scalar.
        if data['nodes'][a['index']]['kind'] in ('TextureSample','TextureSampleParameter2D','ParticleColor','VectorParameter') and 1<=a['output']<=4:
            require(not a['mask'][0] or a['mask']==[1]+[int(k==a['output']) for k in range(1,5)],'Conflicting output channel mask');return sock
        return select(sock,a['mask'])
    def emit(i,output=0):
        key=(i,output)
        if key in built:return built[key]
        require(i not in active,'Material expression cycle');active.add(i)
        try:
            d=data['nodes'][i];kind=d['kind'];label=d['parameter'] or d['name'];ins=d['inputs']
            if kind in ('ScalarParameter','Constant','Constant3Vector') and output==0:s=constant(d['value'],label)
            elif kind=='VectorParameter' and 0<=output<=4:
                if (i,0) not in built:
                    v=d['value'];require(len(v)==4,'Invalid vector parameter width');rgb=constant(v,label);alpha=constant(v[3],label+' (alpha parameter)');built[i,0]=rgb;texture_alpha[rgb.as_pointer()]=alpha
                rgb=built[i,0];s=texture_alpha[rgb.as_pointer()] if output==4 else select(rgb,[1]+[int(k==output) for k in range(1,5)]) if output else rgb
            elif kind=='Constant2Vector' and output==0:s=combine([*d['value'],0.],label)
            elif kind=='ParticleColor' and 0<=output<=4:
                # A neutral editable preview, never a recovered Niagara/Cascade value.
                if (i,0) not in built:
                    rgb=constant([1.,1.,1.,1.],label+' (preview RGB)');alpha=constant(1.,label+' (preview alpha)');built[i,0]=rgb;texture_alpha[rgb.as_pointer()]=alpha;issues.append('ParticleColor uses editable neutral preview; no particle simulation')
                rgb=built[i,0];s=texture_alpha[rgb.as_pointer()] if output==4 else select(rgb,[1]+[int(k==output) for k in range(1,5)]) if output else rgb
            elif kind=='Power' and output==0:
                a=edge(ins['Base']);e=edge(ins['Exponent']) if ins.get('Exponent',{}).get('index') else constant(d['exponent'],'Power exponent');require(a.type==e.type=='VALUE','Non-scalar Power unsupported');s=mathop('POWER',mathop('MAXIMUM',a,0.),e,label)
            elif kind=='SphereMask' and output==0:
                a,b=edge(ins['A']),edge(ins['B']);require(a.type==b.type=='VECTOR','Only vector SphereMask preview supported');radius=edge(ins['Radius']) if ins.get('Radius',{}).get('index') else constant(d['radius'],'Sphere radius')
                require(radius.type=='VALUE' and not ins.get('Hardness',{}).get('index') and 0<=d['hardness_percent']<100,'Unsupported SphereMask hardness or radius')
                dist=node('ShaderNodeVectorMath',label+' distance');dist.operation='DISTANCE';links.new(a,dist.inputs[0]);links.new(b,dist.inputs[1]);safe_radius=mathop('MAXIMUM',radius,1e-6);s=mathop('DIVIDE',mathop('SUBTRACT',1.,mathop('DIVIDE',dist.outputs['Value'],safe_radius)),1.-d['hardness_percent']/100.,label);s.node.use_clamp=True;issues.append('SphereMask source-formula preview; Unreal shader not evaluated')
            elif kind=='Time' and output==0:
                s=time_input();period=d['period'];require(period is None or period>0,'Invalid material time period')
                if period is not None:s=mathop('FLOORED_MODULO',s,period,label)
            elif kind=='Panner' and output==0:
                require(not ins.get('Speed',{}).get('index'),'Connected Panner speed unsupported');coord=edge(ins['Coordinate']) if ins.get('Coordinate',{}).get('index') else uv_coordinates(d['uv_index']);t=edge(ins['Time']) if ins.get('Time',{}).get('index') else time_input();require(coord.type=='VECTOR' and t.type=='VALUE','Unsupported Panner coordinate or time');u,v,_=components(coord);values=[mathop('ADD',q,mathop('MULTIPLY',t,speed)) for q,speed in zip((u,v),d['speed'])]
                require(not d['fractional'],'Fractional Panner mode unsupported')
                s=combine([*values,0.],label);issues.append('Panner uses source UV speeds; runtime material clock not evaluated')
            elif kind=='FunctionInput' and output==0:s=edge(d['bound_input'])
            elif kind=='FunctionOutput' and output==0:s=edge(ins['A'])
            elif kind=='StaticSwitch' and output==0:s=edge(ins['A' if static_value(ins['Value']['index']) else 'B'])
            elif kind=='If' and output==0:
                a=edge(ins['A']);b=edge(ins['B']) if 'B' in ins else constant(d['defaults']['B'],'If B');require(a.type==b.type=='VALUE','Non-scalar If comparison')
                g,l=edge(ins['AGreaterThanB']),edge(ins['ALessThanB']);s=mix(l,g,mathop('GREATER_THAN',a,b),label)
                if 'AEqualsB' in ins and ins['AEqualsB']['index']:
                    eq=mathop('LESS_THAN',mathop('ABSOLUTE',mathop('SUBTRACT',a,b)),d['threshold']);s=mix(s,edge(ins['AEqualsB']),eq,label+' equality')
                else:issues.append('If equality boundary is a preview; no Unreal-evaluated reference')
            elif kind=='IsFirstPerson' and output==0:
                s=constant(0.,'Unreal first-person preview (0 or 1)');s.node['UE_first_person_preview']=True;issues.append('First-person state is a manual preview control; Unreal runtime state not evaluated')
            elif kind=='Length' and output==0:
                a=ins['Input'];src=data['nodes'][a['index']]
                if src['kind']=='WorldPosition' and src.get('world_offset')=='WPT_CameraRelative' and a['output']==0 and a['mask'] in ([0,0,0,0,0],[1,1,1,1,0]):
                    n=node('ShaderNodeCameraData','Camera-relative distance preview');s=mathop('MULTIPLY',n.outputs['View Distance'],100.,label+' (cm)');issues.append('Camera-relative length uses Blender camera distance; no Unreal first-person projection parity')
                else:
                    v=edge(a);require(v.type=='VECTOR','Unsupported Length input');n=node('ShaderNodeVectorMath',label);n.operation='LENGTH';links.new(v,n.inputs[0]);s=n.outputs['Value']
            elif kind in ('WorldPosition','ActorPositionWS','VertexNormalWS') and output==0:
                if kind=='WorldPosition':require(d.get('world_offset','default_not_serialized')=='default_not_serialized','Explicit WorldPosition offset mode unsupported: '+d['world_offset'])
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
                s=uv_coordinates(d['uv_index'],d['uv_scale'],label)
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
                    p=d.get('texture');require(p and p.startswith('/Game/'),'Missing local texture reference');root=Path(content).resolve();f=(root/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(root) and f.is_file(),'Missing texture '+p);n=node('ShaderNodeTexImage',label);n.image=load_editor_texture(f);n['UE_texture_package']=p;configure_sampler(n,d,coordinates);texture_nodes[i]=n;rgb=n.outputs['Color']
                    if n.image.get('UE_texture_profile')=='UE5 1004 editor PNG' and n.image.get('UE_texture_format')=='TSF_BGRA8':
                        # Older embedded source PNGs can contain FColor byte order
                        # encoded as RGBA. Preserve the original packed PNG; correct
                        # the sampling graph only as an explicitly partial preview.
                        r,g,b=components(rgb);rgb=combine([b,g,r],'Legacy BGRA PNG channel-order preview')
                        rgb.node['UE_legacy_png_channel_preview']='BGR to RGB';issues.append('Legacy BGRA PNG channel-order preview; Unreal-exported pixels not independently verified')
                    built[i,0]=rgb;texture_alpha[rgb.as_pointer()]=n.outputs['Alpha']
                s=texture_nodes[i].outputs['Alpha'] if output==4 else built[i,0]
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
                    src=data['nodes'][a['index']];sample=texture_nodes.get(a['index'])
                    direct=(data.get('tangent_space_normal') is True and src['kind'] in ('TextureSample','TextureSampleParameter2D') and src.get('sampler_type')=='SAMPLERTYPE_Normal' and a['output']==0 and a['mask'] in ([0,0,0,0,0],[1,1,1,1,0]) and not src['inputs'].get('Coordinates',{}).get('index') and sample is not None and sample.image.get('UE_texture_profile')=='UE5 editor UEDELTA' and sample.image.colorspace_settings.name=='Non-Color' and 'flip_y' in sample.image)
                    n=node('ShaderNodeNormalMap','Unreal tangent normal (Blender basis preview)')
                    if direct:
                        # Imported UV0 reverses V. DirectX-style source normal Y
                        # therefore needs the opposite sign, unless the source
                        # texture already requests Unreal's green-channel flip.
                        r,g,b=components(s);flip=not sample.image['flip_y']
                        s=combine([r,mathop('SUBTRACT',1.,g,'Source green convention') if flip else g,b],'Direct normal source RGB preview')
                        n.uv_map='UV0';n['UE_normal_green_inverted']=flip;n['UE_normal_source_texture']=sample['UE_texture_package'];n['UE_normal_profile']='direct UV0 source-art RGB; no runtime compression parity'
                        issues.append('Direct normal source-art green convention preview; runtime compression and tangent basis not independently verified')
                    links.new(s,n.inputs['Color']);s=n.outputs[0];issues.append('Tangent-space normal basis not independently verified')
                if k=='EmissiveColor':bs.inputs['Emission Strength'].default_value=1.
                links.new(s,bs.inputs[socket]);connected.append(k);surface_inputs[k]=s
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
    # Preserve source opacity as editable data. Only the bounded explicit unlit
    # translucent preview below consumes it; masked/runtime clipping is not inferred.
    for k in ('Opacity','OpacityMask'):
        a=data['outputs'].get(k)
        if a and a['index']:
            try:
                s=edge(a);require(s.type=='VALUE','Non-scalar opacity');n=node('ShaderNodeMath','Unreal '+k+' (source data)');n.operation='ADD';n.inputs[1].default_value=0.;links.new(s,n.inputs[0]);n['UE_preserved_output']=k;preserved.append(k);surface_inputs[k]=n.outputs[0];issues.append(k+' preserved; Unreal blend or clipping not evaluated')
            except Exception as exc:issues.append(k+': '+str(exc))
    for k,a in data['outputs'].items():
        if a['index'] and k not in connected and k not in preserved:issues.append('Untranslated output '+k)
    # Only explicit, single-model unlit translucent surface graphs with both
    # usable branches qualify. Do not use Principled alpha for lit, masked,
    # additive, or runtime-dependent blend equations. Strict mode stays opaque.
    if allow_partial and unlit_translucent_profile(data) and {'EmissiveColor','Opacity'}<=surface_inputs.keys():
        emission=node('ShaderNodeEmission','Unreal unlit emission preview');links.new(surface_inputs['EmissiveColor'],emission.inputs['Color']);emission.inputs['Strength'].default_value=1.
        transparent=node('ShaderNodeBsdfTransparent','Unreal transparent preview');transparent.inputs['Color'].default_value=(1.,1.,1.,1.)
        alpha=mathop('ADD',surface_inputs['Opacity'],0.,'Preview opacity clamped to 0–1');alpha.node.use_clamp=True
        blend=node('ShaderNodeMixShader','Unlit translucent preview (not engine blend parity)');links.new(alpha,blend.inputs[0]);links.new(transparent.outputs[0],blend.inputs[1]);links.new(emission.outputs[0],blend.inputs[2]);out=next(n for n in nodes if n.type=='OUTPUT_MATERIAL');links.new(blend.outputs[0],out.inputs['Surface']);blend['UE_unlit_translucent_preview']=True;mat['UE_surface_preview']='unlit_translucent';issues.append('Unlit emission/transparent surface approximation; no Unreal depth, sorting or renderer equivalence')
    if allow_partial and masked_surface_profile(data) and 'OpacityMask' in surface_inputs:
        clip=data.get('opacity_mask_clip');source='serialized' if clip is not None else 'preview_default_not_serialized';clip=.3333 if clip is None else clip
        threshold=constant(clip,'Unreal mask clip threshold ('+source+')');threshold.node['UE_mask_clip_source']=source
        alpha=mathop('SUBTRACT',1.,mathop('LESS_THAN',surface_inputs['OpacityMask'],threshold),'Binary mask (>= clip)')
        transparent=node('ShaderNodeBsdfTransparent','Unreal clipped surface preview');transparent.inputs['Color'].default_value=(1.,1.,1.,1.)
        blend=node('ShaderNodeMixShader','Masked surface preview (not engine blend parity)');links.new(alpha,blend.inputs[0]);links.new(transparent.outputs[0],blend.inputs[1]);links.new(bs.outputs[0],blend.inputs[2]);out=next(n for n in nodes if n.type=='OUTPUT_MATERIAL');links.new(blend.outputs[0],out.inputs['Surface']);blend['UE_masked_preview']=True;mat['UE_surface_preview']='masked';mat['UE_mask_clip_source']=source;issues.append('Binary mask surface preview; no Unreal renderer or first-person parity')
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
