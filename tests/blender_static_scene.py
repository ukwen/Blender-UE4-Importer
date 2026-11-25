"""Native partial-project integration test. GOBLIN_CONTENT points to supplied fixture."""
import json, os, sys, tempfile
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import static_scene, uasset, uproject_browser
bpy.ops.wm.read_factory_settings(use_empty=True)
root = Path(os.environ['GOBLIN_CONTENT'])
map_path = root / 'Maps/Overview.umap'
package = '/Game/PolygonGoblinWarCamp/Meshes/Props/SM_Prop_Rope_01'
resolver = static_scene.MeshResolver(uasset.UProject(str(map_path)))
a, status = resolver(package)
b, status2 = resolver(package)
assert a == b and status == status2 == 'reconstructed' and resolver.decode_attempts == 1
assert (len(a.vertices),len(a.polygons)) == (32,60)
bpy.data.meshes.remove(a)
uproject_browser.register()
try:
    state = bpy.context.scene.ueimport_project
    state.project_path = str(root.parents[1]/'Goblin.uproject')
    assert bpy.ops.ueimport.scan_project() == {'FINISHED'}
    assert bpy.ops.ueimport.reconstruct_static() == {'FINISHED'}
finally:
    uproject_browser.unregister()
collection = next(c for c in bpy.data.collections if c.get('UE_geometry_only'))
report = json.loads(bpy.data.texts[collection['UE_report']].as_string())
print('COUNTS', report['actor_status'], 'attempts', report['decode_attempts'], 'unique', report['unique_reconstructed_meshes'])
assert len(collection.objects) == report['static_actors'] == 562
assert report['actor_status'] == {'missing':562}
assert report['decode_attempts'] == report['unique_reconstructed_meshes'] == 0
assert not report['skipped'] and not report['unresolved_parents']
assert package not in report['dependencies']
assert all(o['UE_preview_only'] and o.type == 'EMPTY' for o in collection.objects)
# Controlled routing fixture: use the genuine rope for two test actors only.
# Never presented as original level geometry; production resolver is unchanged.
real_resolver = static_scene.MeshResolver(uasset.UProject(str(map_path)))
selected = sorted(report['dependencies'])[:2]
def route_fixture(ref):
    if ref in selected:
        return real_resolver(package)
    return None, 'layout_only'
fixture, fixture_report = static_scene.map_layout.import_layout(str(map_path), mesh_resolver=route_fixture)
fixture.name = 'TEST ONLY - surrogate rope routing'
objects = [o for o in fixture.objects if o.type == 'MESH']
assert len(objects) == 2 and objects[0].data == objects[1].data
assert real_resolver.decode_attempts == 1
assert (len(objects[0].data.vertices),len(objects[0].data.polygons),len(objects[0].data.uv_layers)) == (32,60,2)
for obj in objects:
    original = next(o for o in collection.objects if o['UE_actor'] == obj['UE_actor'])
    assert obj.matrix_basis == original.matrix_basis
for obj in list(fixture.objects):
    bpy.data.objects.remove(obj, do_unlink=True)
bpy.data.collections.remove(fixture)
for mesh in list(bpy.data.meshes):
    if mesh.users == 0: bpy.data.meshes.remove(mesh)
print('PASS real rope shared by two controlled test actors, original transforms retained')
path = os.environ.get('UE_SCENE_OUTPUT', str(Path(tempfile.gettempdir())/'overview_partial.blend'))
bpy.ops.wm.save_as_mainfile(filepath=path)
print('STATIC_SCENE_PASS', path)
