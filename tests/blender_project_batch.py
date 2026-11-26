"""Run against original Western Frontier project and a reconstructed vehicle package tree."""
import bpy,sys,os,pathlib,json,shutil,collections
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from project_preflight import preflight
from project_batch import run_jobs
from physics_native import read_physics,mesh_physics_reference
import uproject_browser as browser
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True)
west=Path(os.environ['UE_WESTERN_PROJECT']); desc=next(west.glob('*.uproject'))
plan=preflight(str(desc));print('WEST_PREFLIGHT',plan['inventory_count'],plan['closure_count'],plan['dependency_counts'],plan['coverage_counts'],flush=True)
assert plan['inventory_count']==452 and len(plan['jobs'])==2
assert '/Engine/BasicShapes/Cube' in plan['dependencies']
assert not bpy.data.objects
browser.register();state=bpy.context.scene.ueimport_project;state.project_path=str(desc);state.batch_scope='ALL_MAPS';state.components=True;state.static_materials=True
assert bpy.ops.ueimport.preflight()=={'FINISHED'}
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[state.batch_report].as_string());print('WEST_BATCH',[(r['status'],r.get('static'),r.get('foliage'),r.get('components')) for r in report['results']],flush=True)
assert report['status']=='completed' and report['unprocessed']==0
assert sum(r['static']['reconstructed'] for r in report['results'])==2316
assert sum(r['foliage'] for r in report['results'])==462
assert sum(r['components']['reconstructed'] for r in report['results'])==36
out=os.environ['UE_BATCH_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
assert len([o for o in bpy.data.objects if o.type=='ARMATURE'])==36
assert json.loads(bpy.data.texts[bpy.context.scene.ueimport_project.batch_report].as_string())['status']=='completed'
# Separate vehicle project, native package paths recovered from source records.
bpy.ops.wm.read_factory_settings(use_empty=True)
# Factory reset can leave registered classes, but properties may be recreated.
project=Path(os.environ['UE_VEHICLE_PROJECT']);content=project/'Content';project.mkdir(parents=True,exist_ok=True);desc=project/'Vehicles.uproject';desc.write_text('{"EngineAssociation":"4.27"}')
for p in sorted(Path(os.environ['UE_VEHICLE_PHYSICS']).glob('PHYS_Veh*.uasset')):
    d=read_physics(p);source=Path(os.environ['UE_VEHICLE_MESHES'])/(d['preview_mesh'].rsplit('/',1)[-1]+'.uasset');ref=mesh_physics_reference(source)
    for src,key in [(source,d['preview_mesh']),(p,ref)]:
        dest=content/(key[6:]+'.uasset');dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest)
plan=preflight(str(desc),'GEOMETRY');assert len(plan['jobs'])==13 and plan['inventory_count']==26
print('VEH_PREFLIGHT',plan['dependency_counts'],plan['coverage_counts'],flush=True)
# Stop after two real native jobs. Completed objects and gallery report must remain.
it=run_jobs(plan,physics=True);first=[next(it),next(it)];it.close();assert all(r['status']=='reconstructed' and r['result']['physics']['status']=='reconstructed' for r in first)
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==2
assert len([t for t in bpy.data.texts if 'report.json' in t.name])==1
print('STOP_BOUNDARY_PASS',flush=True)
# New empty scene, all jobs through the actual operator.
bpy.ops.wm.read_factory_settings(use_empty=True);state=bpy.context.scene.ueimport_project;state.project_path=str(desc);state.batch_scope='GEOMETRY';state.geometry_physics=True
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
veh=json.loads(bpy.data.texts[state.batch_report].as_string());assert len(veh['results'])==13 and all(r['result']['physics']['status']=='reconstructed' for r in veh['results'])
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==13
print('VEH_BATCH_PASS',flush=True)
Path(os.environ['UE_BATCH_REPORT']).write_text(json.dumps(dict(western=report,vehicles=veh,stop_after_two='passed',save_reopen='passed'),indent=2))
