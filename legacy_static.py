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


def read_legacy_static_path(path):
    """UE4 object-version 508 editor FRawMesh, using bounded typed package records.

    Native field layout is the previously tested 508 profile; migration of the
    package/property boundary, not a claim of independent provenance for all
    existing FRawMesh decoding or Blender construction algorithms.
    """
    from package_records import read_package, root_export, classic_custom_versions
    from skeleton_native import Reader
    from ue4_property_records import read_records
    path=Path(path); meta,raw,table=read_package(path)
    versions=classic_custom_versions(raw)
    require(meta['legacy']==-7 and meta['ue4']==508 and meta['ue5'] is None and meta['licensee']==0 and versions.get(EDITOR.bytes_le)==8 and versions.get(RENDER.bytes_le)==12,'Unsupported UE4.14 static mesh profile')
    e=root_export(table,'StaticMesh'); r=Reader(raw[e.offset:e.offset+e.size])
    props=read_records(r,table.names)
    models=[p for p in props if p.name=='SourceModels' and p.index==0]
    require(len(models)==1 and models[0].kind=='ArrayProperty' and models[0].parameters==('StructProperty',) and len(models[0].data)>=4 and struct.unpack_from('<i',models[0].data)[0]==1,'Only one legacy source LOD supported')
    def flag():
        value=r.i(); require(value in (0,1),'Invalid native boolean'); return value
    def string():
        n=r.i(); require(abs(n)<=1048576,'Oversized native string')
        if n==0:return ''
        data=r.take(n if n>0 else -2*n); end=bytes(1 if n>0 else 2)
        require(data.endswith(end),'Unterminated native string'); return data[:-len(end)].decode('utf8' if n>0 else 'utf-16-le')
    if flag():r.take(16)
    require(r.take(2)==bytes(2) and r.i()==0,'Expected editor source mesh')
    r.take(8); string(); r.take(20)
    sockets=[table.reference(r.i()) for _ in range(r.count(1024))]
    flags,count,size=r.unpack('III'); offset=r.unpack('q')[0]+meta['bulk_data_offset']
    require(flags==1 and 0<count==size<=128*1024*1024 and offset>=e.offset+e.size and offset+size<=len(raw),'Unsupported source bulk range')
    r.take(16); flag()
    n=r.count(4096); require(n>0,'Invalid section count'); sections={}
    for _ in range(n):
        key,mat,collision,shadow=r.unpack('Iiii')
        require(key<4096 and key not in sections and mat>=0 and collision in (0,1) and shadow in (0,1),'Invalid legacy section')
        sections[key]=(mat,collision,shadow)
    require(r.i()==0,'SpeedTree wind unsupported'); n=r.count(4096); require(n>0,'Invalid material count')
    materials=[]; display=[]; material_refs=[]
    for _ in range(n):
        ref=r.i(); name=r.name(table.names); imported=r.name(table.names)
        flags=r.unpack('ii'); density=r.unpack('4f')
        require(all(v in (0,1) for v in flags) and all(math.isfinite(v) for v in density),'Invalid material UV metadata')
        package=table.package(ref) if ref else ''; require(not ref or bool(package),'Unresolved material reference')
        materials.append((imported,package)); display.append(name); material_refs.append(ref)
    require(r.pos==e.size,'Unexpected legacy native export trailer')
    require(all(0<=m<n for m,_,_ in sections.values()),'Invalid section material')
    data=decode_raw(raw[offset:offset+size]); require(set(data['slots'])<=set(sections),'Missing raw face section')
    data.update(materials=materials,display=display,material_refs=material_refs,sections=sections,sockets=[x.name if x else None for x in sockets],name=e.name,source=str(path))
    return data


def read_legacy_static(export):
    """Temporary legacy integration adapter; no legacy property reads."""
    data=read_legacy_static_path(export.asset.filepath)
    require(export.export_class_type=='StaticMesh' and export.object_name==data['name'],'Mismatched static export')
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
        from material_stage import MaterialResolver, bind_native_mesh_slots
        bind_native_mesh_slots(mesh,MaterialResolver(export.asset.uproject,allow_partial=True))
    if all_lods: mesh.name=data['name']+'_LOD0'
    return [mesh] if all_lods else mesh
