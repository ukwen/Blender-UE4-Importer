"""Import native Quinn LODs on one rig and verify shared animation after reopen."""
import os,sys,json
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import skeleton_blender as sb
from skeletal_lod_group import members,set_active_lod
from ue5_modern_skeletal import read_skeletal56_all
src=next(Path(os.environ['UASSETAPI_ASSETS']).rglob('SKM_Quinn_Simple.uasset'))
data=read_skeletal56_all(src)
bpy.ops.wm.read_factory_settings(use_empty=True);sb.register()
assert getattr(bpy.ops,'import').ue_native_skeletal_mesh(filepath=str(src),profile='5.6',all_lods=True)=={'FINISHED'}
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE');rows=members(arm)
assert len(bpy.data.objects)==4 and len(bpy.data.armatures)==1 and len(bpy.data.materials)==2
assert all(list(o.data.materials)==list(rows[0].data.materials) for o in rows.values())
bpy.context.view_layer.objects.active=arm;arm.select_set(True)
b=arm.pose.bones['spine_01'];b.rotation_mode='XYZ';b.rotation_euler.x=0;b.keyframe_insert('rotation_euler',frame=1);b.rotation_euler.x=.3;b.keyframe_insert('rotation_euler',frame=12);action=arm.animation_data.action
assert action and len(bpy.data.actions)==1
results=[]
for i,o in rows.items():
    assert bpy.ops.object.ue_set_native_lod(lod=i)=={'FINISHED'}
    assert arm['UE_active_lod']==i
    assert all(x.hide_viewport==x.hide_render==(j!=i) for j,x in rows.items())
    bpy.context.scene.frame_set(1);bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
    before=[v.co.copy() for v in o.evaluated_get(dg).data.vertices]
    bpy.context.scene.frame_set(12);bpy.context.view_layer.update(); dg=bpy.context.evaluated_depsgraph_get()
    d=data[i]; matrices=[arm.pose.bones[r['name']].matrix@arm.data.bones[r['name']].matrix_local.inverted() for r in d['bones']]
    ev=o.evaluated_get(dg);error=0.;move=0.;moved=0
    assert len(ev.data.vertices)==len(d['positions'])
    for v,rest,w,e in zip(o.data.vertices,before,d['weights'],ev.data.vertices):
        expected=sum((matrices[j]@v.co*(q/255) for j,q in w.items()),Vector((0,0,0)))
        error=max(error,(e.co-expected).length);dist=(e.co-rest).length;move=max(move,dist);moved+=dist>1e-5
    assert error<1e-5 and moved>0 and arm.animation_data.action==action
    results.append(dict(lod=i,vertices=len(o.data.vertices),triangles=len(o.data.polygons),moved_vertices=moved,max_deformation_error_m=error,max_movement_m=move))
try: set_active_lod(arm,3);raise AssertionError('bad index accepted')
except ValueError: pass
rows[0]['UE_lod_group_member']=False
try: set_active_lod(arm,0);raise AssertionError('bad group accepted')
except ValueError: pass
rows[0]['UE_lod_group_member']=True
assert arm['UE_active_lod']==2 and not rows[2].hide_render
set_active_lod(arm,1);bpy.context.scene.frame_set(12)
out=os.environ['UE53_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE');rows=members(arm);assert arm['UE_active_lod']==1 and arm.animation_data.action is not None
assert all(x.hide_viewport==x.hide_render==(j!=1) for j,x in rows.items())
bpy.context.view_layer.objects.active=arm;assert bpy.ops.object.ue_set_native_lod(lod=0)=={'FINISHED'};assert not rows[0].hide_viewport
assert len(bpy.data.armatures)==1 and len(bpy.data.materials)==2 and len(bpy.data.actions)==1
Path(os.environ['UE53_REPORT']).write_text(json.dumps(dict(blender=bpy.app.version_string,rigs=1,materials=2,actions=1,lods=results,save_reopen=True,damaged_group_rejection=True),indent=2))
print('SHARED_NATIVE_LOD_PASS',results,flush=True)
