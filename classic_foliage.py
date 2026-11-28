"""Typed UE4 508 foliage package boundary, using the existing native decoder.

The two source components in Western Frontier provide the positive fixture
profile. The existing instance payload algorithm is retained for parity.
"""
from dataclasses import dataclass
import struct
from classic_actor_layout import require, object_index, triple
from package_records import read_package, ExportRecord, ImportRecord
from skeleton_native import Reader
from ue4_property_records import read_records


@dataclass(frozen=True, slots=True)
class FoliageRecord:
    name: str
    package: str
    owner: str
    root_index: int
    root_transform: tuple
    component_transform: tuple
    rows: tuple


def _properties(raw, table, entry):
    reader = Reader(raw[entry.offset:entry.offset + entry.size])
    props = {p.name: p for p in read_records(reader, table.names) if p.index == 0}
    return props, reader


def _transform(props, names):
    for key in ('bAbsoluteLocation', 'bAbsoluteRotation', 'bAbsoluteScale'):
        if key in props:
            require(props[key].kind == 'BoolProperty' and not props[key].boolean,
                    'Unsupported absolute foliage transform')
    socket = props.get('AttachSocketName')
    if socket is not None:
        require(socket.kind == 'NameProperty' and len(socket.data) == 8 and
                Reader(socket.data).name(names) == 'None', 'Unsupported foliage socket attachment')
    return (triple(props, 'RelativeLocation', 'Vector', (0.,0.,0.)),
            triple(props, 'RelativeRotation', 'Rotator', (0.,0.,0.)),
            triple(props, 'RelativeScale3D', 'Vector', (1.,1.,1.)))


def inspect_foliage(path):
    from foliage_legacy import decode_instances
    meta, raw, table = read_package(path)
    require(meta['ue4'] == 508 and meta['ue5'] is None and meta['licensee'] == 0,
            'Unsupported classic foliage profile')
    records, errors = [], []
    for entry in table.exports:
        if entry.kind != 'FoliageInstancedStaticMeshComponent':
            continue
        try:
            props, tail = _properties(raw, table, entry)
            count = props.get('NumBuiltInstances')
            require(count is not None and count.kind == 'IntProperty' and len(count.data) == 4,
                    'Missing foliage count')
            rows = decode_instances(tail.take(len(tail.data)-tail.pos), struct.unpack('<i', count.data)[0])
            mesh_index = object_index(props, 'StaticMesh')
            mesh = table.reference(mesh_index)
            package = table.package(mesh_index)
            require(isinstance(mesh, ImportRecord) and mesh.kind == 'StaticMesh' and package.startswith('/Game/'),
                    'Unresolved foliage mesh package')
            owner = table.reference(entry.outer)
            require(isinstance(owner, ExportRecord) and owner.kind == 'InstancedFoliageActor', 'Invalid foliage owner')
            level = table.reference(owner.outer)
            require(isinstance(level, ExportRecord) and level.kind == 'Level', 'Invalid foliage level')
            owner_props, _ = _properties(raw, table, owner)
            root_index = object_index(owner_props, 'RootComponent')
            root = table.reference(root_index)
            require(isinstance(root, ExportRecord) and root.outer == entry.outer and root.kind == 'SceneComponent'
                    and object_index(props, 'AttachParent') == root_index, 'Unsupported foliage root association')
            root_props, _ = _properties(raw, table, root)
            require(not object_index(root_props, 'AttachParent'), 'Unsupported external foliage parent')
            records.append(FoliageRecord(entry.name, package, owner.name, root_index,
                                         _transform(root_props, table.names), _transform(props, table.names), tuple(rows)))
        except (ValueError, UnicodeError, struct.error) as exc:
            errors.append({'component':entry.name,'package':'','instances':0,'status':'unsupported','detail':str(exc)})
    return records, errors


def reconstruct_classic_foliage(filepath, collection, resolver):
    import bpy
    from collections import Counter
    from classic_layout_blender import apply_transform
    from foliage_legacy import build_instances
    records, reports = inspect_foliage(filepath)
    roots = {}
    for record in records:
        result = {'component':record.name,'package':record.package,'instances':0,'source_instances':len(record.rows),'status':'unsupported'}
        created = []
        try:
            mesh, status = resolver(record.package)
            if mesh is None:
                result.update(status=status, detail='Foliage source mesh unavailable')
                continue
            root = roots.get(record.root_index)
            if root is None:
                root = bpy.data.objects.new(record.owner+' / Foliage root',None)
                created.append(root)
                collection.objects.link(root)
                apply_transform(root, *record.root_transform)
                root['UE_foliage_root'] = record.owner
            anchor = bpy.data.objects.new(record.name+' / Component',None)
            created.append(anchor)
            collection.objects.link(anchor)
            anchor.parent = root
            apply_transform(anchor, *record.component_transform)
            anchor['UE_foliage_anchor'] = record.name
            children = build_instances(collection,anchor,mesh,record.name,record.package,record.rows)
            created.extend(children)
            roots[record.root_index] = root
            result.update(status='reconstructed', instances=len(children))
        except Exception as exc:
            for obj in reversed(created):
                bpy.data.objects.remove(obj,do_unlink=True)
            result.update(status='unsupported' if isinstance(exc,(ValueError,NotImplementedError)) else 'failed',detail=str(exc))
        finally:
            reports.append(result)
    return {'components':len(reports),'status':dict(Counter(r['status'] for r in reports)),
            'instances':sum(r['instances'] for r in reports),'records':reports}
