import sys, json, pathlib, hashlib, os
from unittest.mock import patch
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import bpy,uasset,umat,editor_texture,material_stage,static_scene
root=pathlib.Path(os.environ['GOBLIN_CONTENT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
with patch.object(umat.subprocess,'run',side_effect=AssertionError('No UModel allowed')):
 for p in sorted(root.rglob('T_*.uasset')):
  png,meta=editor_texture.read_editor_texture(p); assert meta['width']==meta['height']==4096; print('SOURCE',p.name,len(png),hashlib.sha256(png).hexdigest(),meta)
 path=root/'Materials/MI_PolygonGoblinWarCamp.uasset'; mat,g=umat.ImportNodeGraph(str(path)); hist=json.loads(mat['UE_instance_overrides']); assert [len(h['applied']) for h in hist]==[12,8]; print('HISTORY',hist)
 assert len(json.loads(mat['UE_instance_chain']))==2
 for k,v in [('Roughness',.85),('Metallic',1),('WindSpeed',0)]: assert abs(g.param_nodes[k][0].node.outputs[0].default_value-v)<1e-6
 assert material_stage.connected_surface(mat.node_tree)
 for n in mat.node_tree.nodes:
  if n.type=='TEX_IMAGE':
   assert n.image and n.image.packed_file and tuple(n.image.size)==(4096,4096); print('IMAGE',n.label,n['UE_texture_package'],n.image.name,n.image.colorspace_settings.name,n.image.get('flip_y'))
 assert len([n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE'])==3
 mat.use_fake_user=True
 c,r=static_scene.reconstruct_static_map(str(root/'Maps/Overview.umap'),materials=True,allow_partial_materials=True)
 print('REPORT',r['material_report']); assert r['actor_status']=={'missing':559,'reconstructed':3}
 meshes=[o for o in c.objects if o.type=='MESH']; print('MESHES',[(o.name,[m.get('UE_material_status') for m in o.data.materials]) for o in meshes]); assert sum(o.data.materials[0]['UE_material_status']=='partial_graph_unresolved' for o in meshes)==2
 assert sum(o.data.materials[0]['UE_material_status']=='missing_dependencies' for o in meshes)==1
 assert len([i for i in bpy.data.images if i.get('UE_editor_texture_key')])==3
 output=pathlib.Path(os.environ['UE_SCENE_OUTPUT'])
 bpy.ops.wm.save_as_mainfile(filepath=str(output))
 output.with_suffix('.json').write_text(json.dumps(r,indent=2))
 print('ACCEPT_113_PASS')
