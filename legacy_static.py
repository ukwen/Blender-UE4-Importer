"""Bounded UE4.14 (object version 508) editor FRawMesh import."""
import json
import math
import struct
import uuid
from pathlib import Path

EDITOR=uuid.UUID('e4b068ed-42e9-f494-0bda-31a241bb462e')
RENDER=uuid.UUID('12f88b9f-4afc-8875-0cd9-7ca629bd3a38')


def require(ok,message):
    if not ok: raise ValueError(message)


def decode_raw(payload):
    from skeleton_native import Reader
    r=Reader(payload)
    require(r.unpack('ii')==(1,0),'Unsupported UE4.14 FRawMesh version')
    def array(fmt,limit=12000000):
        n=r.count(limit); width=struct.calcsize('<'+fmt)
        return list(struct.iter_unpack('<'+fmt,r.take(n*width)))
    slots=[x[0] for x in array('i')]; smooth=[x[0] for x in array('I')]; points=array('3f',1000000)
    wedges=[x[0] for x in array('i')]; tangents=array('3f'); bitangents=array('3f'); normals=array('3f')
    uv=[array('2f') for _ in range(8)]; colors=array('4B'); imports=[x[0] for x in array('i',4096)]
    n=len(wedges); require(points and slots and n==len(slots)*3 and len(smooth)==len(slots),'Invalid raw mesh counts')
    require(all(0<=i<len(points) for i in wedges) and min(slots)>=0,'Invalid wedge or material index')
    require(all(len(a) in (0,n) for a in (tangents,bitangents,normals,colors,*uv)),'Invalid corner data count')
    require(all(math.isfinite(v) for a in (points,tangents,bitangents,normals,*uv) for row in a for v in row),'Nonfinite geometry')
    require(r.pos==len(payload),'Unexpected raw mesh trailer')
    return dict(points=points,wedges=wedges,slots=slots,smooth=smooth,tangents=tangents,bitangents=bitangents,normals=normals,uv=uv,colors=colors,import_slots=imports)


def package_reference(asset,index):
    seen=set()
    while index<0:
        require(index not in seen and -index<=len(asset.imports),'Invalid material reference chain'); seen.add(index)
        ref=asset.GetImport(index)
        if ref.class_name=='Package' and ref.object_name.startswith(('/Game/','/Engine/')): return ref.object_name
        index=ref.outer_index
    return ''


def read_legacy_static(export):
    a=export.asset; f=a.f; s=a.summary; path=Path(a.filepath)
    require(s.version_ue4==508 and s.version_ue4_licensee==0 and s.version_legacy==-7 and s.custom_versions.get(EDITOR)==8 and s.custom_versions.get(RENDER)==12 and not s.compression_flags and not path.with_suffix('.uexp').exists(),'Unsupported UE4.14 static mesh profile')
    require(export.export_class_type=='StaticMesh','Expected static mesh export')
    export.ReadProperties(False,False)
    require(export.serial_desc.offset<=f.Position()<export.serial_desc.offset+export.serial_desc.count,'Invalid native export start')
    guid=f.ReadInt32(); require(guid in (0,1),'Invalid object GUID flag')
    if guid: f.ReadGuid()
    require(f.ReadBytes(2)==bytes(2) and f.ReadInt32()==0,'Expected editor source mesh')
    f.ReadInt32(); f.ReadInt32(); f.ReadFString(); f.ReadUInt32(); f.ReadGuid()
    n=f.ReadInt32(); require(0<=n<=1024,'Invalid sockets count'); sockets=[a.DecodePackageIndex(f.ReadInt32()) for _ in range(n)]
    require(len(export.properties.TryGetValue('SourceModels',[]))==1,'Only one legacy source LOD supported')
    flags,count,size=f.ReadStruct('III',12); offset=f.ReadInt64()+s.bulk_data_offset
    require(flags==1 and 0<count==size<=128*1024*1024 and offset>=export.serial_desc.offset+export.serial_desc.count and offset+size<=path.stat().st_size,'Unsupported source bulk range')
    f.ReadGuid(); require(f.ReadInt32() in (0,1),'Invalid source GUID flag')
    n=f.ReadInt32(); require(0<n<=4096,'Invalid section count'); sections={}
    for _ in range(n):
        key,mat,collision,shadow=f.ReadStruct('Iiii',16)
        require(key<4096 and key not in sections and mat>=0 and collision in (0,1) and shadow in (0,1),'Invalid legacy section')
        sections[key]=(mat,collision,shadow)
    require(f.ReadInt32()==0,'SpeedTree wind unsupported'); n=f.ReadInt32(); require(0<n<=4096,'Invalid material count')
    materials=[]; display=[]; material_refs=[]
    for _ in range(n):
        ref=f.ReadInt32(); name=f.ReadFName(a.names); imported=f.ReadFName(a.names)
        flags=f.ReadStruct('ii',8); density=f.ReadStruct('4f',16)
        require(all(v in (0,1) for v in flags) and all(math.isfinite(v) for v in density),'Invalid material UV metadata')
        package=package_reference(a,ref) if ref else ''; require(not ref or bool(package),'Unresolved material reference')
        materials.append((imported,package)); display.append(name); material_refs.append(ref)
    require(f.Position()==export.serial_desc.offset+export.serial_desc.count,'Unexpected legacy native export trailer')
    require(all(0<=m<n for m,_,_ in sections.values()),'Invalid section material')
    f.Seek(offset); data=decode_raw(f.ReadBytes(size))
    require(set(data['slots'])<=set(sections),'Missing raw face section')
    data.update(materials=materials,display=display,material_refs=material_refs,sections=sections,sockets=[x.object_name if x else None for x in sockets],name=export.object_name,source=str(path))
    return data


def build_legacy_static(data):
    import bpy
    pts=[(y*.01,x*.01,z*.01) for x,y,z in data['points']]; indices=list(range(len(pts))); faces=[]; seen=set(); splits=0
    for i in range(0,len(data['wedges']),3):
        face=tuple(data['wedges'][i:i+3]); require(len(set(face))==3,'Degenerate source triangle indices')
        key=tuple(sorted(face))
        if key in seen:
            # Preserve duplicate faces and all their corner data, splitting only topology.
            start=len(pts); pts.extend(pts[v] for v in face); indices.extend(face); face=(start,start+1,start+2); splits+=1
        seen.add(key); faces.append(face)
    mesh=bpy.data.meshes.new(data['name'])
    try:
        mesh.from_pydata(pts,[],faces); require(not mesh.validate(verbose=False),'Blender rejected source topology'); mesh.update()
        require(len(mesh.polygons)==len(faces) and len(mesh.vertices)==len(pts),'Geometry count mismatch')
        for i,p in enumerate(mesh.polygons): require(tuple(p.vertices)==faces[i],'Unexpected polygon order'); p.use_smooth=True
        for j,channel in enumerate(data['uv']):
            if channel:
                layer=mesh.uv_layers.new(name='UV'+str(j)); layer.data.foreach_set('uv',[v for u,w in channel for v in (u,1-w)])
        if data['normals']: mesh.normals_split_custom_set([(y,x,z) for x,y,z in data['normals']])
        for name,values in [('UE_source_tangent',data['tangents']),('UE_source_bitangent',data['bitangents'])]:
            if values:
                attr=mesh.attributes.new(name,'FLOAT_VECTOR','CORNER'); attr.data.foreach_set('vector',[v for x,y,z in values for v in (y,x,z)])
        if data['colors']:
            attr=mesh.color_attributes.new(name='Color',type='BYTE_COLOR',domain='CORNER'); attr.data.foreach_set('color_srgb',[v/255 for b,g,r,a in data['colors'] for v in (r,g,b,a)])
        for name,domain,values in [('UE_source_vertex_index','POINT',indices),('UE_source_triangle_index','FACE',list(range(len(faces)))),('UE_source_material_index','FACE',[data['sections'][i][0] for i in data['slots']]),('UE_source_smoothing_mask','FACE',[v if v<2**31 else v-2**32 for v in data['smooth']])]:
            attr=mesh.attributes.new(name,'INT',domain);attr.data.foreach_set('value',values)
        mesh['UE_source_format']='UE4.14 FRawMesh'; mesh['UE_material_bindings']=json.dumps(data['materials']); mesh['UE_static_material_slots']=[x[0] for x in data['materials']]; mesh['UE_section_info']=json.dumps(data['sections']); mesh['UE_source_lod_count']=1;mesh['UE_lod_index']=0; mesh['UE_missing_source_lods']='[]'; mesh['UE_socket_references']=json.dumps(data['sockets']); mesh['UE_duplicate_faces_split']=splits; mesh['UAsset']=data['source']
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh);raise


def import_legacy_static(export,import_materials=False,all_lods=False):
    data=read_legacy_static(export);mesh=build_legacy_static(data)
    if import_materials:
        # Reuse the existing material importer; no new shader implementation.
        import bpy
        from umat import TryGetUMaterialImport
        for (name,package),display,index in zip(data['materials'],data['display'],data['material_refs']):
            ref=export.asset.DecodePackageIndex(index)
            try: mat=TryGetUMaterialImport(ref,mesh=mesh) if ref else None
            except Exception: mat=None
            if mat is None:
                mat=bpy.data.materials.new(display);mat['UE_unresolved_material']=True;mat['UE_material_package']=package
            mesh.materials.append(mat)
        for p,v in zip(mesh.polygons,mesh.attributes['UE_source_material_index'].data):p.material_index=v.value
    if all_lods: mesh.name=data['name']+'_LOD0'
    return [mesh] if all_lods else mesh
