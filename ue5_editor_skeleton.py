"""Bounded UE5.6 editor USkeleton native reference pose, sockets and retarget sources."""
import math
from pathlib import Path
from skeleton_native import Reader
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_dependencies import read_dependencies


def checked_transform(values):
    q,t,s=values[:4],values[4:7],values[7:10]
    require(all(math.isfinite(x) for x in values) and abs(sum(x*x for x in q)-1)<.001 and min(s)>0,'Invalid reference transform')
    return dict(rotation=q,translation=t,scale=s)


def read_skeleton(path):
    path=Path(path);m,b,im,ex,ref,pkg=read_tables(path);names=m['names'];require(m['ue5']==1017,'Expected UE5.6 editor skeleton profile')
    roots=[i for i,e in enumerate(ex,1) if not e['outer'] and e['kind']=='Skeleton'];require(len(roots)==1,'Expected one root skeleton');root=roots[0];e=ref(root);t=export_tags(b,e,names)
    r=Reader(b[e['offset']+e['script_end']:e['offset']+e['size']]);require(r.i()==0,'Unexpected skeleton GUID flag');n=r.count(8192);require(n>0,'Empty skeleton');bones=[];seen=set()
    for i in range(n):
        name,parent,export_name=r.name(names),r.i(),r.string();require(name and name==export_name and len(name.encode())<=63 and name.casefold() not in seen and parent in ([-1] if i==0 else range(i)),'Invalid editor bone identity');seen.add(name.casefold());bones.append(dict(name=name,parent=parent))
    require(r.i()==n,'Reference pose count mismatch')
    for bone in bones:bone.update(checked_transform(r.unpack('10d')))
    require(r.i()==n,'Bone map count mismatch');seen=set()
    for _ in range(n):
        name,i=r.name(names),r.i();require(0<=i<n and i not in seen and name==bones[i]['name'],'Invalid bone map');seen.add(i)
    soft=read_dependencies(path)['soft_object_paths'];retarget={}
    for _ in range(r.count(256)):
        key,name=r.name(names),r.name(names);require(key==name and name not in retarget,'Invalid retarget pose identity');require(r.i()==n,'Retarget pose count mismatch');pose=[checked_transform(r.unpack('10d')) for _ in range(n)];i=r.i();require(0<=i<len(soft) and soft[i]['package'] and not soft[i]['subpath'],'Invalid retarget source asset');retarget[name]=dict(asset=soft[i],pose=pose)
    # Later native skeleton data contains runtime retarget modes and other tables;
    # do not interpret it as transforms or claim complete USkeleton evaluation.
    sockets=[];seen=set();bone_names={x['name'] for x in bones}
    if 'Sockets' in t:
        v=t['Sockets'];require(v['type']==['ArrayProperty','ObjectProperty'],'Invalid socket array');sr=Reader(v['data'])
        for _ in range(sr.count(8192)):
            i=sr.i();require(0<i<=len(ex) and ref(i)['kind']=='SkeletalMeshSocket' and ref(i)['outer']==root,'Invalid socket ownership');st=export_tags(b,ref(i),names)
            def name(k):
                v=st[k];require(v['type']==['NameProperty'] and len(v['data'])==8,'Invalid socket name');return Reader(v['data']).name(names)
            def vec(k,kind,default):
                if k not in st:return default
                v=st[k];require(v['type']==['StructProperty',kind,'/Script/CoreUObject'] and len(v['data'])==24,'Invalid socket transform');x=Reader(v['data']).unpack('3d');require(all(math.isfinite(a) for a in x),'Invalid socket transform');return x
            sn,bn=name('SocketName'),name('BoneName');require(sn not in seen and bn in bone_names,'Invalid socket association');seen.add(sn);sockets.append(dict(name=sn,bone=bn,location_cm=vec('RelativeLocation','Vector',(0.,0.,0.)),rotation_pyr=vec('RelativeRotation','Rotator',(0.,0.,0.)),scale=vec('RelativeScale','Vector',(1.,1.,1.))))
        require(sr.pos==len(sr.data),'Invalid socket array extent')
    identity=''
    for parent in path.resolve().parents:
        if parent.name=='Content' and len(list(parent.parent.glob('*.uproject')))==1:
            from project_preflight import package_id
            identity=package_id(path.resolve(),parent);break
    return dict(name=e['name'],bones=bones,sockets=sockets,retarget_sources=retarget,skeleton_package=identity,tail_bytes=len(r.data)-r.pos)
