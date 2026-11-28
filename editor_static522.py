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


def read_source_models(reader, raw, bulk_base, export_end, count):
    """Read explicit source-model slots, preserving absent LOD identities.

    The one-model profile is original-fixture verified; multi-model traversal
    is exercised with controlled headers, not an original multi-LOD package.
    """
    require(1 <= count <= 64, 'Invalid source LOD count')
    result=[]; missing=[]; spans=[]; total=0
    for index in range(count):
        if not flag(reader):
            missing.append(index); continue
        flags, expanded, packed, offset = reader.unpack('IIIq')
        if flags not in (0x201,0x203):
            raise UnsupportedProfile('Unsupported source bulk flags')
        start=bulk_base+offset; end=start+packed
        require(offset>=0 and start>=export_end and 0<expanded<=128*1024*1024 and 0<packed<=128*1024*1024 and end<=len(raw)-4, 'Invalid source bulk extent')
        require(all((start,end)==span or end<=span[0] or start>=span[1] for span in spans), 'Overlapping source bulk extents')
        total+=expanded
        require(total<=256*1024*1024, 'Aggregate source LOD byte limit')
        spans.append((start,end)); payload=raw[start:end]
        if flags&2: payload=decompress_chunks(payload,expanded)
        else: require(packed==expanded, 'Uncompressed source size mismatch')
        reader.take(16); flag(reader)
        result.append((index,decode_mesh_description(payload)))
    if not result: raise UnsupportedProfile('No stored MeshDescription source')
    return result,missing


def read_static_lods(path):
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
    require(1<=count<=64, 'Invalid source LOD count')
    if flag(reader): reader.take(16)
    require(reader.take(2)==b'\0\0' and not flag(reader), 'Expected unstripped editor mesh')
    table.reference(reader.i()); table.reference(reader.i())
    chars=reader.i(); require(abs(chars)<=1048576,'Invalid high-resolution source name')
    if chars:
        data=reader.take(chars if chars>0 else -2*chars); require(data.endswith(b'\0' if chars>0 else b'\0\0'),'Unterminated high-resolution source name')
    reader.take(4+16) # high-resolution CRC, lighting GUID
    sockets=[table.reference(reader.i()) for _ in range(reader.count(1024))]
    models,missing=read_source_models(reader,raw,summary['bulk_data_offset'],max(e.offset+e.size for e in table.exports),count)
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
    return [dict(name=export.name,source=str(path),geometry=geometry,materials=slots,display=display,
                 sockets=[s.name if s else None for s in sockets],lod_index=index,lod_count=count,missing_lods=missing)
            for index,geometry in models]


def read_static(path):
    return read_static_lods(path)[0]


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
        mesh['UE_source_lod_count']=data['lod_count'];mesh['UE_lod_index']=data['lod_index'];mesh['UE_missing_source_lods']=json.dumps(data['missing_lods']);mesh['UE_socket_references']=json.dumps(data['sockets'])
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        raise
