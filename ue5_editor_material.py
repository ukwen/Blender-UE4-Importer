"""Tagged UE5 editor material graph, global instance overrides and bounded PBR subset.
No execution of custom HLSL, engine functions or particle/runtime expressions.
"""
import json, math, struct
from pathlib import Path
from skeleton_native import Reader
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags,read_tag_stream,read_tags


def read_material(path):
    m,b,im,ex,ref,pkg=read_tables(path); names=m['names']
    roots=[(i,e) for i,e in enumerate(ex,1) if not e['outer'] and e['kind'] in ('Material','MaterialInstanceConstant')];require(len(roots)==1,'Expected one material root');i,e=roots[0]
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
        require(len(data)>=36,'Truncated expression input'); r=Reader(data); j,slot=r.unpack('2i');nm=r.name(names);mask=r.unpack('5i');require(0<=j<=len(ex) and 0<=slot<64 and all(v in (0,1) for v in mask),'Invalid expression reference');return dict(index=j,output=slot,mask=list(mask),input_name=nm)
    nodes={}
    for j,x in enumerate(ex,1):
        if x['outer']!=i or not x['kind'].startswith('MaterialExpression') or x['kind'].endswith('Comment'):continue
        p=export_tags(b,x,names);kind=x['kind'].removeprefix('MaterialExpression');node=dict(kind=kind,name=x['name'],parameter=name(p,'ParameterName'),guid=p.get('ExpressionGUID',{}).get('data',b'').hex(),position=[val(p,'MaterialExpressionEditorX',['IntProperty'],'i',0),val(p,'MaterialExpressionEditorY',['IntProperty'],'i',0)],inputs={k:edge(v['data']) for k,v in p.items() if v['type']==['StructProperty','ExpressionInput','/Script/Engine'] and len(v['data'])==36})
        if kind=='ScalarParameter':node['value']=val(p,'DefaultValue',['FloatProperty'],'f',0.)
        if kind=='VectorParameter':node['value']=val(p,'DefaultValue',['StructProperty','LinearColor','/Script/CoreUObject'],'4f',[0.,0.,0.,1.])
        if kind=='Constant':node['value']=val(p,'R',['FloatProperty'],'f',0.)
        if kind=='Constant3Vector':node['value']=val(p,'Constant',['StructProperty','LinearColor','/Script/CoreUObject'],'4f',[0.,0.,0.,1.])
        if kind=='MaterialFunctionCall':node['function']=imported(p,'MaterialFunction',('MaterialFunction','MaterialFunctionInstance'))
        if kind=='TextureCoordinate':node['uv_index']=val(p,'CoordinateIndex',['IntProperty'],'i',0);node['uv_scale']=[val(p,k,['FloatProperty'],'f',1.) for k in ('UTiling','VTiling')]
        if kind=='ComponentMask':node['mask']=[1]+[int(boolval(p,k)) for k in ('R','G','B','A')]
        if kind in ('TextureSample','TextureSampleParameter2D') and 'Texture' in p:node['texture']=imported(p,'Texture',('Texture2D',))
        if kind=='NamedRerouteUsage':node['declaration']=object_index(p,'Declaration')
        if kind=='StaticSwitchParameter':node['value']=boolval(p,'DefaultValue')
        if kind=='LinearInterpolate':node['defaults']={k:val(p,'Const'+k,['FloatProperty'],'f',d) for k,d in [('A',0.),('B',1.),('Alpha',.5)]}
        if kind in ('Multiply','Add','Subtract','Divide'):node['defaults']={k:val(p,'Const'+k,['FloatProperty'],'f',1. if kind in ('Multiply','Divide') else 0.) for k in ('A','B')}
        nodes[j]=node
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


def resolve_material(content,package):
    content=Path(content).resolve();seen=set();chain=[];overrides={};unsupported=[]
    def path(p):
        require(p.startswith('/Game/'),'Material dependency is outside project: '+p);f=(content/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(content) and f.is_file(),'Missing material package '+p);return f
    p=package
    while True:
        require(p not in seen and len(seen)<32,'Material inheritance cycle or depth limit');seen.add(p);data=read_material(path(p));chain.append(p);unsupported.extend(data['unsupported'])
        if data['kind']=='material':break
        for v in data['parameters']:overrides.setdefault((v['kind'],v['name']),v)
        p=data['parent']
    for n in data['nodes'].values():
        kind={'ScalarParameter':'scalar','VectorParameter':'vector','TextureSampleParameter2D':'texture','StaticSwitchParameter':'switch'}.get(n['kind']);v=overrides.get((kind,n['parameter']))
        if v:
            if v['guid'] and any(bytes.fromhex(v['guid'])) and n['guid']!=v['guid']:unsupported.append('Parameter GUID mismatch: '+n['parameter']);continue
            n['texture' if kind=='texture' else 'value']=v['value']
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
    def select(sock,mask):
        if not mask[0] or mask[1:]==[1,1,1,0]:return sock
        if mask[1:]==[0,0,0,1] and sock.node.type=='TEX_IMAGE':return sock.node.outputs['Alpha']
        if sum(mask[1:])==1 and not mask[4]:
            if sock.type=='VALUE':return sock
            n=node('ShaderNodeSeparateColor','Serialized channel mask');links.new(sock,n.inputs[0]);return n.outputs[mask[1:].index(1)]
        raise NotImplementedError('Unsupported output channel mask')
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
                a,b=[edge(ins[k]) if k in ins and ins[k]['index'] else constant(d['defaults'][k],k) for k in ('A','B')];require(a.type==b.type=='VALUE','Unsupported non-scalar '+kind)
                n=node('ShaderNodeMath',label);n.operation={'Add':'ADD','Subtract':'SUBTRACT','Divide':'DIVIDE'}[kind];links.new(a,n.inputs[0]);links.new(b,n.inputs[1]);s=n.outputs[0]
            elif kind in ('TextureSampleParameter2D','TextureSample') and 0<=output<=4 and not any(v['index'] for v in ins.values()):
                if (i,0) not in built:
                    p=d.get('texture');require(p and p.startswith('/Game/'),'Missing local texture reference');root=Path(content).resolve();f=(root/(p[6:]+'.uasset')).resolve();require(f.is_relative_to(root) and f.is_file(),'Missing texture '+p);n=node('ShaderNodeTexImage',label);n.image=load_editor_texture(f);n['UE_texture_package']=p;configure_sampler(n);built[i,0]=n.outputs['Color']
                s=built[i,0];s=s.node.outputs['Alpha'] if output==4 else s
                if 1<=output<=3:s=select(s,[1]+[int(k==output) for k in range(1,5)])
            elif kind=='LinearInterpolate' and output==0:
                a,b,f=[edge(ins[k]) if k in ins else constant(d['defaults'][k],k) for k in ('A','B','Alpha')]
                if a.type==b.type==f.type=='VALUE':
                    def mathop(op,x,y):
                        n=node('ShaderNodeMath',label);n.operation=op;links.new(x,n.inputs[0]);links.new(y,n.inputs[1]);return n.outputs[0]
                    s=mathop('ADD',a,mathop('MULTIPLY',mathop('SUBTRACT',b,a),f))
                else:
                    n=node('ShaderNodeMixRGB',label);n.blend_type='MIX';n.use_clamp=False
                    for j,v in enumerate((f,a,b)):links.new(v,n.inputs[j])
                    s=n.outputs[0]
            elif kind=='Multiply' and output==0:
                a,b=[edge(ins[k]) if k in ins else constant(d['defaults'][k],k) for k in ('A','B')];color=any(x.type in ('RGBA','VECTOR') for x in (a,b));n=node('ShaderNodeMixRGB' if color else 'ShaderNodeMath',label)
                if color:n.blend_type='MULTIPLY';n.inputs[0].default_value=1.;links.new(a,n.inputs[1]);links.new(b,n.inputs[2])
                else:n.operation='MULTIPLY';links.new(a,n.inputs[0]);links.new(b,n.inputs[1])
                s=n.outputs[0]
            elif kind=='StaticSwitchParameter' and output==0 and not any('Unsupported static parameter' in x for x in issues):s=edge(ins['A' if d['value'] else 'B'])
            elif kind=='MaterialFunctionCall':raise NotImplementedError('Unresolved material function '+d['function'])
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
