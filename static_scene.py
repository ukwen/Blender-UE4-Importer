"""Geometry-only static level reconstruction; missing assets stay visible as empties."""
import json
import os
from pathlib import Path
from collections import Counter
import bpy
import uasset
import umesh
import map_layout


class MeshResolver:
    """One native decode per canonical package path, including cached failures."""
    def __init__(self, project):
        self.project = project
        self.cache = {}
        self.records = {}
        self.decode_attempts = 0

    def __call__(self, package):
        if package in self.records:
            record = self.records[package]
            return self.cache.get(record['key']), record['status']
        key = None
        status = 'missing'
        detail = ''
        mesh = None
        try:
            path = Path(self.project.resolve_package(package))
            key = os.path.normcase(str(path.resolve()))
            if key in self.cache:
                mesh = self.cache[key]
                prior = next(r for r in self.records.values() if r['key'] == key)
                status, detail = prior['status'], prior['detail']
            elif not path.is_file():
                detail = 'Package file not found'
            else:
                self.decode_attempts += 1
                existing = {m.as_pointer() for m in bpy.data.meshes}
                asset = uasset.UAsset(str(path), False, self.project)
                try:
                    asset.Read(False)
                    exports = [e for e in asset.exports if e.export_class_type == 'StaticMesh']
                    if len(exports) != 1:
                        raise NotImplementedError('Expected one StaticMesh export')
                    mesh = umesh.ImportStaticMesh(exports[0], import_materials=False, log=False)
                    if mesh is None or not len(mesh.vertices) or not len(mesh.polygons):
                        raise ValueError('No usable native geometry')
                    mesh['UE_mesh_package'] = package
                    mesh['UE_geometry_only'] = True
                    status = 'reconstructed'
                except Exception:
                    for candidate in list(bpy.data.meshes):
                        if candidate.as_pointer() not in existing and candidate.users == 0:
                            bpy.data.meshes.remove(candidate)
                    mesh = None
                    raise
                finally:
                    asset.Close()
        except FileNotFoundError as exc:
            detail = str(exc)
        except (NotImplementedError, AssertionError) as exc:
            status, detail = 'unsupported', str(exc) or 'Unsupported native serialization'
        except Exception as exc:
            status, detail = 'failed', f'{type(exc).__name__}: {exc}'
        if key is not None:
            self.cache[key] = mesh
        self.records[package] = {'key': key, 'status': status, 'detail': detail}
        return mesh, status


def reconstruct_static_map(filepath):
    """Return a new collection plus measured per-actor and per-package results."""
    resolver = MeshResolver(uasset.UProject(filepath))
    collection, report = map_layout.import_layout(filepath, mesh_resolver=resolver)
    counts = Counter(o['UE_geometry_status'] for o in collection.objects)
    report.update(actor_status=dict(counts), decode_attempts=resolver.decode_attempts,
                  unique_reconstructed_meshes=len({o.data.as_pointer() for o in collection.objects if o.type == 'MESH'}),
                  materials_imported=False,
                  dependencies={p: {'status': r['status'], 'detail': r['detail']} for p,r in resolver.records.items()})
    collection['UE_geometry_only'] = True
    collection['UE_reconstructed_actors'] = counts['reconstructed']
    collection['UE_unresolved_actors'] = len(collection.objects) - counts['reconstructed']
    text = bpy.data.texts.new(collection.name + ' - import report.json')
    text.write(json.dumps(report, indent=2, sort_keys=True))
    collection['UE_report'] = text.name
    return collection, report
