"""Original classic/modern preview transaction and late-stage rollback."""
import importlib.abc,os,sys
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from project_session import new_ids
forbidden={'uasset','umap','umat','umesh'}; attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in forbidden:
            attempts.append(fullname);raise ImportError('Inherited module prohibited: '+fullname)
sys.meta_path.insert(0,Block())
import static_scene, component_scene, ue5_editor_scene
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;camera=bpy.data.objects.new('Existing Camera',bpy.data.cameras.new('Existing Camera'));scene.collection.objects.link(camera);scene.camera=camera
world=bpy.data.worlds.new('Existing World');scene.world=world
western=next(Path(os.environ['UE_WESTERN_PROJECT']).rglob('Overview.umap'))
modern=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/MyStuff/Maps/TestLevel.umap'
def fail(*args,**kwargs):
    assert set(new_ids())!=before,'Fault must occur after allocation'
    raise RuntimeError('controlled late fault')
def check_unchanged():
    assert set(new_ids())==before and scene.camera==camera and scene.world==world
before=set(new_ids())
with patch.object(component_scene,'extend_components',side_effect=fail):
    try:static_scene.reconstruct_static_map(str(western),components=True)
    except RuntimeError as exc:assert str(exc)=='controlled late fault'
    else:raise AssertionError('late classic fault accepted')
check_unchanged()
original=ue5_editor_scene.reconstruct
def modern_fault(*args,**kwargs):
    original(*args,**kwargs);return fail()
with patch.object(ue5_editor_scene,'reconstruct',side_effect=modern_fault):
    try:static_scene.reconstruct_static_map(str(modern))
    except RuntimeError as exc:assert str(exc)=='controlled late fault'
    else:raise AssertionError('late modern fault accepted')
check_unchanged()
with patch('package_inspector.inspect_package',return_value={'ue4':518,'ue5':None}):
    for f in (lambda:static_scene.reconstruct_static_map(str(western)),lambda:component_scene.extend_components(str(western),scene.collection,None)):
        try:f()
        except NotImplementedError:pass
        else:raise AssertionError('unsupported classic profile accepted')
        check_unchanged()
for path in (western,modern):
    c,r=static_scene.reconstruct_static_map(str(path),components=True)
    assert c.get('UE_report') and any(o.type=='MESH' for o in c.all_objects)
    print('NATIVE_PREVIEW_PASS',path.name,len(c.all_objects),r['actor_status'],flush=True)
assert not attempts and forbidden.isdisjoint(sys.modules)
print('NATIVE_PREVIEW_TRANSACTION_PASS',flush=True)
