"""Real wrapper, actual Overview meshes, controlled nonzero-mask evaluation."""
import json, math, os, sys
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import umat, static_scene, wind_preview as wp

root = Path(os.environ['GOBLIN_CONTENT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
with patch.object(umat.subprocess, 'run', side_effect=AssertionError('No UModel')):
    mat, _ = umat.ImportNodeGraph(str(root/'Materials/MI_PolygonGoblinWarCamp.uasset'))
    profile = json.loads(mat['UE_wind_profile'])
    assert profile['mask'] == '1 - vertex color red'
    assert {k:v['material_value'] for k,v in profile['parameters'].items()} == {'WindIntensity':10.,'WindSpeed':0.,'WindStregth':50.}
    assert {k:v['custom_primitive_index'] for k,v in profile['parameters'].items()} == {'WindIntensity':1,'WindSpeed':2,'WindStregth':0}
    lerps = {s['parameter']:s['material_lerp_value'] for s in profile['engine_inputs'] if 'parameter' in s}
    assert abs(lerps['WindIntensity']+180)<1e-6 and abs(lerps['WindStregth']+.98)<1e-6 and lerps['WindSpeed']==.5
    assert not profile['engine_input_semantics_verified'] and not profile['actor_custom_primitive_data_verified']
    assert mat['UE_unresolved_material'] and mat['UE_unimplemented_surface_inputs']=='WorldPositionOffset'
    mat.use_fake_user=True
    collection, report = static_scene.reconstruct_static_map(str(root/'Maps/Overview.umap'), materials=True, allow_partial_materials=True)
assert report['actor_status']=={'missing':559,'reconstructed':3}
objects=[o for o in collection.objects if o.type=='MESH' and 'UE_wind_profile' in o.material_slots[0].material]
assert len(objects)==2
scene=bpy.context.scene; scene.render.fps=24; scene.render.fps_base=1

def evaluated(obj, frame):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh=ev.to_mesh()
    try:
        assert len(mesh.vertices)==len(obj.data.vertices) and len(mesh.polygons)==len(obj.data.polygons)
        return [v.co.copy() for v in mesh.vertices]
    finally: ev.to_mesh_clear()

wp.register()
try:
    bpy.ops.object.select_all(action='DESELECT')
    for obj in objects: obj.select_set(True)
    bpy.context.view_layer.objects.active=objects[0]
    assert bpy.ops.ueimport.wind_preview()=={'FINISHED'}
finally: wp.unregister()
for obj in objects:
    source=[v.co.copy() for v in obj.data.vertices]
    mod, weights=wp.add_preview(obj)
    assert len(obj.modifiers)==1 and max(weights)==0
    assert max((a-b).length for f in (1,13,25,37) for a,b in zip(evaluated(obj,f),source))<1e-7
    p=json.loads(obj.material_slots[0].material['UE_wind_profile'])
    assert p['parameters']['WindSpeed']['material_value']==100 and p['parameters']['WindStregth']['material_value']==100
    assert obj.material_slots[0].material['UE_material_status']=='partial_graph_unresolved'
    print('REAL_ZERO_MASK_PASS',obj.name,len(source))

# Controlled duplicate of genuine mesh, not native actor paint. Keep original immutable.
source_obj=objects[0]; clone=source_obj.copy(); clone.data=source_obj.data.copy(); clone.name='TEST ONLY - edited vertex colors'
collection.objects.link(clone)
for m in list(clone.modifiers): clone.modifiers.remove(m)
red=clone.data.color_attributes['Color']
for loop in clone.data.loops:
    r=(0.,.5,1.)[loop.vertex_index%3]
    red.data[loop.index].color=(r,1,1,1)
mod, weights=wp.add_preview(clone)
assert set(weights)=={0.,.5,1.}
base=[v.co.copy() for v in clone.data.vertices]
max_error=0.; max_displacement=0.
for frame in (1,13,25,37,49):
    result=evaluated(clone,frame)
    for a,b,w in zip(result,base,weights):
        expected=.02*w*math.sin(math.tau*(frame/24*.5+b.x*.5))
        max_error=max(max_error,abs(a.x-b.x-expected),abs(a.y-b.y),abs(a.z-b.z))
        max_displacement=max(max_displacement,abs(a.x-b.x))
assert max_error<2e-6 and max_displacement>.015
assert all(v.co==b for v,b in zip(clone.data.vertices,base))
assert max(wp.vertex_weights(source_obj.data))==0
print('CONTROLLED_MASKED_PREVIEW_PASS',max_error,max_displacement)
# Fail closed on a shared-point color discontinuity, then remove test duplicate.
loop=clone.data.loops[0]; peers=[l for l in clone.data.loops if l.vertex_index==loop.vertex_index]
assert len(peers)>1
red.data[peers[1].index].color=(1-red.data[loop.index].color[0],1,1,1) if red.data[loop.index].color[0]!=.5 else (0,1,1,1)
try: wp.vertex_weights(clone.data)
except NotImplementedError: pass
else: raise AssertionError('Seam accepted')
mesh=clone.data; ng=mod.node_group
bpy.data.objects.remove(clone,do_unlink=True); bpy.data.meshes.remove(mesh); bpy.data.node_groups.remove(ng)
scene.frame_set(1)
out=os.environ['UE_WIND_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out)
print('WIND_PREVIEW_PASS',out)
