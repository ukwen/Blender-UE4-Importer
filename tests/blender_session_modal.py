"""GUI acceptance harness: invoke real modal operator; external Escape key required."""
import bpy,sys,os,json,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as b
b.register();bpy.ops.wm.read_factory_settings(use_empty=True)
s=bpy.context.scene.ueimport_project;s.project_path=str(Path(os.environ['UE_VEHICLE_PROJECT'])/'Vehicles.uproject');s.batch_scope='GEOMETRY';s.geometry_physics=True
base=b.UEIMPORT_OT_batch.step
def observe(self):
    result=base(self)
    if len(self.results)==1:
        Path(os.environ['UE_MODAL_SIGNAL']).write_text('first native job complete'); time.sleep(1.5)
    return result
b.UEIMPORT_OT_batch.step=observe
start=time.monotonic()
def invoke():
    win=bpy.context.window_manager.windows[0]; area=next(a for a in win.screen.areas if a.type=='VIEW_3D')
    with bpy.context.temp_override(window=win,area=area,region=next(r for r in area.regions if r.type=='WINDOW')):
        assert bpy.ops.ueimport.batch_import('INVOKE_DEFAULT')=={'RUNNING_MODAL'}
    bpy.app.timers.register(check,first_interval=.2);return None
def check():
    if b.UEIMPORT_OT_batch._active:
        if time.monotonic()-start>90: raise RuntimeError('Modal cancellation timeout')
        return .2
    state=bpy.context.scene.ueimport_project;r=json.loads(bpy.data.texts[state.batch_report].as_string());n=sum(o.type=='ARMATURE' for o in bpy.data.objects)
    assert r['status']=='stopped' and 1<=n<13 and len(r['results'])==n,(r['status'],n)
    Path(os.environ['UE_MODAL_REPORT']).write_text(json.dumps(dict(status=r['status'],completed=n,remaining=r['unprocessed']),indent=2));print('GUI_ESC_PASS',n,flush=True);bpy.ops.wm.quit_blender();return None
bpy.app.timers.register(invoke,first_interval=1.)
