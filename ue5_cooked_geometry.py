"""Bounded UE5.0 unversioned cooked split geometry (Matya profile).
No buffer scanning or UE4 fallback. Property fragment layouts are explicitly
restricted; arbitrary unversioned schemas and Nanite clusters are unsupported.
"""
import math
import struct
from pathlib import Path
from skeleton_native import Reader, MAGIC, reference_skeleton
from skeletal_mesh_native import require, array, assemble


def package(path, kind=None):
    p=Path(path); side=p.with_suffix('.uexp')
    require(p.stat().st_size<=16*1024*1024 and side.stat().st_size<=128*1024*1024,'UE5 package size limit')
    h=p.read_bytes(); data=side.read_bytes(); r=Reader(h)
    require(r.take(4)==MAGIC and r.unpack('6i')==(-8,0,0,0,0,0),'Expected UE5.0 unversioned split header')
    require(r.i()==len(h) and r.string()=='None' and r.unpack('I')==(0x80002200,),'Unsupported UE5 package flags')
    n,no,g,go,ec,eo,ic,io=r.unpack('8i')
    require(0<n<=100000 and g==go==0 and 0<ec<=4096 and 0<ic<=100000 and r.pos<=no<io<eo<len(h) and io+32*ic==eo and eo+108*ec<=len(h),'Invalid UE5 tables')
    r.pos=no; names=[]
    for _ in range(n): names.append(r.string()); r.take(4)
    require(r.pos==io,'Invalid UE5 names extent'); imports=[]
    for _ in range(ic):
        item=(r.name(names),r.name(names),r.i(),r.name(names)); require(r.i()==0,'Unsupported UE5 import flags'); imports.append(item)
    roots=[]; ranges=[]
    for i in range(ec):
        r.pos=eo+i*108; ci,si,ti,outer=r.unpack('4i'); name=r.name(names); r.take(4); size,offset=r.unpack('qq'); start=offset-len(h)
        require(-ic<=ci<0 and 0<=outer<=ec and 0<=start and 0<size<=len(data)-4-start,'Invalid UE5 export extent')
        require(all(start>=b or start+size<=a for a,b in ranges),'Overlapping UE5 exports'); ranges.append((start,start+size))
        if not outer:
            require(imports[-ci-1][:2]==('/Script/CoreUObject','Class'),'Invalid UE5 root class')
            roots.append((imports[-ci-1][3],name,start,size))
    require(len(roots)==1 and data[-4:]==MAGIC and sum(b-a for a,b in ranges)==len(data)-4,'Invalid UE5 sidecar coverage')
    cls,name,start,size=roots[0]; require(kind is None or cls==kind,'Wrong UE5 root class')
    return cls,name,names,imports,Reader(data[start:start+size])


def material_ref(ref,imports):
    if not ref: return None
    require(-len(imports)<=ref<0,'Invalid UE5 material index'); imp=imports[-ref-1]; outer=imp[2]
    require(imp[1]=='Material' and -len(imports)<=outer<0 and imports[-outer-1][1]=='Package','Invalid UE5 material outer')
    return imports[-outer-1][3]


def buffers(r):
    stride,n,stored,vc=r.unpack('IIII'); require(stride==stored==12 and 0<n<=1000000 and vc==n,'Invalid UE5 position buffer')
    positions=list(struct.iter_unpack('<3f',r.take(n*12)))
    strip,uv,vc,full,high=r.unpack('HIIII'); require(strip==1 and 1<=uv<=8 and vc==n and full in (0,1) and high==0,'Unsupported UE5 tangent metadata')
    require(r.unpack('II')==(8,n),'Invalid UE5 tangent buffer'); tangents=[]; normals=[]; signs=[]
    for _ in range(n):
        v=r.unpack('8b'); tangents.append(tuple(max(-1,x/127) for x in v[:3])); normals.append(tuple(max(-1,x/127) for x in v[4:7])); signs.append(max(-1,v[7]/127))
    require(r.unpack('II')==((8 if full else 4),n*uv),'Invalid UE5 UV buffer')
    uvs=[r.unpack(('f' if full else 'e')*(2*uv)) for _ in range(n)]
    require(all(math.isfinite(x) for row in positions+uvs for x in row),'Nonfinite UE5 geometry')
    return positions,normals,tangents,signs,uvs


def read_static50(path):
    _,name,names,imports,r=package(path,'StaticMesh')
    require(r.take(4)==bytes.fromhex('02061103'),'Unsupported UE5 static property fragments')
    # This validated schema has one material, one lightmap-density array and LWC bounds.
    prefix=r.take(100); require(prefix[:6]==bytes.fromhex('010000000009') and prefix[10:22]==bytes.fromhex('010000000000000001000000'),'Unsupported UE5 static property layout')
    prefix_material=material_ref(struct.unpack_from('<i',prefix,6)[0],imports)
    require(all(math.isfinite(v) for v in struct.unpack_from('<7d',prefix,44)),'Invalid UE5 static bounds')
    bulk=Path(path).with_suffix('.ubulk')
    require(bulk.is_file() and bulk.stat().st_size==36 and bulk.read_bytes()==b'\xff'*36,'Missing or unsupported UE5 static bulk payload; no Nanite decoder')
    require(r.unpack('iHi')==(0,1,1),'Unsupported UE5 static native header')
    require(all(0<x<=4096 for x in r.unpack('ii')),'Invalid UE5 collision reference'); r.take(16)
    require(r.unpack('iiH')==(0,1,0x0801),'Unsupported UE5 static LOD flags')
    sections=[]
    for _ in range(r.count(4096)):
        mat,first,tri,low,high,collision,shadow,force,visible=r.unpack('9I')
        require(tri>0 and low<=high and collision in (0,1) and shadow in (0,1) and (force,visible)==(0,1),'Invalid UE5 static section'); sections.append((mat,first,tri,low,high))
    require(r.take(14)==bytes(8)+b'\x01\x00\x00\x00\x01\x08','Unsupported UE5 inline render flags')
    positions,normals,tangents,signs,uvs=buffers(r); n=len(positions)
    require(r.unpack('HII')==(1,0,0),'Unsupported UE5 static color buffer')
    def indices():
        wide,stride,size=r.unpack('III'); require(wide in (0,1) and stride==1 and size<=48000000 and size%(4 if wide else 2)==0,'Invalid UE5 index buffer')
        values=[v[0] for v in struct.iter_unpack('<I' if wide else '<H',r.take(size))]; require(all(i<n for i in values),'UE5 index out of range'); require(r.i()==0,'Unsupported UE5 index trailer'); return values
    idx=indices(); require(indices()==[],'Unsupported UE5 secondary index flags'); indices()
    # Remaining render metadata is a bounded, non-Nanite profile. It is not used as geometry.
    opaque=r.take(669); require(opaque[:40]==bytes.fromhex('0000000001000000')+bytes(32) and struct.unpack_from('<Iiiq',opaque,521)==(0x10501,36,36,0),'Unsupported UE5 static render trailer')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i(); slot=r.name(names); r.take(24); materials.append((slot,material_ref(ref,imports)))
    require(r.pos==len(r.data) and len(materials)==1 and materials[0][1]==prefix_material,'Unexpected UE5 static material table or trailer')
    faces=[]; slots=[]; covered=set()
    for mat,first,tri,low,high in sections:
        require(mat<len(materials) and high<n and first%3==0 and first+tri*3<=len(idx),'Invalid UE5 section extent')
        for j in range(first,first+tri*3,3):
            face=tuple(idx[j:j+3]); require(j not in covered and len(set(face))==3 and all(low<=i<=high for i in face),'Invalid UE5 triangle'); covered.add(j); faces.append(face); slots.append(mat)
    require(len(covered)*3==len(idx),'Incomplete UE5 static coverage')
    return dict(name=name,version='5.0',positions=positions,faces=faces,slots=slots,materials=materials,uvs=uvs,normals=normals,tangents=tangents,signs=signs,colors=None)


def read_skeletal50(path):
    _,name,names,imports,r=package(path,'SkeletalMesh')
    require(r.take(8)==bytes.fromhex('000206020a020803'),'Unsupported UE5 skeletal property fragments')
    # Explicit unversioned schema: fixed single-LOD settings and sampling info.
    prefix=r.take(136)
    for offset,cls in ((0,'Skeleton'),(112,'PhysicsAsset')):
        ref=struct.unpack_from('<i',prefix,offset)[0]
        require(-len(imports)<=ref<0 and imports[-ref-1][1]==cls,'Invalid UE5 skeletal dependency')
    require(r.i()==0 and r.unpack('BB')==(1,0),'Unsupported UE5 skeletal native header')
    require(all(math.isfinite(v) for v in r.unpack('7d')),'Invalid UE5 LWC bounds')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i(); slot=r.name(names); r.take(28); materials.append((slot,material_ref(ref,imports)))
    bones=reference_skeleton(r,names,'d')
    require(r.unpack('IIHII')==(1,1,1,0,1),'Unsupported UE5 skeletal LOD header')
    active=array(r,'H',8192); sections=[]
    for _ in range(r.count(4096)):
        strip,mat,start,tri,flags,shadow,visible,base=r.unpack('HHIQBIIQ')
        require(strip==1 and mat<len(materials) and flags in (0,1,2,3) and shadow in (0,1) and visible in (0,1),'Invalid UE5 skeletal section')
        palette=array(r,'H',256); count,maximum=r.unpack('II')
        require(palette and len(set(palette))==len(palette) and max(palette)<len(bones) and 1<=maximum<=12 and 0<count<=1000000,'Invalid UE5 palette')
        require(r.take(22)==b'\xff\xff'+bytes(16)+b'\xff'*4,'Unsupported UE5 cloth section')
        overlap=array(r,'I',12000000); require(all(i<count for i in overlap),'Invalid UE5 overlap indices')
        require(r.i()==count,'Invalid UE5 overlap count'); r.take(count*8); require(r.i()==0,'Unsupported UE5 section trailer')
        sections.append((mat,start,tri,base,count,palette,maximum))
    required=array(r,'H',8192); require(all(i<len(bones) for i in active+required),'Invalid UE5 active bones')
    length=r.count(128*1024*1024); start=r.pos
    require(r.unpack('H')==(1,),'Invalid UE5 index strip flags')
    width,stride,count=r.unpack('Bii'); require(width==stride and width in (2,4) and 0<count<=12000000,'Invalid UE5 skeletal indices')
    idx=[x[0] for x in struct.iter_unpack('<H' if width==2 else '<I',r.take(count*width))]
    positions,normals,tangents,signs,uvs=buffers(r); n=len(positions)
    strip,variable,influences,total,vc,wide,stride,size=r.unpack('HIIIIIII')
    require(strip==1 and variable==wide==0 and 1<=influences<=12 and total==n*influences and vc==n and stride==1 and size==total*2,'Unsupported UE5 skin weight buffer')
    weights=[r.take(influences*2) for _ in range(n)]
    require(r.unpack('HIII')==(1,0,4,0),'Unsupported UE5 weight lookup')
    require(r.take(12)==bytes(12) and r.pos-start==length,'Invalid UE5 skeletal buffer extent')
    require(r.take(6)==b'\x01\x01'+bytes(4) and r.pos==len(r.data),'Unsupported UE5 skeletal export trailer')
    return assemble(r,name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,None,'5.0')


def read_skeleton50(path):
    _,name,names,imports,r=package(path,'Skeleton')
    require(r.take(2)==b'\x00\x03','Unsupported UE5 skeleton property fragments')
    n=r.count(8192)
    for _ in range(n): require(r.take(3)==b'\x82\x03\x01','Unsupported UE5 BoneTree entry')
    require(r.i()==0,'Unsupported UE5 skeleton GUID flag')
    bones=reference_skeleton(r,names,'d'); require(len(bones)==n,'UE5 BoneTree mismatch')
    require(r.i()==0,'Unsupported UE5 skeleton virtual bones'); r.take(16) # serialized GUID
    require(r.take(18)==b'\x01'+bytes(15)+b'\x01\x00' and r.pos==len(r.data),'Unsupported UE5 skeleton trailer')
    return name,bones
