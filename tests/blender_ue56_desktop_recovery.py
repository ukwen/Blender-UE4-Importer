"""Real desktop confirmation for original-package recovery in a disposable copy.
Use desktop_recovery_x11_driver.py on a dedicated Xvfb display.
"""
import os,sys,json,time,traceback,shutil,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import __init__ as addon
from project_session import hash_file
out=Path(os.environ['UE_DESKTOP_DIR']);out.mkdir(parents=True,exist_ok=True)
source=Path(os.environ['UE56_EDITOR_PROJECT']);temp=tempfile.TemporaryDirectory(prefix='ue-desktop-recovery-')
work=Path(temp.name);root=work/'ShooterSam';recovery=work/'Recovery';recovery.mkdir();shutil.copytree(source.parent,root)
relative=Path('Content/LevelPrototyping/Meshes/SM_Cube.uasset');target=root/relative;candidate=recovery/'renamed_original.uasset';shutil.move(target,candidate)
expected=hash_file(source.parent/relative);assert hash_file(candidate)==expected
phase='setup';deadline=time.monotonic()+100;result={}
def mark(name,value=''):(out/name).write_text(value)
def invoke():
    with bpy.context.temp_override(window=win,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
        response=bpy.ops.ueimport.restore_sources('INVOKE_DEFAULT');assert 'RUNNING_MODAL' in response or 'INTERFACE' in response,response
    assert not target.exists()
def tick():
    global phase,win,area,s,at
    try:
        if time.monotonic()>deadline:raise RuntimeError('Recovery desktop timeout '+phase)
        if phase=='setup':
            addon.register();win=bpy.context.window;area=next(a for a in win.screen.areas if a.type=='VIEW_3D');s=win.scene.ueimport_project
            s.project_path=str(root/source.name);s.recovery_folder=str(recovery);assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
            s.active=next(i for i,m in enumerate(s.maps) if m.name.endswith('Lvl_Combat.umap'))
            assert bpy.ops.ueimport.locate_sources()=={'FINISHED'};plan=json.loads(bpy.data.texts[s.source_recovery_plan].as_string());assert plan['counts']['ready']==1,plan['counts']
            invoke();mark('first_prompt');phase='cancel';return .1
        if phase=='cancel' and (out/'cancel_sent').exists():
            if time.time()-(out/'cancel_sent').stat().st_mtime<.6:return .1
            assert not target.exists() and s.source_recovery_plan,'Cancelled dialog changed filesystem or plan'
            result['cancelled_without_writes']=True;invoke();mark('second_prompt');phase='confirm';return .1
        if phase=='confirm' and (out/'confirm_sent').exists() and target.exists():
            assert hash_file(target)==expected and hash_file(candidate)==expected and hash_file(source.parent/relative)==expected
            assert not s.source_recovery_plan and 'Restored 1' in s.source_recovery_status,s.source_recovery_status
            result.update(original_package_restored=True,source_unchanged=True,sha256=expected,actual_x11_confirmation=True)
            mark('result.json',json.dumps(result,indent=2));mark('done');phase='done';return .1
        if phase=='done' and (out/'quit').exists():temp.cleanup();bpy.ops.wm.quit_blender();return None
        return .1
    except Exception:
        mark('error',traceback.format_exc());print(traceback.format_exc(),flush=True);return None
bpy.app.timers.register(tick,first_interval=2.)
