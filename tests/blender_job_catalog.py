import bpy,sys,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]));import uproject_browser as b
bpy.ops.wm.read_factory_settings(use_empty=True);b.register();s=bpy.context.scene.ueimport_project
s.project_path=str(Path(os.environ['UE_VEHICLE_PROJECT'])/'Vehicles.uproject');s.batch_scope='GEOMETRY';s.geometry_physics=True
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'} and len(s.job_items)==13
s.use_job_selection=True;assert bpy.ops.ueimport.check_jobs(enabled=False)=={'FINISHED'}
for item in list(s.job_items)[:2]:item.enabled=True
plan=b.make_plan(s);assert len(plan['jobs'])==2 and len(plan['seeds'])==2
assert bpy.ops.ueimport.preflight()=={'FINISHED'} and bpy.ops.ueimport.batch_import()=={'FINISHED'}
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==2
r=json.loads(bpy.data.texts[s.batch_report].as_string());assert len(r['results'])==2 and all(x['result']['physics']['status']=='reconstructed' for x in r['results'])
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'} and sum(i.enabled for i in s.job_items)==2
s.job_filter='Cart'
try:b.make_plan(s);raise AssertionError('stale selection accepted')
except ValueError as e:assert 'stale' in str(e)
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert len(s.job_items)==5 and all(i.enabled for i in s.job_items)
print('CATALOG_SELECTION_PASS',flush=True)
