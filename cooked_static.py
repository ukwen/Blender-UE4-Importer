"""Bounded tagged UE4.18/4.27 inline cooked static render geometry."""
import math,struct
from pathlib import Path
from skeleton_native import Reader,MAGIC
from skeletal_mesh_native import require


def read_static(path,version):
    if version=="5.0":
        from ue5_cooked_geometry import read_static50
        return read_static50(path)
    require(version in ('4.18','4.27'),'Unsupported cooked static profile')
    p=Path(path); side=p.with_suffix('.uexp')
    require(p.stat().st_size<=16*1024*1024 and side.stat().st_size<=128*1024*1024,'Package size limit')
    header=p.read_bytes(); data=side.read_bytes(); r=Reader(header)
    require(r.take(4)==MAGIC and r.unpack('5i')==(-7,0,0,0,0),'Unsupported package header')
    require(r.i()==len(header) and r.string()=='None','Invalid split header')
    flags=r.unpack('I')[0]; require(flags&0x80000000 and not flags&0x2000,'Expected tagged editor-filtered package')
    n,no,g,go,ec,eo,ic,io=r.unpack('8i')
    require(0<n<=100000 and g==go==0 and 1<=ec<=4096 and 0<ic<=100000 and r.pos<=no<io<eo<len(header) and io+28*ic==eo and eo+104*ec<=len(header),'Invalid tables')
    r.pos=no; names=[]
    for _ in range(n): names.append(r.string()); r.take(4)
    require(r.pos==io,'Invalid name table')
    imports=[(r.name(names),r.name(names),r.i(),r.name(names)) for _ in range(ic)]
    roots=[]
    for i in range(ec):
        r.pos=eo+104*i; ci,si,ti,outer=r.unpack('4i'); name=r.name(names); r.take(4); size,offset=r.unpack('qq')
        require(-ic<=ci<0 and len(header)<=offset and 0<size<=len(data)-4-(offset-len(header)),'Invalid export extent')
        if outer==0 and imports[-ci-1][:2]==('/Script/CoreUObject','Class') and imports[-ci-1][3]=='StaticMesh': roots.append((name,offset-len(header),size))
    require(len(roots)==1 and data[-4:]==MAGIC,'Expected root StaticMesh export')
    name,start,size=roots[0]; r=Reader(data[start:start+size]); seen=set()
    tags={'StaticMaterials':('ArrayProperty','StructProperty'),'LightmapUVDensity':('FloatProperty',None),'LightMapResolution':('IntProperty',None),'ExtendedBounds':('StructProperty','BoxSphereBounds')}
    while True:
        k=r.name(names)
        if k=='None': break
        typ=r.name(names); sz,idx=r.unpack('ii'); require(k not in seen and k in tags and idx==0 and sz>=0 and tags[k][0]==typ,'Unsupported static tag: '+k); seen.add(k)
        if tags[k][1]: require(r.name(names)==tags[k][1],'Invalid inner property type')
        if typ=='StructProperty': r.take(16)
        require(r.take(1)==b'\0','Unsupported property GUID'); r.take(sz)
    require(r.unpack('iHi')==(0,1,1),'Unsupported cooked header')
    body,nav=r.unpack('ii'); require(0<=body<=ec and 0<=nav<=ec,'Invalid collision references'); r.take(16)
    require(r.unpack('ii')==(0,1),'Only one inline LOD without sockets supported')
    require(r.unpack('BB')==(1,8 if version=='4.27' else 0),'Unsupported render strip flags')
    sections=[]
    for _ in range(r.count(4096)):
        mat,first,tri,low,high,collision,shadow=r.unpack('7I')
        require(collision in (0,1) and shadow in (0,1) and tri>0 and low<=high,'Invalid render section')
        if version=='4.27': require(r.unpack('II')==(0,1),'Unsupported 4.27 section flags')
        sections.append((mat,first,tri,low,high))
    require(r.take(14 if version=='4.27' else 4)==(bytes(8)+b'\x01\x00\x00\x00\x01\x08' if version=='4.27' else bytes(4)),'Unsupported inline render flags')
    stride,n,stored,vc=r.unpack('IIII'); require(stride==stored==12 and 0<n<=1000000 and vc==n,'Invalid position buffer')
    positions=list(struct.iter_unpack('<3f',r.take(n*12)))
    tangents=[]; normals=[]; signs=[]; uvs=[]
    if version=='4.18':
        strip,uv,stride,vc,full,high,stored,count=r.unpack('H7I')
        require(strip==1 and 1<=uv<=8 and vc==count==n and full in (0,1) and high==0 and stride==stored==8+uv*(8 if full else 4),'Unsupported interleaved buffer')
        for _ in range(n):
            row=r.unpack('8B'+('f' if full else 'e')*(2*uv)); tangents.append(tuple(x/127.5-1 for x in row[:3])); normals.append(tuple(x/127.5-1 for x in row[4:7])); signs.append(row[7]/127.5-1); uvs.append(row[8:])
    else:
        strip,uv,vc,full,high,stride,count=r.unpack('H6I'); require(strip==1 and 1<=uv<=8 and vc==count==n and full in (0,1) and high==0 and stride==8,'Unsupported separate buffer')
        for _ in range(n):
            row=r.unpack('8b'); tangents.append(tuple(max(-1,x/127) for x in row[:3])); normals.append(tuple(max(-1,x/127) for x in row[4:7])); signs.append(max(-1,row[7]/127))
        require(r.unpack('II')==((8 if full else 4),n*uv),'Invalid UV buffer'); uvs=[r.unpack(('f' if full else 'e')*(2*uv)) for _ in range(n)]
    require(all(math.isfinite(x) for row in positions+uvs for x in row),'Nonfinite geometry')
    strip,stride,count=r.unpack('HII'); require(strip==1 and stride in (0,4) and count==(n if stride else 0),'Unsupported color buffer'); colors=None
    if stride:
        require(r.unpack('II')==(4,n),'Invalid color buffer'); colors=[r.unpack('4B') for _ in range(n)]
    def indices():
        wide,stride,count=r.unpack('III'); require(wide in (0,1) and stride==1 and count<=48000000 and count%(4 if wide else 2)==0,'Invalid index buffer')
        out=[x[0] for x in struct.iter_unpack('<I' if wide else '<H',r.take(count))]
        require(all(i<n for i in out),'Index out of range')
        if version=='4.27': require(r.i()==0,'Unsupported index trailer')
        return out
    idx=indices()
    for _ in range(4): indices()
    # Bounded profile: retain but do not interpret render metadata between the
    # index arrays and native material table. Exact extent is profile-specific.
    opaque=r.take(147 if version=='4.27' else 98)
    require(opaque[:24]==bytes(24),'Unsupported LOD trailer')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i(); slot=r.name(names); package=None
        if ref:
            require(-ic<=ref<0,'Invalid material reference'); outer=imports[-ref-1][2]
            require(-ic<=outer<0 and imports[-outer-1][1]=='Package','Invalid material outer'); package=imports[-outer-1][3]
        r.take(24); materials.append((slot,package))
    require(r.pos==len(r.data),'Unexpected static export trailer')
    faces=[]; slots=[]; covered=set()
    for mat,first,tri,low,high in sections:
        require(mat<len(materials) and high<n and first%3==0 and first+3*tri<=len(idx),'Invalid section extent')
        for j in range(first,first+3*tri,3):
            face=tuple(idx[j:j+3]); require(j not in covered and len(set(face))==3 and all(low<=i<=high for i in face),'Invalid triangle'); covered.add(j); faces.append(face); slots.append(mat)
    require(len(covered)*3==len(idx),'Incomplete section coverage')
    return dict(name=name,version=version,positions=positions,faces=faces,slots=slots,materials=materials,uvs=uvs,normals=normals,tangents=tangents,signs=signs,colors=colors)


def build_static(data):
    import bpy,json
    mesh=bpy.data.meshes.new(data['name']); mats=[]
    try:
        mesh.from_pydata([(y*.01,x*.01,z*.01) for x,y,z in data['positions']],[],data['faces']); mesh.update()
        require(not mesh.validate(clean_customdata=False),'Invalid mesh topology')
        for name,package in data['materials']:
            mat=bpy.data.materials.new(name); mats.append(mat); mat['UE_unresolved_material']=True
            if package: mat['UE_material_package']=package
            mesh.materials.append(mat)
        for poly,slot in zip(mesh.polygons,data['slots']): poly.material_index=slot; poly.use_smooth=True
        for i in range(len(data['uvs'][0])//2):
            uv=mesh.uv_layers.new(name=f'UV{i}'); uv.data.foreach_set('uv',[x for loop in mesh.loops for x in (data['uvs'][loop.vertex_index][2*i],1-data['uvs'][loop.vertex_index][2*i+1])])
        mesh.normals_split_custom_set([(y,x,z) for x,y,z in (data['normals'][l.vertex_index] for l in mesh.loops)])
        a=mesh.attributes.new('UE_source_tangent','FLOAT_VECTOR','CORNER'); a.data.foreach_set('vector',[x for l in mesh.loops for x in (data['tangents'][l.vertex_index][1],data['tangents'][l.vertex_index][0],data['tangents'][l.vertex_index][2])])
        a=mesh.attributes.new('UE_source_binormal_sign','FLOAT','CORNER'); a.data.foreach_set('value',[data['signs'][l.vertex_index] for l in mesh.loops])
        if data['colors'] is not None:
            a=mesh.color_attributes.new(name='UE_VertexColor',type='BYTE_COLOR',domain='CORNER'); a.data.foreach_set('color_srgb',[x/255 for l in mesh.loops for x in (data['colors'][l.vertex_index][2],data['colors'][l.vertex_index][1],data['colors'][l.vertex_index][0],data['colors'][l.vertex_index][3])])
        mesh['UE_material_bindings']=json.dumps([(name,package or '') for name,package in data['materials']])
        a=mesh.attributes.new('UE_source_material_index','INT','FACE'); a.data.foreach_set('value',data['slots'])
        mesh['UE_source_format']='cooked_static_'+data['version']; return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        for mat in mats:
            if not mat.users: bpy.data.materials.remove(mat)
        raise
