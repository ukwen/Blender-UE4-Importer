"""Native classic static actor layout preview; never silently switch decoders."""


def import_layout(filepath, mesh_resolver=None):
    """Read supported classic actor placements, optionally resolving geometry."""
    from package_inspector import inspect_package
    meta = inspect_package(filepath)
    if meta.get('ue4') not in (508, 522) or meta.get('ue5') is not None:
        raise NotImplementedError('Unsupported native classic map layout; no validated native decoder for this profile')
    from classic_layout_blender import import_classic_layout
    return import_classic_layout(filepath, mesh_resolver)
