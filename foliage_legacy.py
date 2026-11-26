"""Bounded UE4.14 editor foliage component decoder and Blender linked instances."""
import math
import struct


def decode_instances(payload, expected_count):
    # Profile observed in Western Frontier version 508 editor exports. Do not scan
    # for plausible transforms: require the exact prefix, bulk stride and trailer.
    if len(payload) < 47 or payload[:10] != b'\0\0\0\0\1\0\0\0\0\0' or payload[26:31] != bytes(5):
        raise ValueError('Unsupported foliage native prefix')
    stride, count = struct.unpack_from('<II', payload, 31)
    if stride != 80 or count != expected_count or not 0 < count <= 1000000:
        raise ValueError('Unsupported foliage instance count or stride')
    end = 39 + count * stride
    if end + 8 > len(payload):
        raise ValueError('Truncated foliage instance buffer')
    node_stride, nodes = struct.unpack_from('<II', payload, end)
    if node_stride != 40 or not 0 < nodes <= 2 * count or end + 8 + nodes * node_stride != len(payload):
        raise ValueError('Unsupported foliage cluster trailer')
    transforms = []
    for row in struct.iter_unpack('<20f', payload[39:end]):
        if not all(math.isfinite(v) for v in row) or (row[3], row[7], row[11], row[15]) != (0., 0., 0., 1.):
            raise ValueError('Invalid foliage affine matrix')
        transforms.append(row)
    for node in struct.iter_unpack('<3f i 3f iii', payload[end+8:]):
        if not all(math.isfinite(node[j]) for j in (0, 1, 2, 4, 5, 6)) or any(node[j] > node[j+4] for j in range(3)):
            raise ValueError('Invalid foliage cluster bounds')
        if not 0 <= node[8] <= node[9] < count or any(v < -1 or v >= nodes for v in (node[3], node[7])):
            raise ValueError('Invalid foliage cluster range')
    return transforms


def read_component(export):
    from uasset import Properties
    asset = export.asset
    if (export.export_class_type != 'FoliageInstancedStaticMeshComponent' or asset.summary.version_ue4 != 508
            or asset.summary.version_legacy != -7 or asset.summary.version_ue4_licensee != 0 or asset.summary.compression_flags):
        raise ValueError('Unsupported foliage export profile')
    f = asset.f
    f.Seek(export.serial_desc.offset)
    props = Properties().Read(asset, read_children=False)
    end = export.serial_desc.offset + export.serial_desc.count
    remaining = end - f.Position()
    if not 47 <= remaining <= 128 * 1024 * 1024:
        raise ValueError('Invalid foliage export extent')
    records = decode_instances(f.ReadBytes(remaining), props.TryGetValue('NumBuiltInstances'))
    ref = props.TryGetValue('StaticMesh')
    package = getattr(getattr(ref, 'import_ref', None), 'object_name', '')
    if not package.startswith('/Game/'):
        raise ValueError('Unresolved foliage mesh package')
    return props, package, records


def instance_matrix(row):
    from mathutils import Matrix
    # Unreal FMatrix rows are basis vectors; Blender uses column vectors.
    # Change handedness by conjugating with the X/Y swap; convert cm to m.
    unreal = Matrix([row[i:i+4] for i in range(0, 16, 4)]).transposed()
    swap = Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
    result = swap @ unreal @ swap
    result.translation *= .01
    return result


def build_instances(collection, parent, mesh, component_name, package, records):
    import bpy
    if mesh is None or parent is None:
        raise ValueError('Foliage requires resolved mesh and component parent')
    # Validate all matrices before creating any objects. Refuse shear that Blender
    # cannot represent as a local transform without silently changing placement.
    matrices = [instance_matrix(row) for row in records]
    from mathutils import Matrix
    for m in matrices:
        loc, rot, scale = m.decompose()
        rebuilt = Matrix.LocRotScale(loc, rot, scale)
        if max(abs(m[i][j]-rebuilt[i][j]) for i in range(4) for j in range(4)) > 1e-5:
            raise ValueError('Foliage matrix contains unsupported shear')
    created = []
    try:
        for index, (row, matrix) in enumerate(zip(records, matrices)):
            obj = bpy.data.objects.new(f'{component_name}_{index:05d}', mesh)
            created.append(obj)
            collection.objects.link(obj)
            obj.parent = parent
            obj.matrix_basis = matrix
            obj['UE_foliage_component'] = component_name
            obj['UE_foliage_instance_index'] = index
            obj['UE_mesh_package'] = package
            obj['UE_lightmap_shadowmap_bias'] = list(row[16:20])
        return created
    except Exception:
        for obj in created:
            bpy.data.objects.remove(obj, do_unlink=True)
        raise


def reconstruct_foliage(filepath, collection, resolver):
    """Decode map-owned foliage components, retaining failures in a separate report."""
    import bpy
    import uasset
    from umap import Transform
    from collections import Counter
    records=[]; roots={}
    with uasset.UAsset(filepath) as asset:
        for component in asset.exports:
            if component.export_class_type != 'FoliageInstancedStaticMeshComponent':
                continue
            record={'component':component.object_name,'package':'','instances':0,'status':'unsupported'}
            created=[]; root_obj=None; new_root=False
            try:
                props,package,rows=read_component(component)
                record.update(package=package,source_instances=len(rows))
                owner=asset.GetExport(component.outer_index) if 0<component.outer_index<=len(asset.exports) else None
                if owner is None or owner.export_class_type!='InstancedFoliageActor' or not 0<owner.outer_index<=len(asset.exports) or asset.GetExport(owner.outer_index).export_class_type!='Level':
                    raise ValueError('Foliage component is not owned by a level foliage actor')
                owner.ReadProperties(False); root=owner.properties.TryGetValue('RootComponent')
                if root is None or root.outer_index!=component.outer_index or props.TryGetValue('AttachParent') is not root:
                    raise ValueError('Unsupported foliage attachment hierarchy')
                root.ReadProperties(False)
                for p in (props,root.properties):
                    if any(p.TryGetValue(k,False) for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')) or p.TryGetValue('AttachSocketName','None') not in ('None','',None):
                        raise ValueError('Unsupported foliage absolute or socket transform')
                if root.properties.TryGetValue('AttachParent') is not None:
                    raise ValueError('Unsupported external foliage parent')
                mesh,status=resolver(package)
                if mesh is None:
                    record.update(status=status,detail='Foliage source mesh unavailable'); continue
                root_obj=roots.get(id(root))
                if root_obj is None:
                    root_obj=bpy.data.objects.new(owner.object_name+' / Foliage root',None); created.append(root_obj)
                    collection.objects.link(root_obj); root_obj.rotation_mode='YXZ'; Transform(root,root_obj)
                    root_obj['UE_foliage_root']=owner.object_name; new_root=True
                anchor=bpy.data.objects.new(component.object_name+' / Component',None); created.append(anchor)
                collection.objects.link(anchor); anchor.parent=root_obj; anchor.rotation_mode='YXZ'; component.properties=props; Transform(component,anchor)
                anchor['UE_foliage_anchor']=component.object_name
                objs=build_instances(collection,anchor,mesh,component.object_name,package,rows); created.extend(objs)
                if new_root: roots[id(root)]=root_obj
                record.update(status='reconstructed',instances=len(objs))
            except Exception as exc:
                for obj in reversed(created): bpy.data.objects.remove(obj,do_unlink=True)
                record.update(status='unsupported' if isinstance(exc,(ValueError,NotImplementedError)) else 'failed',detail=str(exc))
            finally: records.append(record)
    return {'components':len(records),'status':dict(Counter(r['status'] for r in records)),'instances':sum(r['instances'] for r in records),'records':records}
