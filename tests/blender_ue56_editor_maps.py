"""Original ShooterSam World Partition root static actor reconstruction."""
import json,os,sys,math
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_scene import placement_records
from project_preflight import preflight
from static_scene import reconstruct_static_map
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']); output=Path(os.environ['UE56_EDITOR_OUTPUT']);root=project.parent/'Content'
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
report={}; objects=0
for rel,n,expected in [('ThirdPerson/Lvl_ThirdPerson.umap',65,55),('Variant_Platforming/Lvl_Platforming.umap',144,135),('Variant_SideScrolling/Lvl_SideScrolling.umap',118,91),('Variant_Combat/Lvl_Combat.umap',138,67)]:
    path=root/rel; plan=preflight(str(project),'MAP_GEOMETRY',selected=str(path)); data=placement_records(root,path)
    assert len(data['records'])==expected and data['external_count']==n and not data['skipped'];assert len(plan['jobs'])>=4
    collection,r=reconstruct_static_map(str(path),cooked_profile='5.6'); assert len(collection.objects)==expected
    assert r['actor_status'].get('reconstructed',0)==sum(v['package'].startswith('/Game/') for v in data['records']),r
    lookup={(o['UE_source_actor_package'],o['UE_actor']):o for o in collection.objects}; err=0.;world_error=0.
    # Independent UE FRotator matrix (yaw Z, pitch Y with reversed sign, roll X reversed sign).
    swap=Matrix(((0,1,0),(1,0,0),(0,0,1)))
    for v in data['records']:
        o=lookup[(v['source'],v['actor'])];t,p,s=v['fields']['RelativeLocation'],v['fields']['RelativeRotation'],v['fields']['RelativeScale3D']
        err=max(err,*(abs(a-b) for a,b in zip(o.location,(t[1]*.01,t[0]*.01,t[2]*.01))))
        pitch,yaw,roll=map(math.radians,p)
        expected_rot=swap @ Matrix.Rotation(yaw,3,'Z') @ Matrix.Rotation(-pitch,3,'Y') @ Matrix.Rotation(-roll,3,'X') @ swap
        world_error=max(world_error,max(abs(a-b) for ar,br in zip(o.rotation_euler.to_matrix(),expected_rot) for a,b in zip(ar,br)))
        assert tuple(o.scale)==tuple(Vector((s[1],s[0],s[2])))
        if v['overrides'] and v['overrides'][0] and o.type=='MESH': assert o.material_slots[0].material.get('UE_material_package')==v['overrides'][0]
    assert err<1e-4 and world_error<1e-5,(err,world_error)
    report[rel]=dict(external_packages=n,static=r['actor_status'],mesh_count=r['unique_reconstructed_meshes'],decode_attempts=r['decode_attempts'],position_error_m=err,rotation_matrix_error=world_error,dependency_geometry_jobs=len(plan['jobs']),nonroot_component_classes=r['nonroot_component_classes'])
    objects+=len(collection.objects)
# Test tracked batch map independently; clean direct copy for same level to avoid ambiguity.
s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.batch_scope='ALL_MAPS';s.cooked_profile='5.6';s.job_filter='Lvl_ThirdPerson';assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert len(s.job_items)==1
assert bpy.ops.ueimport.batch_import()=={'FINISHED'};r=json.loads(bpy.data.texts[s.batch_report].as_string());assert r['results'][0]['status']=='completed'
n=len(bpy.data.objects);bpy.ops.wm.save_as_mainfile(filepath=str(output));bpy.ops.wm.open_mainfile(filepath=str(output));s=bpy.context.scene.ueimport_project
assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};r=json.loads(bpy.data.texts[s.batch_report].as_string());assert r['results'][0].get('reused') and len(bpy.data.objects)==n
output.with_suffix('.json').write_text(json.dumps({'maps':report,'batch_reuse':True},indent=2));print('EDITOR_MAP_PASS',objects,flush=True)
