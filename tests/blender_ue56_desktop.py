"""Linux desktop smoke: run without -b on an isolated X11 display.
External driver checks clipboard, sends actual Escape, and captures the UI.
Uses original map assets, read only.
"""
import os,sys,json,time,traceback
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from project_session import new_ids
out=Path(os.environ['UE_DESKTOP_DIR']);out.mkdir(parents=True,exist_ok=True)
project=Path(os.environ['UE56_EDITOR_PROJECT']);result={};phase='setup';deadline=time.monotonic()+100
original_step=browser.UEIMPORT_OT_level_set.step

def mark(name,value=''):
    (out/name).write_text(value)

def step(self):
    r=original_step(self)
    if self.done==1 and not self.finished:mark('first_staged',str(len(bpy.data.objects)))
    return r

def setup():
    global phase,scene,s,area,win,baseline,camera,world
    import __init__ as addon
    addon.register()
    win=bpy.context.window;area=next(a for a in win.screen.areas if a.type=='VIEW_3D')
    area.spaces.active.show_region_ui=True
    region=next(r for r in area.regions if r.type=='UI')
    try:region.active_panel_category='Unreal'
    except AttributeError:pass
    scene=win.scene;s=scene.ueimport_project;camera=scene.camera;world=scene.world
    s.project_path=str(project);s.partial_materials=True
    assert bpy.ops.ueimport.scan_project()=={'FINISHED'} and len(s.maps)==6
    assert bpy.ops.ueimport.check_maps(enabled=True)=={'FINISHED'} and all(m.enabled for m in s.maps)
    assert bpy.ops.ueimport.check_maps(enabled=False)=={'FINISHED'} and not any(m.enabled for m in s.maps)
    s.active=next(i for i,m in enumerate(s.maps) if m.name.endswith('Lvl_ThirdPerson.umap'))
    original=s.project_path;s.project_path=str(project.parent/'absent.uproject');assert not bpy.ops.ueimport.full_scene.poll();s.project_path=original;assert bpy.ops.ueimport.full_scene.poll()
    assert bpy.ops.ueimport.scene_dependencies()=={'FINISHED'};assert bpy.ops.ueimport.copy_scene_actions()=={'FINISHED'}
    mark('clipboard_expected',bpy.data.texts[s.scene_action_report].as_string())
    result.update(scan=True,all_none=True,stale_project_guard=True,advanced_defaults=not any(getattr(s,k) for k in ('show_options','show_recovery','show_environment','show_batch','show_tools')))
    baseline=set(new_ids());browser.UEIMPORT_OT_level_set.step=step
    mark('ready');phase='clipboard';return .05

def tick():
    global phase,baseline
    try:
        if time.monotonic()>deadline:raise RuntimeError('Desktop test timeout: '+phase)
        if phase=='setup':return setup()
        if phase=='clipboard' and (out/'clipboard_checked').exists():
            assert (out/'clipboard_checked').read_text()=='exact';result['external_clipboard_exact']=True
            for m in s.maps:m.enabled=m.name.endswith(('Lvl_ThirdPerson.umap','TestLevel.umap'))
            with bpy.context.temp_override(window=win,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
                assert bpy.ops.ueimport.level_set('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
            phase='cancel';return .05
        if phase=='cancel' and not browser.UEIMPORT_OT_level_set._active:
            assert (out/'first_staged').exists() and (out/'escape_sent').exists()
            assert 'cancelled' in s.batch_status,s.batch_status
            assert set(new_ids())==baseline and scene.camera==camera and scene.world==world
            result.update(actual_escape=True,exact_id_rollback=True,camera_world_preserved=True)
            browser.UEIMPORT_OT_level_set.step=original_step
            # Retry the same operation through the desktop modal handler.
            with bpy.context.temp_override(window=win,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
                assert bpy.ops.ueimport.level_set('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
            phase='retry';return .05
        if phase=='retry' and not browser.UEIMPORT_OT_level_set._active:
            assert s.batch_status.startswith('Imported 2'),s.batch_status
            group=next(c for c in scene.collection.children if c.get('UE_project_level_set'))
            assert len(group.children)==2
            assert scene.camera==camera and scene.world==world
            result.update(modal_retry=True,levels=len(group.children),objects=sum(len(c.all_objects) for c in group.children))
            # Expand all folds for an actual draw pass; test screenshot is external.
            for k in ('show_options','show_recovery','show_environment','show_batch','show_tools'):setattr(s,k,True)
            area.tag_redraw();mark('expanded_ready');phase='expanded';return .1
        if phase=='expanded' and (out/'expanded_checked').exists():
            for k in ('show_options','show_recovery','show_environment','show_batch','show_tools'):setattr(s,k,False)
            area.tag_redraw();result['advanced_panel_capture']=True
            mark('result.json',json.dumps(result,indent=2));mark('done');phase='done';return .1
        if phase=='done' and (out/'quit').exists():bpy.ops.wm.quit_blender();return None
        return .05
    except Exception:
        mark('error',traceback.format_exc());print(traceback.format_exc(),flush=True);return None
bpy.app.timers.register(tick,first_interval=2.)
