"""Real large-map cooperative rollback, then exact synchronous/staged small-map parity."""
import bpy,os,sys,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_full_scene import iter_reconstruct,reconstruct
from saved_project_levels import iter_reconstruct as set_steps
from project_session import new_ids,rollback_new
from import_workflow import _ACTIVE
project=Path(os.environ['UE56_EDITOR_PROJECT']);content=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
main=content/'MyStuff/Maps/MainLevel.umap';small=content/'ThirdPerson/Lvl_ThirdPerson.umap'
assert main.is_file() and small.is_file()
scene=bpy.context.scene;camera=scene.camera;world=scene.world;baseline=set(new_ids());original={o.name:tuple(tuple(r) for r in o.matrix_world) for o in scene.objects}
for mode in ('single','set'):
    it=iter_reconstruct(str(main),True) if mode=='single' else set_steps(project,[main,small],True,stage_steps=True)
    try:
        for row in it:
            stage=row if isinstance(row,str) else row.get('stage','')
            assert _ACTIVE.get() is None
            if stage.startswith('Static actors 32/'):
                assert len(bpy.data.objects)>=len(original)+32 and set(new_ids())>baseline
                print('PARTIAL_STAGE',mode,stage,len(bpy.data.objects),flush=True);break
        else:raise AssertionError('No actual in-map checkpoint')
    finally:it.close()
    assert set(new_ids())==baseline and scene.camera==camera and scene.world==world
    assert {o.name:tuple(tuple(r) for r in o.matrix_world) for o in scene.objects}==original
root,r=reconstruct(str(small),True);expected=r['counts'];expected_diag=r['material_diagnostics'];rollback_new(baseline)
assert set(new_ids())==baseline
it=iter_reconstruct(str(small),True);stages=[]
try:
    while True:stages.append(next(it));assert _ACTIVE.get() is None
except StopIteration as done:root,r=done.value
finally:it.close()
assert r['counts']==expected and r['material_diagnostics']==expected_diag
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));root=next(c for c in bpy.context.scene.collection.children if c.get('UE_full_scene_source')==str(small));assert len(root.all_objects)==expected['objects']
result=dict(single_midmap_rollback=True,set_midmap_rollback=True,existing_ids_preserved=True,cache_context_isolated=True,stages=len(stages),counts=expected,material_diagnostics=expected_diag,reopen=True)
out.with_suffix('.json').write_text(json.dumps(result,indent=2));print('MIDMAP_PASS',len(stages),expected,flush=True)
