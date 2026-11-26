"""Real asset saved-scene recovery and stale detection."""
import bpy,sys,os,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from project_preflight import preflight
from project_session import run_session,TAG,new_ids
import static_scene
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
west=Path(os.environ['UE_WESTERN_PROJECT']);desc=next(west.glob('*.uproject'));plan=preflight(str(desc));assert len(plan['jobs'])==2
soft=[(k,v['soft_references']) for k,v in plan['records'].items() if v['soft_references']];print('SOFT',len(soft),soft[:3],flush=True);assert soft
s=bpy.context.scene.ueimport_project;s.project_path=str(desc);s.components=True;s.static_materials=True;s.job_filter='Demonstration'
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[s.batch_report].as_string());print('FIRST',[(r['status'],r.get('detail')) for r in report['results']],flush=True);assert len(report['results'])==1 and report['results'][0]['status']=='completed'
first=report['results'][0];assert first['static']['reconstructed']==1994 and first['foliage']==462
out=os.environ['UE_SESSION_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
s=bpy.context.scene.ueimport_project;s.job_filter='';assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[s.batch_report].as_string());print('RESUME',[(r['status'],r.get('reused'),r.get('detail')) for r in report['results']],flush=True)
assert len(report['results'])==2 and sum(bool(r.get('reused')) for r in report['results'])==1 and all(r['status']=='completed' for r in report['results'])
assert sum(r['static']['reconstructed'] for r in report['results'])==2316 and sum(r['components']['reconstructed'] for r in report['results'])==36
n=len(bpy.data.objects);assert bpy.ops.ueimport.batch_import()=={'FINISHED'};repeat=json.loads(bpy.data.texts[s.batch_report].as_string());assert all(r.get('reused') for r in repeat['results']) and len(bpy.data.objects)==n
bpy.ops.wm.save_as_mainfile(filepath=out)
s.static_materials=False;assert bpy.ops.ueimport.batch_import()=={'FINISHED'};blocked=json.loads(bpy.data.texts[s.batch_report].as_string());assert all(r['status']=='blocked_stale' for r in blocked['results']) and len(bpy.data.objects)==n
s.static_materials=True;col=bpy.data.collections[first['collection']];bpy.data.objects.remove(list(col.all_objects)[0],do_unlink=True);assert bpy.ops.ueimport.batch_import()=={'FINISHED'};damaged=json.loads(bpy.data.texts[s.batch_report].as_string());assert sum(r['status']=='blocked_stale' for r in damaged['results'])==1
bpy.ops.wm.read_factory_settings(use_empty=True);desc=Path(os.environ['UE_VEHICLE_PROJECT'])/'Vehicles.uproject';plan=preflight(str(desc),'GEOMETRY');assert len(plan['jobs'])==13 and any(v['soft_references'] for v in plan['records'].values())
it=run_session(plan,physics=True);early=[next(it),next(it)];it.close();print('EARLY',[(r['status'],r.get('detail')) for r in early],flush=True);assert all(r['status']=='reconstructed' for r in early) and sum(o.type=='ARMATURE' for o in bpy.data.objects)==2
vout=os.environ['UE_VEHICLE_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=vout);bpy.ops.wm.open_mainfile(filepath=vout)
results=list(run_session(plan,physics=True));print('VEH',[(r['status'],r.get('reused'),r.get('detail')) for r in results],flush=True);assert len(results)==13 and sum(bool(r.get('reused')) for r in results)==2 and all(r['result']['physics']['status']=='reconstructed' for r in results)
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==13
ends=sorted(c['UE_batch_gallery_end'] for c in bpy.context.scene.collection.children_recursive if c.get(TAG));assert len(set(ends))==13
old=desc.read_bytes();desc.write_bytes(old+b'\n')
try: stale=list(run_session(plan,physics=True));assert all(r['status']=='blocked_stale' for r in stale)
finally: desc.write_bytes(old)
bpy.ops.wm.save_as_mainfile(filepath=vout)
bpy.ops.wm.read_factory_settings(use_empty=True);sentinel=bpy.data.objects.new('Sentinel',None);bpy.context.collection.objects.link(sentinel)
orig=static_scene.reconstruct_static_map
def broken(*a,**k):
    c=bpy.data.collections.new('bad');bpy.context.scene.collection.children.link(c);d=bpy.data.cameras.new('bad');o=bpy.data.objects.new('bad',d);c.objects.link(o);raise RuntimeError('injected')
static_scene.reconstruct_static_map=broken
try:
    p=preflight(str(next(west.glob('*.uproject'))),'ALL_MAPS',job_filter='Demonstration');before=set(new_ids());failed=list(run_session(p));assert failed[0]['status']=='failed' and set(new_ids())==before
finally:static_scene.reconstruct_static_map=orig
assert bpy.data.objects.get('Sentinel')==sentinel
Path(os.environ['UE_SESSION_REPORT']).write_text(json.dumps(dict(western=report,repeat=repeat,blocked_settings=blocked,blocked_members=damaged,vehicles=results,soft_count=len(soft),source_change='passed',rollback_new_ids='passed'),indent=2));print('SESSION_PASS',flush=True)
