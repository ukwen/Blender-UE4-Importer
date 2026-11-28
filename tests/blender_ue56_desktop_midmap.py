"""Original MainLevel actual desktop cancellation, then smaller original retry."""
import bpy,os,sys,time,json,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from project_session import new_ids
out=Path(os.environ['UE_DESKTOP_DIR']);out.mkdir(parents=True,exist_ok=True)
project=Path(os.environ['UE56_EDITOR_PROJECT']);phase='setup';deadline=time.monotonic()+180

def mark(name,value=''): (out/name).write_text(value)

def invoke():
    with bpy.context.temp_override(window=win,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
        assert bpy.ops.ueimport.full_scene('INVOKE_DEFAULT')=={'RUNNING_MODAL'}

def tick():
    global phase,win,area,scene,s,baseline,camera,world
    try:
        assert time.monotonic()<deadline,phase
        if phase=='setup':
            import __init__ as addon
            addon.register();win=bpy.context.window;area=next(a for a in win.screen.areas if a.type=='VIEW_3D');area.spaces.active.show_region_ui=True
            scene=win.scene;s=scene.ueimport_project;camera=scene.camera;world=scene.world;s.project_path=str(project);s.partial_materials=True
            assert bpy.ops.ueimport.scan_project()=={'FINISHED'};baseline=set(new_ids())
            s.active=next(i for i,m in enumerate(s.maps) if m.name.endswith('/MainLevel.umap'))
            invoke();phase='partial';return .02
        if phase=='partial' and s.batch_status.startswith('Static actors '):
            assert set(new_ids())>baseline;assert not any(c.get('UE_full_scene_source') for c in scene.collection.children_recursive)
            mark('partial',json.dumps({'stage':s.batch_status,'objects':len(scene.objects)}));phase='cancel'
        if phase=='cancel' and not browser.UEIMPORT_OT_level_set._active:
            assert (out/'escape_sent').exists() and 'cancelled' in s.batch_status,s.batch_status
            assert set(new_ids())==baseline and scene.camera==camera and scene.world==world
            s.active=next(i for i,m in enumerate(s.maps) if m.name.endswith('Lvl_ThirdPerson.umap'));invoke();phase='retry'
        if phase=='retry' and not browser.UEIMPORT_OT_level_set._active:
            assert s.batch_status=='Selected level imported',s.batch_status
            root=next(c for c in scene.collection.children if c.get('UE_full_scene_source'));assert len(root.all_objects)==62
            result=dict(actual_escape_midmap=True,partial=json.loads((out/'partial').read_text()),exact_id_rollback=True,camera_world_preserved=True,standalone_modal_retry=True,objects=62)
            mark('result.json',json.dumps(result,indent=2));mark('done');phase='done'
        if phase=='done' and (out/'quit').exists():bpy.ops.wm.quit_blender();return None
        return .02
    except Exception:
        mark('error',traceback.format_exc());print(traceback.format_exc(),flush=True);return None
bpy.app.timers.register(tick,first_interval=2.)
