"""Former map operator and project-browser paths use native reconstruction.
Original UE4/UE5 source maps, legacy-filter refusal, rollback and reopen.
"""
import importlib.abc, json, os, sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError('Inherited importer prohibited: '+fullname)
sys.meta_path.insert(0,Block());assert CORE.isdisjoint(sys.modules)
from project_session import new_ids
import asset_entrypoints as entry, uproject_browser as browser
from project_paths import ProjectPaths
western=next(Path(os.environ['UE_WESTERN_PROJECT']).rglob('Overview.umap')).resolve()
modern=(Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/MyStuff/Maps/TestLevel.umap').resolve()
bpy.ops.wm.read_factory_settings(use_empty=True);entry.register();browser.register()
scene=bpy.context.scene
camera=bpy.data.objects.new('Existing camera',bpy.data.cameras.new('Existing camera'));scene.collection.objects.link(camera);scene.camera=camera
world=bpy.data.worlds.new('Existing world');scene.world=world

def refuse(action,reason):
    before=set(new_ids())
    try:action()
    except RuntimeError as exc:assert reason in str(exc),(reason,str(exc))
    else:raise AssertionError('Expected refusal: '+reason)
    assert set(new_ids())==before and scene.camera==camera and scene.world==world

try:
    ops=getattr(bpy.ops,'import')
    refuse(lambda:ops.umap(filepath=str(western),meshes=False),'Historical map filters')
    refuse(lambda:ops.umap(filepath=str(western),materials=False),'Historical map filters')
    refuse(lambda:ops.umap(filepath=str(western),lights_point=True),'Historical map filters')
    refuse(lambda:ops.umap(filepath=str(western),light_intensity=2.),'Historical map filters')
    assert ops.umap(filepath=str(western),allow_partial=True)=={'FINISHED'}
    refuse(lambda:ops.umap(filepath=str(western)),'already imported')
    state=scene.ueimport_project;state.project_path=str(ProjectPaths(modern).descriptor)
    assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
    state.active=next(i for i,m in enumerate(state.maps) if Path(m.filepath)==modern)
    state.materials=False
    refuse(lambda:bpy.ops.ueimport.import_selected_map(),'Historical materials-off')
    state.materials=True;state.partial_materials=True
    assert bpy.ops.ueimport.import_selected_map()=={'FINISHED'}
    refuse(lambda:bpy.ops.ueimport.import_selected_map(),'already imported')
    assert scene.camera==camera and scene.world==world and not attempts
    rows={}
    for path,expected in ((western,(417,352,30)),(modern,(32,10,1))):
        root=next(c for c in scene.collection.children_recursive if c.get('UE_full_scene_source')==str(path))
        report=json.loads(bpy.data.texts[root['UE_report']].as_string());counts=report['counts']
        assert (counts['objects'],counts['meshes'],counts['armatures'])==expected,(path,counts)
        rows[str(path)]=counts
    out=Path(os.environ['UE_MAP_ALIAS_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
    for path,counts in rows.items():
        root=next(c for c in bpy.context.scene.collection.children_recursive if c.get('UE_full_scene_source')==path)
        assert len(root.all_objects)==counts['objects']
    assert bpy.context.scene.camera.name=='Existing camera' and bpy.context.scene.world.name=='Existing world'
    assert not attempts and CORE.isdisjoint(sys.modules)
    out.with_suffix('.json').write_text(json.dumps(dict(levels=rows,filter_refusals=5,duplicate_refusals=2,reopen=True,world_camera_preserved=True,inherited_import_attempts=attempts),indent=2))
    print('NATIVE_MAP_ALIAS_PASS',sum(c['objects'] for c in rows.values()),flush=True)
finally:
    browser.unregister();entry.unregister()
