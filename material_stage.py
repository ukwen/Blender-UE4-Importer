"""Conservative native material binding for static scenes; unresolved slots are explicit."""
import json
from pathlib import Path
import bpy
from reference_identity import package_reference


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
                from package_inspector import inspect_package
                meta=inspect_package(path)
                if meta.get('ue4') in (508,522) and (meta.get('ue5') is None or meta.get('ue5') in (1004,1012,1013,1014,1015,1016,1017,1018)) and not meta.get('sidecars') and not meta.get('flags',0)&0x80002000:
                    from package_records import read_package
                    _,_,table=read_package(path)
                    refs=[i.name for i in table.imports if i.kind=='Package']
                else:
                    from uasset import UAsset
                    asset=UAsset(str(path),False,self.project);asset.Read(False)
                    refs=[i.object_name for i in asset.imports if i.class_name=='Package']
                for name in refs:
                    if name.startswith(('/Game/','/Engine/')): visit(name)
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
            stores = (bpy.data.materials, bpy.data.node_groups, bpy.data.images)
            before = {item.as_pointer() for store in stores for item in store}
            try:
                path=self.project.resolve_package(package)
                from package_inspector import inspect_package
                meta=inspect_package(path); classic=None; graph=False
                if meta.get('ue4') in (508,522) and meta.get('ue5') is None:
                    from classic_material import read_material
                    try: classic=read_material(path)
                    except NotImplementedError:
                        if meta['ue4']==522:
                            from classic_material_graph import read_graph
                            try: graph=read_graph(path)['kind'] in ('material','instance')
                            except NotImplementedError: pass
                elif meta.get('ue5') in (1004,1012,1013,1014,1015,1016,1017,1018) and not meta.get('sidecars') and not meta.get('flags',0)&0x80002000:
                    graph=True
                if classic is not None:
                    from classic_material import build_material
                    mat=build_material(self.project,path,classic)
                elif graph and package.startswith('/Game/'):
                    from ue5_editor_material import build_material
                    mat=build_material(Path(self.project.dir)/'Content',package,self.allow_partial)
                else:
                    import umat
                    umat.TryAppendNodeGroups()
                    mat,_=umat.ImportNodeGraph(path,self.project)
                if not isinstance(mat, bpy.types.Material) or not mat.node_tree:
                    raise ValueError('Not a material graph')
                if mat.get('UE_editor_material_status')=='metadata_only':
                    raise ValueError('Unresolved source graph; partial preview disabled')
                if incomplete_graph(mat.node_tree) or record['missing'] or mat.get('UE_editor_material_status')=='partial':
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
