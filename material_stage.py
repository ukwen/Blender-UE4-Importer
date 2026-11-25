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


def incomplete_graph(tree, seen=None):
    seen = set() if seen is None else seen
    if tree.as_pointer() in seen: return False
    seen.add(tree.as_pointer())
    if tree.get('Error'): return True
    for node in tree.nodes:
        if node.type == 'TEX_IMAGE' and node.image is None: return True
        if node.type == 'GROUP' and (node.node_tree is None or incomplete_graph(node.node_tree, seen)): return True
    return False


def connected_surface(tree):
    """Conservative partial preview gate: require active surface and no missing upstream images/groups.

    A connected graph is not proof of equivalence. Unresolved nodes on other paths
    or unsupported surface semantics remain reported by the importer.
    """
    outputs = [n for n in tree.nodes if n.type == 'OUTPUT_MATERIAL' and n.is_active_output]
    if len(outputs) != 1 or not outputs[0].inputs['Surface'].is_linked:
        return False
    pending = [link.from_node for link in outputs[0].inputs['Surface'].links]
    seen = set()
    while pending:
        node = pending.pop()
        if node.as_pointer() in seen: continue
        seen.add(node.as_pointer())
        if node.type == 'TEX_IMAGE' and node.image is None: return False
        if node.type == 'GROUP' and (node.node_tree is None or incomplete_graph(node.node_tree)): return False
        for socket in node.inputs:
            pending.extend(link.from_node for link in socket.links)
    return True


class MaterialResolver:
    def __init__(self, project, allow_partial=False):
        self.project = project
        self.allow_partial = allow_partial
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
        if package and not record['errors'] and (not record['missing'] or (self.allow_partial and package not in record['missing'])):
            import umat
            # Keep the bundled node library out of the failed-import transaction.
            umat.TryAppendNodeGroups()
            stores = (bpy.data.materials, bpy.data.node_groups, bpy.data.images)
            before = {item.as_pointer() for store in stores for item in store}
            try:
                mat, _ = umat.ImportNodeGraph(self.project.resolve_package(package), self.project)
                if not isinstance(mat, bpy.types.Material) or not mat.node_tree:
                    raise ValueError('Not a material graph')
                if incomplete_graph(mat.node_tree) or record['missing']:
                    if not self.allow_partial or not connected_surface(mat.node_tree):
                        raise ValueError('Incomplete graph or missing image')
                    status = 'partial_graph_unresolved'
                    mat['UE_unresolved_material'] = True
                else:
                    status = 'graph_imported_unverified'
            except Exception as exc:
                record['errors']['graph'] = f'{type(exc).__name__}: {exc}'
                mat = None
                created = [item for store in stores for item in store if item.as_pointer() not in before]
                if created:
                    bpy.data.batch_remove(ids=created)
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


def bind_scene_materials(collection, project, allow_partial=False):
    resolver = MaterialResolver(project, allow_partial=allow_partial)
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
            elif mesh.attributes.get('UE_source_material_index') is not None:
                for poly,entry in zip(mesh.polygons,mesh.attributes['UE_source_material_index'].data):
                    poly.material_index = entry.value
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
    return {'bound_meshes': len(bound), 'packages': resolver.records, 'errors': errors,
            'allow_partial': allow_partial}
