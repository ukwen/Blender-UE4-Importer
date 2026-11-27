"""Bounded UE5.4/5.5/5.6 cooked fallback render geometry.
Layouts verified on UAssetAPI BlankGame and BpThirdPerson fixtures. No Nanite
cluster decoding, arbitrary property schema, collision, or LOD reconstruction.
"""
import math
import struct
from pathlib import Path
from skeleton_native import Reader, MAGIC
from skeletal_mesh_native import require

PROFILES=('5.4','5.5','5.6')


def package(path, kind=None):
    """Modern split import/export table layout; engine minor is not encoded."""
    p=Path(path); side=p.with_suffix('.uexp')
    require(p.stat().st_size<=16*1024*1024 and side.stat().st_size<=128*1024*1024,'Modern UE5 package size limit')
    h=p.read_bytes(); data=side.read_bytes(); r=Reader(h)
    require(r.take(4)==MAGIC,'Invalid UE5 signature'); legacy=r.i()
    require(legacy in (-8,-9),'Expected modern UE5 split package')
    if legacy==-8:
        require(r.unpack('5i')==(0,0,0,0,0),'Expected unversioned package without custom versions')
        require(r.i()==len(h),'Invalid split header extent')
    else:
        require(r.unpack('4i')==(0,0,0,0),'Expected unversioned package')
        r.take(20) # saved hash, not interpreted as content checksum
        require(r.i()==len(h) and r.i()==0,'Invalid split header extent or custom versions')
    source_package=r.string()
    require(source_package.startswith('/') and all(x not in ('','.','..') for x in source_package[1:].split('/')) and '\\' not in source_package and ':' not in source_package,'Invalid source package identity')
    require(r.unpack('I')==(0x80002200,),'Unsupported modern UE5 package flags')
    n,no,sc,so,g,go,ec,eo,ic,io=r.unpack('10i')
    require(0<n<=100000 and sc==g==go==0 and 0<ec<=4096 and 0<ic<=100000 and r.pos<=no<=so<=io<eo<len(h) and io+32*ic==eo and eo+96*ec<=len(h),'Invalid modern UE5 table extents')
    r.pos=no; names=[]
    for _ in range(n): names.append(r.string()); r.take(4)
    require(r.pos==io and (not so or so==io),'Invalid modern UE5 name extent')
    imports=[]
    for _ in range(ic):
        item=(r.name(names),r.name(names),r.i(),r.name(names)); optional=r.i()
        require(-ic<=item[2]<=ec and optional in (0,1),'Invalid modern UE5 import record'); imports.append(item)
    roots=[]; ranges=[]
    for _ in range(ec):
        ci,si,ti,outer=r.unpack('4i'); name=r.name(names); r.take(4); size,offset=r.unpack('qq'); start=offset-len(h)
        bits=r.unpack('4i'); r.take(4); more=r.unpack('3i'); deps=r.unpack('5i')
        require(all(-ic<=x<=ec for x in (ci,si,ti,outer)) and all(x in (0,1) for x in bits+more),'Invalid modern UE5 export record')
        require(0<=start and 0<=size<=len(data)-4-start and all(start>=b or start+size<=a for a,b in ranges),'Invalid modern UE5 export extent')
        ranges.append((start,start+size))
        if not outer:
            require(-ic<=ci<0 and imports[-ci-1][:2]==('/Script/CoreUObject','Class'),'Unsupported modern UE5 root class')
            roots.append((imports[-ci-1][3],name,start,size))
    require(len(roots)==1 and data[-4:]==MAGIC and sum(b-a for a,b in ranges)==len(data)-4,'Invalid modern UE5 sidecar coverage')
    cls,name,start,size=roots[0]; require(kind is None or cls==kind,'Wrong modern UE5 root class')
    return cls,name,names,imports,Reader(data[start:start+size]),source_package


def material_ref(ref,imports):
    require(-len(imports)<=ref<0,'Invalid modern material reference'); imp=imports[-ref-1]; outer=imp[2]
    require(imp[1] in ('Material','MaterialInstanceConstant') and -len(imports)<=outer<0 and imports[-outer-1][1]=='Package','Invalid modern material outer')
    return imports[-outer-1][3]


def read_static_modern(path,version):
    require(version in PROFILES,'Unsupported modern static profile')
    _,name,names,imports,r,source=package(path,'StaticMesh')
    # Explicit fragment layouts; opaque fixed-schema properties are skipped by
    # their verified extents, never located by scanning for a vertex signature.
    prefix_len,signature,count,refs,strip,mat_stride={
        '5.4':(116,bytes.fromhex('0000000002081003'),1,(14,),0x0805,36),
        '5.5':(106,bytes.fromhex('03041503'),2,(10,40),5,36),
        '5.6':(109,bytes.fromhex('03061403'),1,(11,),5,40),
    }[version]
    prefix=r.take(prefix_len); require(prefix.startswith(signature),'Unsupported modern static property fragments')
    # The native material table is authoritative; cross-check references from
    # the property prefix, including distinct numbered imports of one package.
    prefix_refs=[struct.unpack_from('<i',prefix,o)[0] for o in refs]
    for ref in prefix_refs: material_ref(ref,imports)
    require(all(math.isfinite(x) for x in struct.unpack_from('<7d',prefix,prefix_len-56)),'Invalid source bounds')
    require(r.unpack('iHi')==(0,5,1),'Invalid modern static native header')
    require(r.unpack('ii')==(1,2),'Unsupported collision reference layout'); r.take(16)
    require(r.unpack('iiH')==(0,1,strip),'Unsupported modern LOD flags')
    sections=[]
    for _ in range(r.count(4096)):
        mat,first,tri,low,high,collision,shadow,force,visible=r.unpack('9I')
        require(tri>0 and low<=high and collision in (0,1) and shadow in (0,1) and force in (0,1) and visible in (0,1),'Invalid modern static section')
        if version!='5.4': require(r.i() in (0,1),'Invalid raytracing section flag')
        sections.append((mat,first,tri,low,high))
    if version=='5.6': require(all(math.isfinite(x) for x in r.unpack('7d')),'Invalid LOD bounds')
    inline=r.take(18)
    expected=bytes.fromhex('010000000000000000000000010000000508') if version=='5.4' else bytes.fromhex('000000000000000001000000000000000500')
    require(inline==expected,'Unsupported inline LOD serialization')
    stride,n,stored,vc=r.unpack('4I'); require(stride==stored==12 and 0<n<=1000000 and vc==n,'Invalid modern position buffer')
    positions=list(struct.iter_unpack('<3f',r.take(n*12)))
    strip,uv,vc,full,high,stride,stored=r.unpack('H6I')
    require(strip==5 and 1<=uv<=8 and vc==stored==n and full in (0,1) and high==0 and stride==8,'Unsupported modern tangent metadata')
    normals=[]; tangents=[]; signs=[]
    for _ in range(n):
        row=r.unpack('8b'); tangents.append(tuple(max(-1,x/127) for x in row[:3])); normals.append(tuple(max(-1,x/127) for x in row[4:7])); signs.append(max(-1,row[7]/127))
    require(r.unpack('II')==((8 if full else 4),n*uv),'Invalid modern UV buffer')
    uvs=[r.unpack(('f' if full else 'e')*(2*uv)) for _ in range(n)]
    require(all(math.isfinite(x) for row in positions+uvs for x in row),'Nonfinite modern geometry')
    require(r.unpack('HII')==(5,0,0),'Unsupported modern vertex color buffer')
    def indices():
        wide,stride,size=r.unpack('III'); width=4 if wide else 2
        require(wide in (0,1) and stride==1 and size<=48000000 and size%width==0,'Invalid modern index buffer')
        values=[v[0] for v in struct.iter_unpack('<I' if wide else '<H',r.take(size))]
        require(all(i<n for i in values) and r.i()==0,'Invalid modern index value or trailer'); return values
    idx=indices()
    for _ in range(3): indices()
    # Native tail contains Nanite/RT metadata and bounds; do not decode or
    # pretend to reconstruct it. Bound the skip by the known material count
    # and fixed entry size. Verify the serialized count and source references.
    tail=len(r.data)-r.pos-4-count*mat_stride
    require(32<=tail<=32*1024*1024,'Invalid modern static tail extent'); r.take(tail)
    require(r.i()==count,'Modern material count mismatch'); materials=[]; native_refs=[]
    for _ in range(count):
        ref=r.i(); native_refs.append(ref); slot=r.name(names); r.take(mat_stride-12); materials.append((slot,material_ref(ref,imports)))
    require(r.pos==len(r.data) and native_refs==prefix_refs,'Modern material binding mismatch')
    faces=[]; slots=[]; covered=set()
    for mat,first,tri,low,high in sections:
        require(mat<len(materials) and high<n and first%3==0 and first+3*tri<=len(idx),'Invalid modern section extent')
        for j in range(first,first+3*tri,3):
            face=tuple(idx[j:j+3]); require(j not in covered and len(set(face))==3 and all(low<=i<=high for i in face),'Invalid modern triangle'); covered.add(j); faces.append(face); slots.append(mat)
    require(len(covered)*3==len(idx),'Incomplete modern triangle coverage')
    bulk=Path(path).with_suffix('.ubulk')
    return dict(name=name,version=version,positions=positions,faces=faces,slots=slots,materials=materials,uvs=uvs,normals=normals,tangents=tangents,signs=signs,colors=None,source_package=source,geometry_scope='inline fallback render geometry; Nanite and collision not reconstructed',external_bulk_bytes=bulk.stat().st_size if bulk.is_file() else 0)
