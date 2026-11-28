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
    from package_inspector import inspect_package
    meta = inspect_package(filepath)
    if meta.get('ue4') == 508 and meta.get('ue5') is None:
        from classic_foliage import reconstruct_classic_foliage
        return reconstruct_classic_foliage(filepath, collection, resolver)
    if meta.get('ue4') == 522 and meta.get('ue5') is None:
        from package_records import read_package
        _,_,table=read_package(filepath)
        records=[dict(component=e.name,package='',instances=0,status='unsupported',detail='Unsupported foliage export profile') for e in table.exports if e.kind=='FoliageInstancedStaticMeshComponent']
        return dict(components=len(records),status={'unsupported':len(records)} if records else {},instances=0,records=records)
    raise NotImplementedError('Native foliage package profile unsupported; no legacy fallback')
