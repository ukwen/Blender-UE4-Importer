"""Bounded UE5.6 Quinn-style cooked skeletal render LODs; no cloth or variable weights."""
import math
import struct
from skeleton_native import Reader, reference_skeleton
from skeletal_mesh_native import array, assemble, require
from ue5_modern_static import package, material_ref


def read_skeletal56(path, lod=0):
    require(isinstance(lod,int) and 0<=lod<3,'Unsupported UE5.6 LOD selection')
    return read_skeletal56_all(path)[lod]


def read_skeletal56_all(path):
    """Validate every native render LOD once before creating Blender data."""
    _,name,names,imports,r,source=package(path,'SkeletalMesh')
    require(r.take(10)==bytes.fromhex('00020602010206020903'),'Unsupported UE5.6 skeletal property fragments')
    ref=r.i(); require(-len(imports)<=ref<0 and imports[-ref-1][1]=='Skeleton','Invalid skeleton reference')
    outer=imports[-ref-1][2]; require(-len(imports)<=outer<0 and imports[-outer-1][1]=='Package','Invalid skeleton package')
    skeleton_package=imports[-outer-1][3]
    require(r.i()==3,'Unsupported UE5.6 skeletal property LOD count'); r.take(448)
    require(r.unpack('iBB')==(0,5,0),'Unsupported UE5.6 skeletal native header')
    require(all(math.isfinite(v) for v in r.unpack('7d')),'Invalid skeletal bounds')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i(); slot=r.name(names); r.take(32); materials.append((slot,material_ref(ref,imports)))
    require(materials,'Missing skeletal material table')
    bones=reference_skeleton(r,names,'d')
    flag,count=r.unpack('II'); require(flag==1 and count==3,'Unsupported UE5.6 LOD selection')
    results=[]
    for i in range(count):
        require(r.unpack('HII')==(5,0,1),'Unsupported UE5.6 inline LOD flags')
        active=array(r,'H',8192); sections=[]
        for _ in range(r.count(4096)):
            strip,mat,start,tri,flags,shadow,visible,base=r.unpack('HHIQBIIQ')
            require(strip==261 and mat<len(materials) and tri>0 and start%3==0 and flags==3 and shadow in (0,1) and visible in (0,1),'Unsupported UE5.6 section flags')
            palette=array(r,'H',256); vc,maximum=r.unpack('II')
            require(palette and len(set(palette))==len(palette) and max(palette)<len(bones) and 1<=maximum<=8 and 0<vc<=1000000,'Invalid skeletal palette')
            require(r.take(22)==b'\xff\xff'+bytes(16)+b'\xff'*4 and r.i()==0,'Unsupported UE5.6 cloth/overlap data')
            sections.append((mat,start,tri,base,vc,palette,maximum))
        required=array(r,'H',8192)
        require(active and required and all(j<len(bones) for j in active+required),'Invalid active/required bones')
        length=r.count(128*1024*1024); buffer=Reader(r.take(length))
        data=_lod(buffer,name,bones,materials,sections)
        data.update(source_package=source,skeleton_package=skeleton_package,lod_index=i,lod_count=count,geometry_scope='native inline skeletal render LOD; cloth and ray tracing not reconstructed',external_bulk_bytes=0)
        results.append(data)
    require(r.take(96)==b'\x05'+bytes(89)+b'\x03\x03'+bytes(4) and r.pos==len(r.data),'Unsupported UE5.6 skeletal export trailer')
    summary=[{'vertices':len(x['positions']),'triangles':len(x['faces'])} for x in results]
    for result in results: result['lod_summary']=summary
    return results


def _lod(r,name,bones,materials,sections):
    strip,width,stride,ic=r.unpack('HBii'); require(strip==5 and width==stride and width in (2,4) and 0<ic<=12000000,'Invalid skeletal indices')
    idx=[x[0] for x in struct.iter_unpack('<H' if width==2 else '<I',r.take(ic*width))]
    stride,n,stored,vc=r.unpack('4I');require(stride==stored==12 and 0<n<=1000000 and vc==n,'Invalid skeletal positions')
    positions=list(struct.iter_unpack('<3f',r.take(n*12)))
    strip,uv,vc,full,high,stride,stored=r.unpack('H6I')
    require(strip==5 and 1<=uv<=8 and vc==stored==n and full in (0,1) and high==0 and stride==8,'Invalid skeletal tangent data')
    normals=[]; tangents=[]; signs=[]
    for row in struct.iter_unpack('<8b',r.take(n*8)):
        tangents.append(tuple(max(-1,x/127) for x in row[:3]));normals.append(tuple(max(-1,x/127) for x in row[4:7]));signs.append(max(-1,row[7]/127))
    require(r.unpack('II')==((8 if full else 4),n*uv),'Invalid skeletal UV data')
    uvs=[r.unpack(('f' if full else 'e')*(2*uv)) for _ in range(n)]
    require(all(math.isfinite(x) for row in positions+uvs for x in row),'Nonfinite skeletal geometry')
    strip,variable,influences,total,vc,wide,wide_weight,stride,size=r.unpack('H8I')
    require(strip==5 and variable==wide==wide_weight==0 and influences in (4,8) and total==n*influences and vc==n and stride==1 and size==total*2,'Unsupported UE5.6 weight layout')
    weights=[r.take(influences*2) for _ in range(n)]
    require(r.unpack('HIII')==(5,0,4,0),'Unsupported skeletal weight lookup')
    # Bounded empty/opaque cloth, vertex-color, raytracing trailer in this profile.
    require(r.take(54)==bytes(4)+b'\xff'*24+b'\x01'+bytes(15)+b'\x05'+bytes(9) and r.pos==len(r.data),'Unsupported UE5.6 LOD trailer')
    return assemble(r,name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,None,'5.6')
