"""Actual grouped geometry batch, camera driver visibility, and saved-session validation."""
import os,sys,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import skeleton_blender as sb,uproject_browser as browser
from skeletal_lod_group import members
bpy.ops.wm.read_factory_settings(use_empty=True);sb.register();browser.register()
s=bpy.context.scene.ueimport_project;s.project_path=os.environ['UE53_PROJECT'];s.batch_scope='GEOMETRY';s.cooked_profile='5.6';s.geometry_all_lods=True
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'} and len(s.job_items)==1
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[s.batch_report].as_string());r=report['results'][0];assert r['status']=='reconstructed' and len(r['result']['lods'])==3
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE');rows=members(arm);assert len(bpy.data.materials)==2
assert any(m.get('UE_cooked_instance') for m in rows[0].data.materials)
bpy.context.view_layer.objects.active=arm;arm.select_set(True)
c=bpy.data.objects.new('LOD Camera',bpy.data.cameras.new('LOD Camera'));bpy.context.collection.objects.link(c);bpy.context.scene.camera=c
# Camera positioned relative to offset gallery armature.
assert bpy.ops.object.ue_enable_lod_distance(near=5,far=15)=={'FINISHED'}
def check(arm,c):
    rows=members(arm);out=[]
    for distance,i in [(2,0),(5,1),(10,1),(15,2),(20,2),(2,0)]:
        c.location=arm.matrix_world.translation;c.location.x+=distance
        bpy.context.view_layer.update()
        # update driver evaluation even when the hidden object leaves the viewport graph
        bpy.context.scene.frame_set(bpy.context.scene.frame_current+1);bpy.context.view_layer.update()
        vis=[j for j,o in rows.items() if not o.hide_viewport];render=[j for j,o in rows.items() if not o.hide_render]
        assert vis==render==[i],(distance,vis,render)
        out.append([distance,i])
    return out
before=check(arm,c);out=os.environ['UE53_BATCH_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
arm=next(o for o in bpy.data.objects if o.type=='ARMATURE');c=bpy.context.scene.camera;after=check(arm,c);assert before==after
s=bpy.context.scene.ueimport_project;n=len(bpy.data.objects);assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
repeat=json.loads(bpy.data.texts[s.batch_report].as_string());assert repeat['results'][0]['reused'] and len(bpy.data.objects)==n
s.geometry_all_lods=False;assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
stale=json.loads(bpy.data.texts[s.batch_report].as_string());assert stale['results'][0]['status']=='blocked_stale' and len(bpy.data.objects)==n
s.geometry_all_lods=True
rows=members(arm);mod=next(m for m in rows[1].modifiers if m.type=='ARMATURE');mod.object=None
assert bpy.ops.ueimport.batch_import()=={'FINISHED'};damaged=json.loads(bpy.data.texts[s.batch_report].as_string());assert damaged['results'][0]['status']=='blocked_stale' and len(bpy.data.objects)==n
mod.object=arm
bpy.context.view_layer.objects.active=arm;assert bpy.ops.object.ue_set_native_lod(lod=2)=={'FINISHED'}
assert all(o.hide_viewport==o.hide_render==(i!=2) for i,o in rows.items())
assert not any(o.animation_data and len(o.animation_data.drivers) for o in rows.values())
Path(os.environ['UE53_BATCH_REPORT']).write_text(json.dumps(dict(blender=bpy.app.version_string,report=report,repeat=repeat,stale=stale,damaged=damaged,distances=before,persisted_distances=after,manual_return=True),indent=2))
print('NATIVE_LOD_BATCH_PASS',flush=True)
