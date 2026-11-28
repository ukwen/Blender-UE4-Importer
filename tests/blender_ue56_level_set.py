"""Original map set through registered UI, ownership, independent visibility and rollback."""
import os,sys,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from project_session import new_ids
from saved_project_levels import reconstruct
from ue5_level_layout import inventory
project=Path(os.environ['UE56_EDITOR_PROJECT']);content=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
p=content/'ThirdPerson/Lvl_ThirdPerson.umap';q=content/'MyStuff/Maps/TestLevel.umap'
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();scene=bpy.context.scene
camera=bpy.data.objects.new('User Camera',bpy.data.cameras.new('User Camera'));scene.collection.objects.link(camera);scene.camera=camera
world=bpy.data.worlds.new('User World');scene.world=world
s=scene.ueimport_project;s.project_path=str(project);s.partial_materials=True;assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
for m in s.maps:m.enabled=Path(m.filepath) in (p,q)
assert bpy.ops.ueimport.level_set()=={'FINISHED'}
group=next(c for c in scene.collection.children if c.get('UE_project_level_set'));report=json.loads(bpy.data.texts[group['UE_report']].as_string());assert len(report['levels'])==2
assert scene.world==world and scene.camera==camera
roots={c['UE_full_scene_source']:c for c in group.children};assert set(roots)=={str(p),str(q)}
for c in roots.values():
    r=json.loads(bpy.data.texts[c['UE_report']].as_string());assert len(c.all_objects)==r['counts']['objects'];assert 'level_layout' in r
assert json.loads(bpy.data.texts[roots[str(p)]['UE_report']].as_string())['level_layout']['owned_external_packages']==65
matrices={}
for target in (p,q):
    s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==target);assert bpy.ops.ueimport.activate_level()=={'FINISHED'};bpy.context.view_layer.update()
    assert all(c.hide_render==c.hide_viewport==(k!=str(target)) for k,c in roots.items());matrices[str(target)]={o.name:[list(v) for v in o.matrix_world] for o in roots[str(target)].all_objects}
ids=set(new_ids())
try:reconstruct(project,[p,q]);raise AssertionError('duplicate accepted')
except ValueError as exc:assert 'already imported' in str(exc)
assert set(new_ids())==ids
# Original maps with injected second-stage failure: whole set must roll back.
import ue5_full_scene
original=ue5_full_scene.reconstruct;calls=[]
def fail(*a,**k):
    calls.append(a[0])
    if len(calls)==2:raise RuntimeError('injected second level failure')
    return original(*a,**k)
ue5_full_scene.reconstruct=fail
try:
    try:reconstruct(project,[content/'Variant_Combat/Lvl_Combat.umap',content/'Variant_Platforming/Lvl_Platforming.umap'],True);raise AssertionError('failure not propagated')
    except RuntimeError as exc:assert 'injected second level' in str(exc)
    assert len(calls)==2 and set(new_ids())==ids and scene.camera==camera and scene.world==world
finally:ue5_full_scene.reconstruct=original
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));scene=bpy.context.scene;s=scene.ueimport_project;group=next(c for c in scene.collection.children if c.get('UE_project_level_set'))
assert group['UE_active_level']==str(q);assert json.loads(bpy.data.texts[group['UE_report']].as_string())['active_source']==str(q);assert scene.camera.name=='User Camera' and scene.world.name=='User World'
max_error=0
for target in (p,q):
    s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==target);assert bpy.ops.ueimport.activate_level()=={'FINISHED'};bpy.context.view_layer.update();c=next(c for c in group.children if c.get('UE_full_scene_source')==str(target));assert len(c.all_objects)==len(matrices[str(target)])
    for o in c.all_objects:max_error=max(max_error,max(abs(o.matrix_world[i][j]-matrices[str(target)][o.name][i][j]) for i in range(4) for j in range(4)))
assert max_error<1e-6,max_error
layouts={}
for p in content.rglob('Lvl_*.umap'):
    r=inventory(content,p);layouts[p.stem]=dict(owned=r['owned_external_packages'],external_errors=len(r['external_errors']),partition=r['partition'],composition_candidates=len(r['composition_candidates']))
result=dict(levels=report['levels'],layouts=layouts,max_reopen_matrix_error=max_error,reopen=True,duplicate_refusal=True,late_rollback=True,world_camera_preserved=True,scope='Independent levels, not streaming assembly')
out.with_suffix('.json').write_text(json.dumps(result,indent=2));print('LEVEL_SET_PASS',result,flush=True)
