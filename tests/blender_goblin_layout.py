"""Run in Blender 4.2.4 with GOBLIN_CONTENT pointing to PolygonGoblinWarCamp."""
import os, sys, tempfile
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import map_layout, umesh
bpy.ops.wm.read_factory_settings(use_empty=True)
root = Path(os.environ['GOBLIN_CONTENT'])
try:
    umesh.ImportMeshUAsset(str(root/'Meshes/Props/SM_Prop_Rope_01.uasset'), import_materials=False)
except NotImplementedError as exc:
    assert 'Unsupported mesh payload layout (32, -1)' in str(exc)
else:
    raise AssertionError('Unsupported layout falsely accepted')
assert len(bpy.data.meshes) == 0
collection, report = map_layout.import_layout(str(root/'Maps/Overview.umap'))
assert report['static_actors'] == report['unique_mesh_packages'] == 562
assert not report['skipped'] and not report['unresolved_parents']
assert len(collection.objects) == 562
obj = next(o for o in collection.objects if o['UE_actor']=='SM_Bld_Barracks_01_165')
assert abs(obj.location.y-30)<1e-6 and abs(obj.location.z-.8358)<.0001
with tempfile.TemporaryDirectory() as tmp:
    path = str(Path(tmp)/'overview.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    assert sum(bool(o.get('UE_preview_only')) for o in bpy.data.objects)==562
print('GOBLIN_LAYOUT_PASS')
