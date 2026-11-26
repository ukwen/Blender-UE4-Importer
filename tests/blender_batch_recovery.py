"""Inject failure after allocating objects and check only newly created IDs are removed."""
import bpy,sys,tempfile,pathlib,json,types
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
from project_batch import run_jobs
from project_preflight import preflight
from pathlib import Path
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh=bpy.data.meshes.new('Original'); obj=bpy.data.objects.new('Original',mesh); bpy.context.scene.collection.objects.link(obj)
with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp); content=root/'Content';content.mkdir();desc=root/'Test.uproject';desc.write_text('{}');a=content/'A.umap';b=content/'B.umap';a.touch();b.touch()
    plan=preflight(str(desc));assert plan['coverage_counts']=={'unknown':2}
    assert preflight(str(desc),'SELECTED_MAP',str(b))['jobs']==[str(b)]
    try:preflight(str(desc),'GEOMETRY',subfolder='../');raise AssertionError('escape accepted')
    except ValueError:pass
    def mock(path,**kw):
        coll=bpy.data.collections.new(Path(path).stem);bpy.context.scene.collection.children.link(coll)
        m=bpy.data.meshes.new('created');o=bpy.data.objects.new('created',m);coll.objects.link(o)
        if path==str(a):raise ValueError('injected failure')
        coll['UE_report']='report';return coll,{'actor_status':{'reconstructed':1}}
    sys.modules['static_scene']=types.SimpleNamespace(reconstruct_static_map=mock)
    rows=list(run_jobs(plan));assert [r['status'] for r in rows]==['failed','completed'];assert len(bpy.data.objects)==2 and len(bpy.data.meshes)==2;assert bpy.data.collections.get('A') is None and bpy.data.objects.get('Original')==obj
    print('FAILURE_ROLLBACK_AND_CONTINUE_PASS; SELECTED_SCOPE_PASS; UNKNOWN_COVERAGE_PASS; ESCAPE_REFUSAL_PASS')
