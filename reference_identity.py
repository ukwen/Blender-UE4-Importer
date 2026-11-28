"""External package identity for typed views and the temporary legacy bridge."""
def package_reference(ref):
    from classic_map_records import MapEntry
    if isinstance(ref, MapEntry):
        return ref.package_identity
    if ref is None:
        return ''
    # Kept solely for remaining legacy callers until their migration.
    from uasset import Import
    seen=set()
    while isinstance(ref,Import) and id(ref) not in seen:
        seen.add(id(ref))
        if ref.object_name.startswith(('/Game/','/Engine/')):
            return ref.object_name
        ref=ref.import_ref
    return ''
