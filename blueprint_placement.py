"""Bounded direct-child Character CDO body placement. No construction scripts."""
import math
from pathlib import Path
from package_inspector import inspect_package
from skeleton_native import Reader

FIELDS={'RelativeLocation':'Vector','RelativeRotation':'Rotator','RelativeScale3D':'Vector'}
ABSOLUTE=('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')

def check(ok,message):
    if not ok: raise ValueError(message)

def transform4(p):
    out={}
    for k,kind in FIELDS.items():
        if k in p:
            prop=p[k]; v=prop.value
            check(prop.type=='StructProperty' and prop.struct_type==kind and prop.len==12,'Invalid transform '+k)
            out[k]=(v.x,v.y,v.z)
    for k in ABSOLUTE:
        if k in p:
            check(p[k].type=='BoolProperty' and not p[k].value,'Absolute transform unsupported')
    return out

def props5(raw,e,names):
    r=Reader(raw[e['offset']+e['script_start']:e['offset']+e['script_end']]); out={}
    check(r.unpack('B')[0]==0,'Unsupported class serialization control')
    while True:
        key=r.name(names)
        if key=='None':
            check(r.pos==len(r.data),'Unexpected property trailer'); return out
        nodes=[]; remaining=1
        while remaining:
            typ,n=r.name(names),r.count(64); nodes.append(typ); remaining+=n-1
            check(len(nodes)+remaining<=128,'Oversized type tree')
        size=r.i(); flags=r.unpack('B')[0]; check(size>=0 and not flags&~0x3f,'Invalid property tag')
        idx=r.i() if flags&1 else 0
        if flags&2:r.take(16)
        if flags&4:
            ext=r.unpack('B')[0]; check(not ext&~2,'Unsupported property extension')
            if ext&2:r.take(5)
        payload=Reader(r.take(size)); check(idx==0 and key not in out,'Repeated property unsupported')
        if key in FIELDS:
            check(nodes==['StructProperty',FIELDS[key],'/Script/CoreUObject'] and size==24 and not flags&0x20,'Unsupported UE5 transform '+key)
            out[key]=payload.unpack('3d')
        elif key in ABSOLUTE:
            raise ValueError('Explicit UE5 absolute flag unsupported')
        elif nodes==['ObjectProperty'] and size==4 and not flags&0x28: out[key]=payload.i()
        else: out[key]=None

def package4(a,i):
    seen=set()
    while i<0:
        check(i not in seen and -i<=len(a.imports),'Invalid import chain'); seen.add(i); v=a.GetImport(i)
        if v.class_name=='Package' and v.object_name.startswith(('/Game/','/Engine/','/Script/')):return v.object_name
        i=v.outer_index
    return ''

def template(path,class_name):
    """Read explicit Mesh, CapsuleComponent and RootComponent CDO associations."""
    path=Path(path); meta=inspect_package(path)
    check(meta.get('status')=='tables_inspected' and meta['ue4']==522 and not meta['sidecars'] and not meta['flags']&0x80002000,'Unsupported Blueprint package')
    if meta['ue5'] is not None:
        check(meta['ue5']==1012,'Blueprint placement requires verified UE5 1012 property layout')
        from ue5_blueprint import read_tables
        meta,raw,im,ex,ref,pkg=read_tables(path); names=meta['names']
        ci,cls=unique([(i,e) for i,e in enumerate(ex,1) if e['outer']==0 and e['kind']=='BlueprintGeneratedClass' and e['name']==class_name])
        di,cdo=unique([(i,e) for i,e in enumerate(ex,1) if e['class_index']==ci and e['outer']==0 and e['name']=='Default__'+class_name])
        p=props5(raw,cdo,names); mi,ri=p['Mesh'],p['RootComponent']; check(type(mi) is int and type(ri) is int and mi>0 and ri>0 and p['CapsuleComponent']==ri,'Invalid CDO associations')
        m,root=ref(mi),ref(ri); check(m['outer']==root['outer']==di and m['kind']=='SkeletalMeshComponent' and root['kind']=='CapsuleComponent','Invalid CDO component types')
        mp,rp=props5(raw,m,names),props5(raw,root,names); check(mp.get('AttachParent')==ri and 'AttachParent' not in rp and 'AttachSocketName' not in mp,'Unsupported CDO attachment')
        si=cls['super_index']; check(si<0,'Unsupported parent class'); parent=ref(si)['name']; parent_package=pkg(si)
        return dict(mesh=m['name'],root=root['name'],parent_class=parent,parent_package=parent_package,mesh_fields={k:mp[k] for k in FIELDS if k in mp},root_fields={k:rp[k] for k in FIELDS if k in rp})
    from classic_blueprint import BlueprintRecords
    return BlueprintRecords(path,class_name).body_template()

def unique(items):
    check(len(items)==1,'Expected one explicit class or CDO'); return items[0]

def resolve_body(project,actor,component,root,package,cache):
    """Merge native Character defaults, one parent Blueprint, child, map overrides."""
    check(actor.properties.TryGetValue('Mesh') is component and actor.properties.TryGetValue('RootComponent') is root and actor.properties.TryGetValue('CapsuleComponent') is root,'Map body/root association unavailable')
    check(component.properties.TryGetValue('AttachParent') is root and not root.properties.TryGetValue('AttachParent') and component.properties.TryGetValue('AttachSocketName','None')=='None','Unsupported map attachment')
    def load(pkg,name):
        key=(pkg,name)
        if key not in cache:cache[key]=template(project.resolve_package(pkg),name)
        return cache[key]
    child=load(package,actor.export_class_type)
    check(child['parent_package'].startswith('/Game/') and child['parent_class'].endswith('_C'),'Expected explicit parent Blueprint')
    parent=load(child['parent_package'],child['parent_class'])
    check(parent['parent_class']=='Character' and parent['parent_package']=='/Script/Engine','Parent must derive directly from native Character')
    check(child['mesh']==parent['mesh']==component.object_name and child['root']==parent['root']==root.object_name,'Component template association mismatch')
    def merge(base,child,instance):
        result={'RelativeLocation':(0.,0.,0.),'RelativeRotation':(0.,0.,0.),'RelativeScale3D':(1.,1.,1.)}; result.update(base);result.update(child);result.update(transform4(instance))
        check(all(math.isfinite(v) for row in result.values() for v in row) and min(result['RelativeScale3D'])>0,'Invalid component transform');return result
    return dict(parent=child['parent_package'],mesh=merge(parent['mesh_fields'],child['mesh_fields'],component.properties),root=merge(parent['root_fields'],child['root_fields'],root.properties))

def apply_fields(obj,fields):
    from mathutils import Euler
    t=fields['RelativeLocation']; p,y,r=fields['RelativeRotation']; s=fields['RelativeScale3D']
    obj.location=(t[1]*.01,t[0]*.01,t[2]*.01); obj.rotation_mode='YXZ'; obj.rotation_euler=Euler(tuple(math.radians(v) for v in (p,r,-y)),'YXZ');obj.scale=(s[1],s[0],s[2])

def place_body(root_node,mesh_node,rig,placement):
    """Apply the resolved body placement to the existing map anchor hierarchy."""
    from mathutils import Matrix
    check(root_node.parent is None and mesh_node.parent==root_node and rig.type=='ARMATURE','Unexpected level anchor hierarchy')
    apply_fields(root_node,placement['root']);apply_fields(mesh_node,placement['mesh'])
    rig.parent=mesh_node;rig.matrix_parent_inverse=Matrix.Identity(4);rig.matrix_basis=Matrix.Identity(4)
    for node in (root_node,mesh_node):
        node['UE_blueprint_defaults_unresolved']=False;node['UE_body_placement']='serialized_parent_child_map';node['UE_parent_blueprint']=placement['parent']


def body_sockets(rig,records,collection):
    from native_sockets import create_socket_anchors
    present=[r for r in records if r['bone'] in rig.data.bones]
    missing=[r['name'] for r in records if r['bone'] not in rig.data.bones]
    anchors=create_socket_anchors(rig,present,collection) if present else []
    return {'created':len(anchors),'missing_bone_sockets':missing}
