"""Historical comparison oracle only; not installed as production code."""
from foliage_legacy import decode_instances

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


