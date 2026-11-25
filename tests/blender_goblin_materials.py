"""Real partial Goblin project + native simple-material regression."""
import json, os, sys
from pathlib import Path
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import static_scene, material_stage, uasset
bpy.ops.wm.read_factory_settings(use_empty=True)
root = Path(os.environ['GOBLIN_CONTENT'])
map_path = root/'Maps/Overview.umap'
collection, report = static_scene.reconstruct_static_map(str(map_path), materials=True)
assert report['actor_status'] == {'missing':559, 'reconstructed':3}, report['actor_status']
assert report['material_report']['bound_meshes'] == 3, report['material_report']
assert not report['material_report']['errors'], report['material_report']['errors']
for obj in collection.objects:
    if obj.type == 'MESH':
        print('MESH', obj.name, len(obj.data.vertices), len(obj.data.polygons), [m.name for m in obj.data.materials], obj.data['UE_material_bindings'])
        assert len(obj.data.materials) > 0
        assert all(m.get('UE_unresolved_material') for m in obj.data.materials)
        assert len(obj.data.uv_layers)==2
resolver = material_stage.MaterialResolver(uasset.UProject(str(map_path)))
base = '/Game/PolygonGoblinWarCamp/Materials/Base/M_PolygonGoblinWarCamp_Base'
instance = '/Game/PolygonGoblinWarCamp/Materials/MI_PolygonGoblinWarCamp'
for ref in [base, instance]:
    mat=resolver.resolve(ref,'Test')
    assert mat.get('UE_unresolved_material') and mat.get('UE_material_status')=='missing_dependencies'
    assert resolver.resolve(ref,'Other') == mat
    print('MISSING', ref, resolver.records[ref]['missing'])
print('MATERIAL_REPORT',json.dumps(report['material_report']))
output = Path(os.environ['UE_SCENE_OUTPUT'])
bpy.ops.wm.save_as_mainfile(filepath=str(output))
output.with_suffix('.json').write_text(json.dumps(report, indent=2))
print('PASS_PARTIAL_SCENE')
# Genuine simple material in a temporary project verifies the positive path.
import tempfile, shutil
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp); (root/'Content').mkdir(); (root/'Test.uproject').write_text('{}')
    shutil.copy(Path(os.environ['UE_TEST_ASSETS'])/'TestEditorAssets/TestMaterial.uasset',root/'Content/TestMaterial.uasset')
    simple=material_stage.MaterialResolver(uasset.UProject(str(root/'Content/TestMaterial.uasset')))
    m=simple.resolve('/Game/TestMaterial','Simple')
    assert m['UE_material_status']=='graph_imported_unverified', simple.records
    assert len(m.node_tree.nodes)==3 and len(m.node_tree.links)==2
    print('PASS_NATIVE_MATERIAL_GRAPH')
