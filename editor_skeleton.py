"""Versioned UE4.27 editor USkeleton reference bones and explicit socket array."""
import math
from pathlib import Path
from animation_native import read_tagged_properties, require
from skeleton_native import Reader


def read_editor_skeleton(path):
    from package_records import read_editor522, root_export
    _, raw, table = read_editor522(path, 64*1024*1024)
    e = root_export(table,'Skeleton')
    def reader(record):
        require(record.size>0,'Empty skeleton export')
        return Reader(raw[record.offset:record.offset+record.size])
    r=reader(e); tags,kinds=read_tagged_properties(r,table.names); require(r.i()==0,'Unsupported skeleton object GUID')
    n=r.count(8192); require(n>0,'Empty skeleton'); bones=[]; seen=set()
    for i in range(n):
        name,parent=r.name(table.names),r.i(); r.string()
        require(name.casefold() not in seen and len(name.encode())<=63 and parent in ([-1] if i==0 else range(i)),'Invalid reference bone'); seen.add(name.casefold()); bones.append(dict(name=name,parent=parent))
    require(r.i()==n,'Reference pose count mismatch')
    for b in bones:
        q,t,s=r.unpack('4f'),r.unpack('3f'),r.unpack('3f'); require(all(math.isfinite(v) for v in q+t+s) and abs(sum(v*v for v in q)-1)<.001 and min(s)>0,'Invalid reference transform'); b.update(rotation=q,translation=t,scale=s)
    require(r.i()==n,'Bone map count mismatch'); seen=set()
    for _ in range(n):
        name,i=r.name(table.names),r.i(); require(0<=i<n and i not in seen and name==bones[i]['name'],'Invalid bone map'); seen.add(i)
    sockets=[]; seen=set()
    if 'Sockets' in tags:
        require(kinds['Sockets']==('ArrayProperty','ObjectProperty'),'Unsupported socket array'); sr=Reader(tags['Sockets']); count=sr.count(8192)
        for _ in range(count):
            i=sr.i(); require(0<i<=len(table.exports),'Invalid socket reference'); se=table.exports[i-1]; require(se.kind=='SkeletalMeshSocket' and se.outer==table.exports.index(e)+1,'Invalid socket owner')
            rr=reader(se); st,sk=read_tagged_properties(rr,table.names); require(rr.i()==0 and rr.pos==len(rr.data),'Unsupported socket trailer')
            def name(key):
                require(sk.get(key)==('NameProperty',None) and len(st[key])==8,'Invalid socket name'); return Reader(st[key]).name(table.names)
            def vec(key,kind,default):
                if key not in st:return default
                require(sk[key]==('StructProperty',kind) and len(st[key])==12,'Invalid socket transform'); v=Reader(st[key]).unpack('3f'); require(all(math.isfinite(x) for x in v),'Invalid socket value'); return v
            sn,bn=name('SocketName'),name('BoneName'); require(sn not in seen and bn in {b['name'] for b in bones},'Invalid socket association'); seen.add(sn)
            sockets.append(dict(name=sn,bone=bn,location_cm=vec('RelativeLocation','Vector',(0.,0.,0.)),rotation_pyr=vec('RelativeRotation','Rotator',(0.,0.,0.)),scale=vec('RelativeScale','Vector',(1.,1.,1.))))
        require(sr.pos==len(sr.data),'Invalid socket array extent')
    return dict(name=e.name,bones=bones,sockets=sockets,tail_bytes=len(r.data)-r.pos)
