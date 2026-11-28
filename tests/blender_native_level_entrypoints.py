"""Actual native saved-level file menu, no inherited modules, real UE4 and UE5."""
import os, sys, json, importlib.abc
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
forbidden={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname in forbidden:
            attempts.append(fullname);raise ImportError('Inherited module prohibited: '+fullname)
sys.meta_path.insert(0,Block())
from project_session import new_ids
import asset_entrypoints as entry
bpy.ops.wm.read_factory_settings(use_empty=True);entry.register()
scene=bpy.context.scene
camera=bpy.data.objects.new('User Camera',bpy.data.cameras.new('User Camera'));scene.collection.objects.link(camera);scene.camera=camera
world=bpy.data.worlds.new('User World');scene.world=world
western=next(Path(os.environ['UE_WESTERN_PROJECT']).rglob('Overview.umap'))
modern=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/MyStuff/Maps/TestLevel.umap'
reports={}
for path in (modern,western):
    assert getattr(bpy.ops,'import').ue_saved_level(filepath=str(path),allow_partial=True)=={'FINISHED'}
    group=next(c for c in scene.collection.children if c.get('UE_project_level_set') and any(x.get('UE_full_scene_source')==str(path) for x in c.children))
    report=json.loads(bpy.data.texts[group['UE_report']].as_string());root=next(iter(group.children));assert report['levels'][0]['source']==str(path)
    counts=report['levels'][0]['counts'];assert counts['meshes']>0 and counts['objects']==len(root.all_objects)
    reports[str(path)]=counts
    before=set(new_ids())
    try:entry.import_saved_levels([path]);raise AssertionError('Duplicate accepted')
    except ValueError as exc:assert 'already imported' in str(exc)
    assert set(new_ids())==before and scene.world==world and scene.camera==camera
    print('NATIVE_LEVEL_MENU_PASS',path.name,counts,flush=True)
before=set(new_ids())
try:entry.import_saved_levels([modern,western]);raise AssertionError('Mixed project accepted')
except ValueError as exc:assert 'one original Unreal project' in str(exc)
assert set(new_ids())==before and not attempts,attempts
out=Path(os.environ['UE_NATIVE_LEVEL_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
assert bpy.context.scene.camera.name=='User Camera' and bpy.context.scene.world.name=='User World'
for path,counts in reports.items():
    root=next(c for c in bpy.context.scene.collection.children_recursive if c.get('UE_full_scene_source')==path)
    assert len(root.all_objects)==counts['objects']
assert forbidden.isdisjoint(sys.modules) and not attempts,attempts
out.with_suffix('.json').write_text(json.dumps(dict(levels=reports,reopen=True,duplicate_refusal=True,mixed_project_refusal=True,inherited_import_attempts=attempts,world_camera_preserved=True),indent=2))
entry.unregister();print('NATIVE_LEVEL_ENTRYPOINTS_PASS',flush=True)
