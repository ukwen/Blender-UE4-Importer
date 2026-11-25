"""Conservative native material binding for static scenes; unresolved slots are explicit."""
import json
from pathlib import Path
import bpy
import uasset


def package_reference(ref):
    """Return the outer package of a native object import, never a basename guess."""
    seen = set()
    while isinstance(ref, uasset.Import) and id(ref) not in seen:
        seen.add(id(ref))
        if ref.object_name.startswith(('/Game/', '/Engine/')):
            return ref.object_name
        ref = ref.import_ref
    return ''


class MaterialResolver:
    def __init__(self, project):
        self.project = project
        self.cache = {}
        self.records = {}

    def audit(self, package):
        visited, missing, errors = set(), set(), {}
        def visit(ref):
            if ref in visited:
                return
            if len(visited) >= 2048:
                errors[ref] = 'Dependency limit reached'
                return
            visited.add(ref)
            asset = None
            try:
                path = Path(self.project.resolve_package(ref))
                if not path.is_file():
                    missing.add(ref)
                    return
                asset = uasset.UAsset(str(path), False, self.project)
                asset.Read(False)
                for imp in asset.imports:
                    if imp.class_name == 'Package' and imp.object_name.startswith(('/Game/', '/Engine/')):
                        visit(imp.object_name)
            except FileNotFoundError:
                missing.add(ref)
            except Exception as exc:
                errors[ref] = f'{type(exc).__name__}: {exc}'
            finally:
                if asset is not None:
                    asset.Close()
        if package:
            visit(package)
        return {'packages': sorted(visited), 'missing': sorted(missing), 'errors': errors}

    def resolve(self, package, slot):
        key = package or ('unbound', slot)
        if key in self.cache:
            return self.cache[key]
        record = self.audit(package)
        mat = None
        status = 'unbound' if not package else 'missing_dependencies' if record['missing'] else 'unsupported_dependencies' if record['errors'] else 'graph_failed'
        if package and not record['missing'] and not record['errors']:
            import umat
            before = {m.as_pointer() for m in bpy.data.materials}
            try:
                mat, _ = umat.ImportNodeGraph(self.project.resolve_package(package), self.project)
                if not isinstance(mat, bpy.types.Material) or not mat.node_tree:
                    raise ValueError('Not a material graph')
                if mat.node_tree.get('Error') or any(n.type == 'TEX_IMAGE' and n.image is None for n in mat.node_tree.nodes):
                    raise ValueError('Incomplete graph or missing image')
                status = 'graph_imported_unverified'
            except Exception as exc:
                record['errors']['graph'] = f'{type(exc).__name__}: {exc}'
                mat = None
                for candidate in list(bpy.data.materials):
                    if candidate.as_pointer() not in before and candidate.users == 0:
                        bpy.data.materials.remove(candidate)
        if mat is None:
            mat = bpy.data.materials.new('UNRESOLVED - ' + (package.rsplit('/', 1)[-1] if package else slot))
            mat.diffuse_color = (0.5, 0.5, 0.5, 1)
            mat['UE_unresolved_material'] = True
        mat['UE_material_package'] = package
        mat['UE_material_status'] = status
        record['status'] = status
        self.records[package or '<unbound> ' + slot] = record
        self.cache[key] = mat
        return mat


def bind_scene_materials(collection, project):
    resolver = MaterialResolver(project)
    bound = set()
    errors = []
    for obj in collection.objects:
        if obj.type != 'MESH':
            continue
        mesh = obj.data
        if mesh.as_pointer() not in bound:
            bindings = json.loads(mesh.get('UE_material_bindings', '[]'))
            if not bindings:
                errors.append({'mesh': mesh.name, 'error': 'No source material bindings decoded'})
                continue
            names = [name for name, _ in bindings]
            mapping = None
            if mesh.get('UE_source_format') == 'Legacy FMeshDescription':
                groups = zip(mesh['UE_polygon_group_ids'], mesh['UE_material_slots'])
                mapping = {g: names.index(n) for g, n in groups if names.count(n) == 1}
                if len(mapping) != len(mesh['UE_polygon_group_ids']):
                    errors.append({'mesh': mesh.name, 'error': 'Ambiguous polygon group binding'})
                    continue
            mesh.materials.clear()
            for slot, package in bindings:
                mesh.materials.append(resolver.resolve(package, slot))
            if mapping is not None:
                for poly, group in zip(mesh.polygons, mesh.attributes['UE_polygon_group'].data):
                    poly.material_index = mapping[group.value]
            bound.add(mesh.as_pointer())
        overrides = json.loads(obj.get('UE_material_override_packages', '[]'))
        for i, package in enumerate(overrides):
            if not package:
                continue
            if i >= len(obj.material_slots):
                errors.append({'actor': obj.name, 'error': 'Override index outside source slots', 'index': i})
                continue
            slot = obj.material_slots[i]
            slot.link = 'OBJECT'
            slot.material = resolver.resolve(package, slot.name)
    return {'bound_meshes': len(bound), 'packages': resolver.records, 'errors': errors}
