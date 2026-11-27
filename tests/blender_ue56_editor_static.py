"""Native original ShooterSam UE5.6 static source geometry acceptance."""
import json,os,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_mesh import read_static,build_static
from ue5_blueprint import read_tables
from project_preflight import preflight
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']); output=Path(os.environ['UE56_EDITOR_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True); browser.register()
root=project.parent/'Content'; plan=preflight(str(project),'GEOMETRY'); paths=[]
for p in root.rglob('*.uasset'):
    if any(k in ('__ExternalActors__','__ExternalObjects__') for k in p.parts):continue
    try: _,_,_,ex,*_=read_tables(p)
    except ValueError:continue
    if any(e['kind']=='StaticMesh' and not e['outer'] for e in ex):paths.append(p)
assert len(paths)==12
report={}; cursor=0
for p in sorted(paths):
    d=read_static(p);mesh=build_static(d);obj=bpy.data.objects.new(p.stem,mesh);bpy.context.scene.collection.objects.link(obj)
    assert len(mesh.vertices)==len(d['vertices']) and len(mesh.polygons)==len(d['triangles']) and len(mesh.uv_layers)==len(d['uvs'])
    err=max(abs(a-b) for v,xyz in zip(mesh.vertices,(d['vertices'][i] for i in sorted(d['vertices']))) for a,b in zip(v.co,(xyz[1]*.01,xyz[0]*.01,xyz[2]*.01)))
    assert err<1e-5
    indices={v:i for i,v in enumerate(sorted(d['vertices']))}
    for poly,(g,cs) in zip(mesh.polygons,d['triangles']):
        assert tuple(poly.vertices)==tuple(indices[d['instances'][c]] for c in cs) and poly.material_index==d['group_to_slot'][g]
    lo=min(v.co.x for v in mesh.vertices); hi=max(v.co.x for v in mesh.vertices); obj.location.x=cursor-lo;cursor+=hi-lo+.4
    report[p.stem]=dict(vertices=len(mesh.vertices),triangles=len(mesh.polygons),uv_sets=len(mesh.uv_layers),position_error_m=err,materials=d['materials'],payload_hash=d['source_hash'])
# Independently exercise the tracked batch path.
s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.batch_scope='GEOMETRY';s.cooked_profile='5.6';s.job_filter='SM_Door.uasset'
# Use exact package name filter without extension (matching behavior depends on UI).
s.job_filter='SM_Door';assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};print('CATALOG',[(i.name,i.package) for i in s.job_items])
assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
r=json.loads(bpy.data.texts[s.batch_report].as_string());print('BATCH',[(x['status'],x.get('detail')) for x in r['results']]); assert r['results'] and all(x['status']=='reconstructed' for x in r['results'])
n=len(bpy.data.objects);bpy.ops.wm.save_as_mainfile(filepath=str(output));bpy.ops.wm.open_mainfile(filepath=str(output))
s=bpy.context.scene.ueimport_project;assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};r=json.loads(bpy.data.texts[s.batch_report].as_string());assert all(x.get('reused') for x in r['results']) and len(bpy.data.objects)==n
output.with_suffix('.json').write_text(json.dumps({'assets':report,'batch_reuse':True,'preflight_counts':plan['dependency_counts']},indent=2));print('EDITOR_STATIC_PASS',len(report),sum(d['vertices'] for d in report.values()),sum(d['triangles'] for d in report.values()),flush=True)
