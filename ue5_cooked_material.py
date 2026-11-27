"""Recover explicit UE5.4/5.6 cooked instance parameters, not a shader graph.
Schema indices verified against the matching UAssetAPI BlankGame and
BpThirdPerson .usmap files. Refuse unknown fields instead of skipping guesses.
"""
import json
import math
from pathlib import Path
from ue5_modern_static import package
from skeletal_mesh_native import require


def fields(r,limit=128):
    """Decode bounded FUnversionedHeader fragments and zero mask."""
    rows=[]; index=0
    for _ in range(limit):
        fragment=r.unpack('H')[0]; index+=fragment&127; count=fragment>>9
        require(index+count<=limit,'Unversioned property index limit')
        rows.extend((i,bool(fragment&128)) for i in range(index,index+count)); index+=count
        if fragment&256: break
    else: raise ValueError('Unterminated unversioned header')
    n=sum(m for _,m in rows); size=0 if n==0 else 1 if n<=8 else 2 if n<=16 else 4*((n+31)//32)
    mask=int.from_bytes(r.take(size),'little'); require(mask>>n==0,'Invalid unversioned zero mask padding')
    out={}; i=0
    for idx,masked in rows:
        out[idx]=masked and bool(mask>>i&1); i+=masked
    return out


def read_instance(path,version):
    require(version in ('5.4','5.6'),'Unsupported cooked material instance profile')
    _,name,names,imports,r,source=package(path,'MaterialInstanceConstant')
    if version=='5.4': require(r.take(4)==bytes(4),'Unsupported UE5.4 material preamble')
    scalar,vector,texture,base,streaming,included=(14,15,17,21,28,26) if version=='5.4' else (20,21,23,29,36,39)
    out=dict(name=name,source_package=source,profile=version,parent=None,parameters=[],streaming=[],base_properties={},shader_status='unresolved_cooked_parent_graph')
    def f32():
        x=r.unpack('f')[0]; require(math.isfinite(x),'Nonfinite material parameter'); return x
    def ref(value,allowed):
        require(-len(imports)<=value<0,'Invalid material parameter reference'); imp=imports[-value-1]; outer=imp[2]
        require(imp[1] in allowed and -len(imports)<=outer<0 and imports[-outer-1][1]=='Package','Invalid material parameter import')
        return imports[-outer-1][3]
    def parameter(kind):
        fs=fields(r); require(set(fs)=={0,1,2} and not fs[0],'Unsupported parameter value layout')
        info=fields(r); require(info=={0:False,1:False,2:False},'Unsupported parameter info layout')
        pname=r.name(names); association=r.unpack('B')[0]; index=r.i()
        require(association in (0,1,2) and -1<=index<4096,'Invalid parameter association')
        if kind=='scalar': value=0.0 if fs[1] else f32()
        elif kind=='vector': value=[0.0]*4 if fs[1] else [f32() for _ in range(4)]
        else:
            ptr=0 if fs[1] else r.i(); value=ref(ptr,('Texture2D',)) if ptr else None
        guid=bytes(16) if fs[2] else r.take(16)
        return dict(name=pname,association=association,index=index,kind=kind,value=value,expression_guid=guid.hex())
    root=fields(r); require(10 in root and not root[10] and set(root)<=set((10,scalar,vector,texture,base,streaming,included)),'Unsupported cooked instance fields')
    for key,zero in root.items():
        if key==10: out['parent']=ref(r.i(),('Material','MaterialInstanceConstant'))
        elif key in (scalar,vector,texture):
            kind={scalar:'scalar',vector:'vector',texture:'texture'}[key]
            if not zero: out['parameters'].extend(parameter(kind) for _ in range(r.count(4096)))
        elif key==included:
            val=0 if zero else r.unpack('B')[0]; require(val in (0,1),'Invalid inclusion flag'); out['included_in_base_game']=bool(val)
        elif key==base:
            if zero: continue
            for i,zero_value in fields(r).items():
                if i==(21 if version=='5.4' else 26): out['base_properties']['OpacityMaskClipValue']=0.0 if zero_value else f32()
                elif version=='5.6' and i==24: out['base_properties']['BlendMode']=0 if zero_value else r.unpack('B')[0]
                else: raise ValueError('Unsupported base property override index')
        elif key==streaming and not zero:
            for _ in range(r.count(4096)):
                fs=fields(r); require(set(fs)=={0,1,2} and not fs[2],'Unsupported material texture streaming info')
                scale=0.0 if fs[0] else f32(); uv=0 if fs[1] else r.i(); texture_name=r.name(names)
                require(0<=uv<8 and scale>=0,'Invalid material texture streaming info')
                out['streaming'].append(dict(texture_name=texture_name,sampling_scale=scale,uv_channel=uv))
    # These fixtures share the bounded non-shader-resource tail. No shader
    # bytecode or parent graph is interpreted here.
    tail=r.take(len(r.data)-r.pos)
    require(tail==bytes.fromhex('000000000000000001000000000300000000'),'Unsupported cooked material native trailer: '+tail.hex())
    identities=[(p['kind'],p['name'],p['association'],p['index']) for p in out['parameters']]
    require(len(set(identities))==len(identities),'Duplicate parameter identity')
    return out


def attach_instance_metadata(material,data):
    """Attach exact source metadata; do not pretend to know shader pin semantics."""
    require(material.get('UE_material_package')==data['source_package'],'Material package identity mismatch')
    material['UE_cooked_instance']=json.dumps(data,sort_keys=True)
    material['UE_material_parent']=data['parent']; material['UE_unresolved_material']=True
    material.use_nodes=True
    # Native parameter controls are deliberately unconnected to the output.
    # The user can connect them to a recovered parent or explicitly authored shader.
    nodes=material.node_tree.nodes; frame=nodes.new('NodeFrame'); frame.label='Source instance parameters — parent graph unresolved'; frame.name='UE Source Instance Parameters'
    for i,p in enumerate(data['parameters']):
        if p['kind']=='scalar': node=nodes.new('ShaderNodeValue'); node.outputs[0].default_value=p['value']
        elif p['kind']=='vector': node=nodes.new('ShaderNodeRGB'); node.outputs[0].default_value=p['value']
        else: node=nodes.new('ShaderNodeTexImage'); node.label=p['name']+' (source texture unresolved)'; node['UE_texture_package']=p['value'] or ''
        node.name='UE Parameter '+str(i); node.label=node.label or p['name']; node.parent=frame; node.location=(0,-i*230); node['UE_parameter_identity']=json.dumps([p['name'],p['association'],p['index']])
    frame.location=(-500,0)


def inspect_material_slots(mesh,project,profile):
    """Resolve source instance parameters automatically where a local package exists."""
    result=[]
    for m in mesh.materials:
        source=m.get('UE_material_package',''); record={'package':source,'status':'unresolved'}
        try:
            path=Path(project.resolve_package(source))
            if not path.is_file(): raise FileNotFoundError('Source material package unavailable')
            cls,_,_,_,_,identity=package(path); require(identity==source,'Serialized source material identity mismatch')
            if cls!='MaterialInstanceConstant': raise NotImplementedError('Cooked parent shader graph is unavailable')
            data=read_instance(path,profile); attach_instance_metadata(m,data)
            record.update(status='parameters_recovered_parent_unresolved',parameters=len(data['parameters']),parent=data['parent'])
        except (ValueError,OSError,NotImplementedError) as exc: record['detail']=str(exc)
        result.append(record)
    return result
