"""Actual mixed-format assets; mutation tests use disposable copies only."""
import sys, pathlib, json, os, tempfile, struct, collections
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import bpy,uasset,uproject_browser as browser
from package_inspector import inspect_package
from ue5_dependencies import read_dependencies
from blueprint_defaults import BlueprintResolver
from blueprint_lineage import resolve_lineage
from project_preflight import preflight
from project_session import run_session
root=pathlib.Path(os.environ['UE_GOBLIN_PROJECT']); desc=next(root.glob('*.uproject'));content=root/'Content';project=uasset.UProject(str(desc)); resolver=BlueprintResolver(project)
files=sorted(content.rglob('BP_Chr*.uasset')); assert len(files)==15
metrics=[]; mutate=None
for path in files:
    package='/Game/'+path.relative_to(content).with_suffix('').as_posix();key=(package,path.stem+'_C')
    r=resolve_lineage(key,resolver.load_local)
    assert r['lineage_status']=='native_parent' and len(r['lineage'])==2 and r['lineage'][1]['class']=='ThirdPersonCharacter_C'
    assert r['bindings']['Mesh']['package'].endswith('/SK_Chr_'+path.stem[7:]);assert r['bindings']['Mesh']['mesh_declared_in']==package
    m=inspect_package(path);record=dict(package=package,ue5=m['ue5'],lineage=r['lineage'],components=len(r['bindings']))
    if m['ue5']==1012:
        d=read_dependencies(path); assert d['soft_package_references']==[package] and len(d['soft_object_paths'])==2
        assert {o['subpath'] for o in d['soft_object_paths']}=={'UserConstructionScript','EventGraph'}
        assert all(o['package']==package for o in d['soft_object_paths']); assert len(d['export_dependency_rows'])==m['export_count']
        record.update(soft_objects=len(d['soft_object_paths']),dependency_rows=len(d['export_dependency_rows']),dependency_indices=sum(map(len,d['export_dependency_rows'])))
        mutate=(path,m,d)
    metrics.append(record)
assert sum(x['ue5']==1012 for x in metrics)==11
# Controlled corruption and external package reference test; not a claimed genuine external soft reference.
path,m,d=mutate; raw=path.read_bytes();target=next(x for x in d['hard_references'] if x in m['names']);bad=0
with tempfile.TemporaryDirectory() as td:
    f=pathlib.Path(td)/path.name
    for off,value in [(m['soft_package_offset'],-1),(m['soft_object_offset'],-1),(m['depends_offset'],100001),(m['soft_object_offset']+16,999999)]:
        b=bytearray(raw);struct.pack_into('<i',b,off,value);f.write_bytes(b)
        try:read_dependencies(f)
        except (ValueError,UnicodeError,struct.error):bad+=1
        else:raise AssertionError('Corrupt dependency accepted')
    b=bytearray(raw);struct.pack_into('<ii',b,m['soft_package_offset'],m['names'].index(target),0);f.write_bytes(b)
    assert target in read_dependencies(f)['soft_references']
assert bad==4
plan=preflight(str(desc));assert plan['soft_coverage_counts']['ue5_1012_summary_tables']==11
assert all(plan['records'][x['package']]['soft_references']==[x['package']] for x in metrics if x['ue5']==1012)
assert not any(k in plan['dependencies'] and k in plan['dependencies'][k]['soft_referenced_by'] for k in plan['records'])
# Selectively import two actual geometry dependencies, then rerun via the other scope.
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();state=bpy.context.scene.ueimport_project
state.project_path=str(desc);assert bpy.ops.ueimport.scan_project()=={'FINISHED'};state.batch_scope='MAP_GEOMETRY';state.job_filter='SK_Chr_';assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'}
all_jobs=len(state.job_items);assert all_jobs>=15
selected={item.package for item in state.job_items if item.package.endswith(('/SK_Chr_Wizard_01','/SK_Chr_Archer_Female_01'))};assert len(selected)==2
for item in state.job_items:item.enabled=item.package in selected
state.use_job_selection=True;assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
report=json.loads(bpy.data.texts[state.batch_report].as_string());assert len(report['results'])==2 and all(r['status']=='reconstructed' for r in report['results'])
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==2
out=os.environ['UE_DEP_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
folder_plan=preflight(str(desc),'GEOMETRY',job_filter='SK_Chr_',selected_packages=selected);repeat=list(run_session(folder_plan));assert len(repeat)==2 and all(r.get('reused') for r in repeat)
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==2
pathlib.Path(os.environ['UE_DEP_REPORT']).write_text(json.dumps(dict(blueprints=metrics,corruption_rejected=bad,controlled_external_soft_reference='passed',dependency_counts=plan['dependency_counts'],soft_coverage=plan['soft_coverage_counts'],map_geometry_jobs=all_jobs,selected_jobs=len(selected),reused=len(repeat)),indent=2))
print('UE5_DEPENDENCY_AND_LINEAGE_PASS',all_jobs,len(selected),len(repeat),flush=True)
