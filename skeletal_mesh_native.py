"""Bounded native UE4.18/4.27 cooked skeletal render mesh reader (tagged split package).
No scanning for buffers. Unsupported layouts fail before Blender object creation.
"""
import math
import struct
from pathlib import Path
from skeleton_native import Reader, MAGIC, reference_skeleton


def require(ok, message):
    if not ok: raise ValueError(message)


def array(r, fmt, limit):
    n=r.count(limit)
    return [r.unpack(fmt)[0] for _ in range(n)]


def read_mesh(path, version='4.18'):
    if version not in ('4.18','4.27'): raise NotImplementedError('Unsupported cooked skeletal render mesh profile')
    p=Path(path); side=p.with_suffix('.uexp')
    require(p.stat().st_size<=16*1024*1024 and side.stat().st_size<=128*1024*1024,'Package exceeds size limit')
    header=p.read_bytes(); data=side.read_bytes(); r=Reader(header)
    require(r.take(4)==MAGIC and r.unpack('5i')==(-7,0,0,0,0),'Unsupported package header')
    require(r.i()==len(header) and r.string()=='None','Unsupported split header')
    flags=r.unpack('I')[0]; require(flags&0x80000000 and not flags&0x2000,'Expected tagged editor-filtered package')
    n,no,g,go,ec,eo,ic,io=r.unpack('8i')
    require(0<n<=100000 and g==go==0 and ec==1 and 0<ic<=100000 and r.pos<=no<io<eo<len(header) and io+28*ic==eo,'Invalid package tables')
    r.pos=no; names=[]
    for _ in range(n): names.append(r.string()); r.take(4)
    require(r.pos==io,'Invalid name table boundary')
    imports=[(r.name(names),r.name(names),r.i(),r.name(names)) for _ in range(ic)]
    ci,si,ti,outer=r.unpack('4i'); name=r.name(names); r.take(4); size,offset=r.unpack('qq')
    require(-ic<=ci<0 and outer==0 and imports[-ci-1][:2]==('/Script/CoreUObject','Class') and imports[-ci-1][3]=='SkeletalMesh','Not a root SkeletalMesh')
    require(offset==len(header) and size==len(data)-4 and data[-4:]==MAGIC,'Invalid split export extent')
    r=Reader(data[:-4]); seen=set()
    while True:
        key=r.name(names)
        if key=='None': break
        typ=r.name(names); sz,idx=r.unpack('ii')
        require(key not in seen and idx==0 and sz>=0,'Invalid property tag'); seen.add(key)
        if key in ('Skeleton','PhysicsAsset') and typ=='ObjectProperty': require(sz==4,'Invalid object property')
        elif key=='LODInfo' and typ=='ArrayProperty': require(r.name(names)=='StructProperty','Invalid LODInfo tag')
        elif version=='4.27' and key=='SamplingInfo' and typ=='StructProperty':
            require(r.name(names)=='SkeletalMeshSamplingInfo','Invalid sampling info tag'); r.take(16)
        else: raise ValueError('Unsupported skeletal property: '+key)
        require(r.take(1)==b'\0','Unsupported property GUID'); r.take(sz)
    require(r.i()==0 and r.unpack('BB')==(1,0),'Unsupported skeletal native header')
    bounds=r.unpack('7f'); require(all(math.isfinite(x) for x in bounds),'Invalid bounds')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i(); slot=r.name(names); r.take(28 if version=='4.27' else 24)
        package=None
        if ref:
            require(-ic<=ref<0,'Invalid material reference'); imp=imports[-ref-1]; outer=imp[2]
            require(-ic<=outer<0 and imports[-outer-1][1]=='Package','Invalid material outer')
            package=imports[-outer-1][3]
        materials.append((slot,package))
    bones=reference_skeleton(r,names)
    if version=='4.27':
        return read_lod427(r,name,bones,materials)
    require(r.i()==1 and r.unpack('BB')==(1,0),'Only one non-cloth tessellated source LOD supported')
    sections=[]
    for _ in range(r.count(4096)):
        strip,mat,start,tri=r.unpack('HHII'); require(strip==1 and mat<len(materials),'Unsupported section')
        require(r.take(8)==bytes.fromhex('0000000000ffffcd'),'Unsupported section flags')
        recompute,shadow,base=r.unpack('III'); require(recompute in (0,1) and shadow in (0,1),'Invalid section flags')
        palette=array(r,'H',256); count,maximum=r.unpack('II')
        require(palette and len(set(palette))==len(palette) and max(palette)<len(bones) and 1<=maximum<=8,'Invalid bone palette')
        require(r.take(34)==bytes(12)+b'\xcd\xcd'+bytes(16)+b'\xff'*4,'Cloth sections unsupported')
        sections.append((mat,start,tri,base,count,palette,maximum))
    def indices():
        width,stride,n=r.unpack('Bii'); require(width==stride and width in (2,4) and 0<=n<=12000000,'Invalid index buffer')
        return list(x[0] for x in struct.iter_unpack('<H' if width==2 else '<I',r.take(n*width)))
    idx=indices(); active=array(r,'H',8192); zero,n=r.unpack('ii'); required=array(r,'H',8192)
    require(zero==0 and 0<n<=1000000 and all(i<len(bones) for i in active+required),'Invalid LOD metadata')
    vertex_map=array(r,'I',1000000); max_map,uv=r.unpack('II')
    require(len(vertex_map)==n and max(vertex_map)<=max_map and 1<=uv<=8,'Invalid vertex map or UV count')
    strip,nuv,full,*bounds,stride,vc=r.unpack('HII6fii')
    require(strip==1 and nuv==uv and full in (0,1) and bounds==[1.,1.,1.,0.,0.,0.] and vc==n and stride==20+uv*(8 if full else 4),'Unsupported vertex format')
    positions=[]; tangents=[]; normals=[]; uvs=[]; signs=[]
    for _ in range(n):
        v=r.unpack('8B3f'+('f' if full else 'e')*(2*uv)); require(all(math.isfinite(x) for x in v[8:]),'Invalid vertex')
        tangents.append(tuple(x/127.5-1 for x in v[:3])); normals.append(tuple(x/127.5-1 for x in v[4:7])); signs.append(v[7]/127.5-1)
        positions.append(v[8:11]); uvs.append(v[11:])
    strip,extra,wvc,stride,sz=r.unpack('HIIII'); require(strip==1 and extra in (0,1) and wvc==sz==n and stride==8*(extra+1),'Unsupported skin weight buffer')
    weights=[r.take(stride) for _ in range(n)]
    # This profile has no vertex colors; consume the actual adjacency buffer.
    adjacency=indices(); require(all(i<n for i in adjacency),'Invalid adjacency index')
    require(r.take(4)==bytes(4) and r.pos==len(r.data),"Unsupported skeletal export trailer")
    return assemble(r,name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,vertex_map,'4.18')

def read_lod427(r,name,bones,materials):
    """UE4.27 inline cooked render LOD, fixed 8-bit indices/weights."""
    require(r.unpack('IIHII')==(1,1,1,0,1),'Unsupported 4.27 LOD header')
    active=array(r,'H',8192)
    sections=[]
    for _ in range(r.count(4096)):
        strip,mat,start,tri,flags,shadow,base=r.unpack('HHIQBIQ')
        require(strip==1 and mat<len(materials) and flags in (0,1) and shadow in (0,1),'Unsupported 4.27 section')
        palette=array(r,'H',256); count,maximum=r.unpack('II')
        require(palette and len(set(palette))==len(palette) and max(palette)<len(bones) and 1<=maximum<=12 and 0<count<=1000000,'Invalid 4.27 section palette')
        require(r.take(22)==b'\xff\xff'+bytes(16)+b'\xff'*4,'Cloth sections unsupported')
        # Serialized duplicate-vertex overlap metadata; not an import vertex map.
        array(r,'I',12000000)
        require(r.i()==count,'Invalid overlap metadata count'); r.take(count*8)
        require(r.i()==0,'Unsupported section trailer')
        sections.append((mat,start,tri,base,count,palette,maximum))
    required=array(r,'H',8192)
    require(all(i<len(bones) for i in active+required),'Invalid bone metadata')
    length=r.count(128*1024*1024); start=r.pos
    def indices():
        width,stride,n=r.unpack('Bii'); require(width==stride and width in (2,4) and 0<=n<=12000000,'Invalid index buffer')
        return [x[0] for x in struct.iter_unpack('<H' if width==2 else '<I',r.take(n*width))]
    require(r.unpack('H')==(1,),'Unsupported index strip flags'); idx=indices()
    stride,n,stored_stride,vc=r.unpack('IIII')
    require(stride==stored_stride==12 and 0<n<=1000000 and vc==n,'Invalid position buffer')
    positions=list(struct.iter_unpack('<3f',r.take(n*12)))
    strip,uv,vc,full,high=r.unpack('HIIII')
    require(strip==1 and 1<=uv<=8 and vc==n and full in (0,1) and high==0,'Unsupported UV/tangent metadata')
    require(r.unpack('II')==(8,n),'Invalid tangent buffer')
    tangents=[]; normals=[]; signs=[]
    for _ in range(n):
        v=r.unpack('8b'); tangents.append(tuple(max(-1,x/127) for x in v[:3])); normals.append(tuple(max(-1,x/127) for x in v[4:7])); signs.append(max(-1,v[7]/127))
    require(r.unpack('II')==((8 if full else 4),n*uv),'Invalid UV buffer')
    uvs=[r.unpack(('f' if full else 'e')*(2*uv)) for _ in range(n)]
    require(all(math.isfinite(v) for row in positions+uvs for v in row),'Nonfinite render data')
    strip,variable,influences,total,vc,wide,stride,size=r.unpack('HIIIIIII')
    require(strip==1 and variable==wide==0 and 1<=influences<=12 and total==n*influences and vc==n and stride==1 and size==total*2,'Unsupported fixed weight buffer')
    weights=[r.take(influences*2) for _ in range(n)]
    require(r.unpack('HIII')==(1,0,4,0),'Unsupported weight lookup buffer')
    adjacency=indices(); require(all(i<n for i in adjacency),'Invalid adjacency buffer')
    require(r.unpack('II')==(0,0) and r.pos-start==length,'Invalid 4.27 buffer extent')
    require(r.take(6)==b'\x01\x01'+bytes(4) and r.pos==len(r.data),'Unsupported 4.27 export trailer')
    return assemble(r,name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,None,'4.27')


def assemble(r,name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,vertex_map,version):
    n=len(positions); stride=len(weights[0])
    faces=[]; slots=[]; skin=[None]*n; used=set(); covered=set()
    for mat,start,tri,base,count,palette,maximum in sections:
        require(count>0 and base+count<=n and start+tri*3<=len(idx),'Invalid section extent')
        for vi in range(base,base+count):
            require(skin[vi] is None,'Overlapping section vertices'); raw=weights[vi]; k=stride//2; result={}
            for joint,w in zip(raw[:k],raw[k:]):
                if w:
                    require(joint<len(palette),'Invalid local bone index'); bone=palette[joint]; result[bone]=result.get(bone,0)+w
            require(sum(result.values())==255 and len(result)<=maximum,'Invalid source weight normalization'); skin[vi]=result
        for j in range(start,start+tri*3,3):
            require(j not in covered,'Overlapping face sections'); covered.add(j); face=idx[j:j+3]
            require(len(set(face))==3 and all(base<=i<base+count for i in face),'Invalid section triangle'); faces.append(tuple(face)); slots.append(mat)
    require(len(covered)*3==len(idx) and all(x is not None for x in skin),'Incomplete section coverage')
    return dict(version=version,name=name,bones=bones,materials=materials,positions=positions,normals=normals,tangents=tangents,signs=signs,uvs=uvs,faces=faces,slots=slots,weights=skin,vertex_map=vertex_map,buffer_end=r.pos,tail_bytes=len(r.data)-r.pos)


def build_mesh(data, collection=None):
    """Build an editable armature and skinned mesh from the validated render buffers."""
    import bpy
    from skeleton_native import build_armature
    collection=collection or bpy.context.collection
    arm=build_armature(data['name']+'_Armature',data['bones'],collection)
    mesh=None; obj=None; materials=[]
    try:
        mesh=bpy.data.meshes.new(data['name'])
        mesh.from_pydata([(y*.01,x*.01,z*.01) for x,y,z in data['positions']],[],data['faces'])
        mesh.update()
        require(not mesh.validate(clean_customdata=False),'Invalid Blender topology')
        for slot,package in data['materials']:
            mat=bpy.data.materials.new(slot); materials.append(mat); mat['UE_unresolved_material']=True
            if package: mat['UE_material_package']=package
            mesh.materials.append(mat)
        for poly,slot in zip(mesh.polygons,data['slots']): poly.material_index=slot; poly.use_smooth=True
        for channel in range(len(data['uvs'][0])//2):
            layer=mesh.uv_layers.new(name=f'UV{channel}')
            layer.data.foreach_set('uv',[v for loop in mesh.loops for v in (data['uvs'][loop.vertex_index][2*channel],1-data['uvs'][loop.vertex_index][2*channel+1])])
        mesh.normals_split_custom_set([(y,x,z) for x,y,z in (data['normals'][loop.vertex_index] for loop in mesh.loops)])
        attr=mesh.attributes.new('UE_source_tangent','FLOAT_VECTOR','CORNER')
        attr.data.foreach_set('vector',[v for loop in mesh.loops for v in (data['tangents'][loop.vertex_index][1],data['tangents'][loop.vertex_index][0],data['tangents'][loop.vertex_index][2])])
        attr=mesh.attributes.new('UE_source_binormal_sign','FLOAT','CORNER'); attr.data.foreach_set('value',[data['signs'][loop.vertex_index] for loop in mesh.loops])
        attr=mesh.attributes.new('UE_source_vertex_index','INT','POINT'); attr.data.foreach_set('value',list(range(len(data['positions']))))
        if data['vertex_map'] is not None:
            attr=mesh.attributes.new('UE_import_vertex_index','INT','POINT'); attr.data.foreach_set('value',data['vertex_map'])
        obj=bpy.data.objects.new(data['name'],mesh); collection.objects.link(obj)
        groups=[obj.vertex_groups.new(name=b['name']) for b in data['bones']]
        for i,weights in enumerate(data['weights']):
            for j,w in weights.items(): groups[j].add([i],w/255.,'REPLACE')
        obj.parent=arm; mod=obj.modifiers.new('UE native skin','ARMATURE'); mod.object=arm; mod.use_deform_preserve_volume=False
        obj['UE_skeletal_mesh_status']='native_cooked_'+data['version']+'_lod0'; obj['UE_unparsed_tail_bytes']=data['tail_bytes']
        arm['UE_skeleton_status']='native_skin_bound'; return obj,arm
    except Exception:
        if obj: bpy.data.objects.remove(obj,do_unlink=True)
        if mesh and mesh.users==0: bpy.data.meshes.remove(mesh)
        for mat in materials:
            if mat.users==0: bpy.data.materials.remove(mat)
        ar=arm.data; bpy.data.objects.remove(arm,do_unlink=True); bpy.data.armatures.remove(ar)
        raise
