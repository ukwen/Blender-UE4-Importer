"""Run with UE_TEST_ASSETS pointing to UAssetAPI.Tests/TestAssets."""
import os, sys, tempfile
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import umat, uasset
from package_inspector import inspect_package
root = Path(os.environ['UE_TEST_ASSETS']) / 'TestEditorAssets'
for file in sorted(root.glob('*.uasset')):
    record = inspect_package(file)
    with uasset.UAsset(str(file)) as asset:
        assert (len(asset.names), len(asset.imports), len(asset.exports)) == (record['name_count'], record['import_count'], record['export_count'])
material, graph = umat.ImportNodeGraph(str(root / 'TestMaterial.uasset'))
assert len(material.node_tree.nodes) == 3 and len(material.node_tree.links) == 2
shader = material.node_tree.nodes.get('Principled BSDF')
assert shader.inputs['Base Color'].is_linked
print('MATERIAL_NODES', [(n.name,n.bl_idname) for n in material.node_tree.nodes])
print('MATERIAL_LINKS', [(l.from_node.name,l.from_socket.name,l.to_node.name,l.to_socket.name) for l in material.node_tree.links])
with tempfile.TemporaryDirectory() as temp:
    material.use_fake_user = True
    target = str(Path(temp)/'real_material.blend')
    bpy.ops.wm.save_as_mainfile(filepath=target)
    bpy.ops.wm.open_mainfile(filepath=target)
    assert len(bpy.data.materials['TestMaterial'].node_tree.links) == 2
print('REAL_MATERIAL_PASS')
