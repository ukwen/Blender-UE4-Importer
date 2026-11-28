"""UE4.27 editor MeshDescription source bulk, exact tested custom-version profile.

Summary layout: UAssetAPI UAsset.cs ReadHeader (MIT, notice in third_party).
The native source-model contract is verified against original monolithic Goblin
War Camp static meshes. Existing MeshDescription decoding/building is reused;
that retained code still requires provenance review. No legacy parser imports.
"""
import json
import math
from pathlib import Path
import struct

from package_records import classic_custom_versions, read_package, root_export
from package_inspector import inspect_package
from skeleton_native import Reader
from ue4_property_records import read_records
from source_compression import decompress_chunks
from mesh_description import decode_mesh_description

# Serialized FGuid words for FEditorObjectVersion, FEnterpriseObjectVersion,
# FRenderingObjectVersion in the recovered original assets.
VERSIONS = {bytes.fromhex('ed68b0e4e94294f40bda31a241bb462e'):40,
            bytes.fromhex('d6bcff9d58014f49821221e288a8923c'):10,
            bytes.fromhex('9f8bf812fc4a75880cd97ca629bd3a38'):44}

class UnsupportedProfile(NotImplementedError):
    """A different layout, not a malformed record in this supported layout."""


def require(ok, message):
    if not ok:
        raise ValueError(message)


def flag(reader):
    result = reader.i()
    require(result in (0,1), 'Invalid native boolean')
    return bool(result)


def read_static(path):
    path = Path(path)
    meta, raw, table = read_package(path)
    versions = classic_custom_versions(raw) if meta['ue5'] is None else {}
    if not (meta['ue4']==522 and meta['ue5'] is None and meta['legacy']==-7 and meta['licensee']==0
            and not meta['flags'] & 0x80002008 and all(versions.get(k)==v for k,v in VERSIONS.items())):
        raise UnsupportedProfile('Unsupported UE4.27 MeshDescription source version')
    summary = inspect_package(path, include_bulk_522=True)
    require(summary['status']=='tables_inspected' and summary.get('bulk_data_offset') is not None and summary['size']==len(raw), 'Invalid editor bulk summary')
    export = root_export(table,'StaticMesh')
    reader = Reader(raw[export.offset:export.offset+export.size])
    props = read_records(reader,table.names)
    models = [p for p in props if p.name=='SourceModels' and p.index==0]
    require(len(models)==1 and models[0].kind=='ArrayProperty' and models[0].parameters==('StructProperty',) and len(models[0].data)>=4, 'Missing SourceModels array')
    count = struct.unpack_from('<i',models[0].data)[0]
    # The original fixtures each have one explicit source LOD. Retain the
    # existing compatibility path for other source-model layouts.
    if count != 1:
        raise UnsupportedProfile('Only one explicit editor source LOD validated')
    if flag(reader): reader.take(16)
    require(reader.take(2)==b'\0\0' and not flag(reader), 'Expected unstripped editor mesh')
    table.reference(reader.i()); table.reference(reader.i())
    chars=reader.i(); require(abs(chars)<=1048576,'Invalid high-resolution source name')
    if chars:
        data=reader.take(chars if chars>0 else -2*chars); require(data.endswith(b'\0' if chars>0 else b'\0\0'),'Unterminated high-resolution source name')
    reader.take(4+16) # high-resolution CRC, lighting GUID
    sockets=[table.reference(reader.i()) for _ in range(reader.count(1024))]
    require(flag(reader),'No stored MeshDescription source')
    flags, expanded, packed, offset = reader.unpack('IIIq')
    if flags not in (0x201,0x203):
        raise UnsupportedProfile('Unsupported source bulk flags')
    start = summary['bulk_data_offset'] + offset
    # Bulk must not overlap any serialized export or the package end signature.
    require(start>=max(e.offset+e.size for e in table.exports) and offset>=0 and 0<expanded<=128*1024*1024 and 0<packed<=128*1024*1024 and start+packed<=len(raw)-4,'Invalid source bulk extent')
    payload=raw[start:start+packed]
    if flags&2:
        payload=decompress_chunks(payload,expanded)
    else:
        require(packed==expanded,'Uncompressed source size mismatch')
    reader.take(16); flag(reader)
    require(not flag(reader),'SpeedTree source not supported')
    slots=[]; display=[]
    for _ in range(reader.count(4096)):
        ref=reader.i(); name=reader.name(table.names); imported=reader.name(table.names)
        flag(reader);flag(reader)
        require(all(map(math.isfinite,reader.unpack('4f'))),'Invalid UV density')
        package=table.package(ref) if ref else ''
        require(not ref or bool(package),'Unresolved material slot reference')
        slots.append((imported,package));display.append(name)
    require(slots and reader.pos==export.size,'Unexpected editor static mesh tail')
    geometry=decode_mesh_description(payload)
    return dict(name=export.name,source=str(path),geometry=geometry,materials=slots,display=display,sockets=[s.name if s else None for s in sockets])


def build_static(data):
    import bpy
    from mesh_description_blender import build_description
    mesh=build_description(data['geometry'],data['name'],data['source'])
    try:
        names=[n for n,_ in data['materials']]
        mapping={g:names.index(n) for g,n in zip(mesh['UE_polygon_group_ids'],mesh['UE_material_slots']) if names.count(n)==1}
        if len(mapping)==len(mesh['UE_polygon_group_ids']):
            attr=mesh.attributes.new('UE_source_material_index','INT','FACE')
            attr.data.foreach_set('value',[mapping[x.value] for x in mesh.attributes['UE_polygon_group'].data])
        else:
            mesh['UE_material_binding_error']='MeshDescription material slot mapping is ambiguous or missing'
        mesh['UE_material_bindings']=json.dumps(data['materials']);mesh['UE_static_material_slots']=names
        mesh['UE_source_lod_count']=1;mesh['UE_lod_index']=0;mesh['UE_missing_source_lods']='[]';mesh['UE_socket_references']=json.dumps(data['sockets'])
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
