"""Run with Blender 4.2.4, UE_ROPE_ASSET set to original user fixture."""
import os, sys, tempfile
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import umesh
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = umesh.ImportMeshUAsset(os.environ['UE_ROPE_ASSET'], import_materials=False)
assert (len(mesh.vertices), len(mesh.edges), len(mesh.polygons), len(mesh.loops)) == (32,90,60,180)
assert mesh.has_custom_normals
assert [uv.name for uv in mesh.uv_layers] == ['UV0','UV1']
assert list(mesh['UE_material_slots']) == ['Goblin_01_A219']
assert mesh.color_attributes['Color'].domain == 'CORNER'
assert all(p.normal.dot(mesh.corner_normals[i].vector)>0 for p in mesh.polygons for i in p.loop_indices)
obj = bpy.data.objects.new(mesh.name, mesh)
bpy.context.collection.objects.link(obj)
with tempfile.TemporaryDirectory() as tmp:
    path = str(Path(tmp)/'rope.blend')
    bpy.ops.wm.save_as_mainfile(filepath=path)
    bpy.ops.wm.open_mainfile(filepath=path)
    m = bpy.data.meshes['SM_Prop_Rope_01']
    assert (len(m.vertices), len(m.polygons), len(m.uv_layers)) == (32,60,2)
    assert m.has_custom_normals
print('ROPE_NATIVE_PASS')
