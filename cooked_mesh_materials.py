"""Bind verified cooked material package identities to native mesh slots.

No inferred texture roles, no legacy fallback, no cross-project material reuse.
Dependency-only materials remain explicitly unresolved; surface preview is opt-in.
"""
import json
from pathlib import Path

from cooked_material_catalog import PROFILES, import_cooked_material
from material_stage import bind_native_mesh_slots


class CookedSlotResolver:
    def __init__(self, project, profile, allow_partial=False):
        self.project = project
        self.profile = profile
        self.allow_partial = allow_partial
        self.cache = {}
        self.records = {}

    def resolve(self, package, slot):
        import bpy
        key = package or ('unbound', slot)
        if key in self.cache:
            return self.cache[key]
        mat = None
        record = {'package': package, 'status': 'unresolved', 'detail': ''}
        try:
            if not package:
                raise ValueError('Source slot has no package identity')
            path = Path(self.project.resolve_package(package))
            if not path.is_file():
                raise FileNotFoundError('Source material package unavailable: '+package)
            mat = import_cooked_material(path, self.profile, self.allow_partial)
            if mat.get('UE_material_package') != package:
                raise RuntimeError('Cooked material identity mismatch')
            mat.use_fake_user = False
            record['status'] = mat['UE_material_status']
            record['dependencies'] = json.loads(mat['UE_cooked_material_dependencies'])
            record['detail'] = mat.get('UE_cooked_preview_issue', 'Source shader unresolved')
        except (OSError, ValueError, NotImplementedError) as exc:
            record['detail'] = str(exc)
        if mat is None:
            mat = bpy.data.materials.new('UNRESOLVED - '+(package.rsplit('/',1)[-1] if package else slot))
            mat['UE_material_package'] = package
            mat['UE_material_status'] = 'shader_unresolved'
        mat['UE_unresolved_material'] = True
        self.cache[key] = mat
        self.records[package or '<unbound> '+slot] = record
        return mat


def bind_cooked_objects(objects, project, profile, materials, allow_partial=False):
    """Bind only source slots, retaining original polygon indices and editable geometry.

    Require an original project context rather than guessing paths for loose files.
    A shared resolver is scoped to a single mesh import transaction.
    """
    supported = profile in PROFILES and project.descriptor is not None and all(
        Path(o["UE_source_package"]).is_relative_to((Path(project.dir)/"Content").resolve()) for o in objects)
    # Avoid applying a UV0 graph to geometry that cannot supply its source UV set.
    preview = allow_partial and all(o.data.uv_layers.get('UV0') is not None for o in objects)
    resolver = CookedSlotResolver(project, profile, preview) if materials and supported else None
    for obj in objects:
        mesh = obj.data
        if resolver and len(mesh.materials):
            bind_native_mesh_slots(mesh, resolver)
        obj['UE_unresolved_material'] = bool(materials and len(mesh.materials))
        obj['UE_cooked_material_status'] = ('source slot bindings; shader equivalence unresolved' if resolver else
            'slot identities only; no supported project material profile' if materials else 'material reconstruction disabled')
    if resolver:
        report = json.dumps(resolver.records, sort_keys=True)
        for obj in objects:
            obj['UE_material_report'] = report
    return objects
