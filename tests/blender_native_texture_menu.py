"""Original editor and cooked texture batches, with inherited imports prohibited."""
import bpy, os, sys, importlib.abc, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
forbidden={'uasset','umesh','umat','umap'}; attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in forbidden:
            attempts.append(fullname); raise ImportError('Inherited module prohibited: '+fullname)
sys.meta_path.insert(0,Block())
import texture_blender as tex
import asset_entrypoints as entry
from project_session import new_ids
from package_records import read_package
bpy.ops.wm.read_factory_settings(use_empty=True);entry.register();tex.register()
west=Path(os.environ['UE_WESTERN_PROJECT']); modern=Path(os.environ['UE56_EDITOR_PROJECT']).parent
classic=next(p for p in sorted(west.rglob('*.uasset')) if 'Textures' in p.parts and any(e.kind=='Texture2D' for e in read_package(p)[2].exports))
ue5=next(modern.rglob('T_UE_Logo_M.uasset'))
existing=tex.load_editor_texture(classic); existing.use_fake_user=False
before=set(new_ids())
not_texture=next(p for p in sorted(west.rglob('SM_*.uasset')))
try:tex.import_texture_batch([classic,ue5,not_texture]);raise AssertionError('Mixed asset batch accepted')
except (ValueError,NotImplementedError):pass
assert set(new_ids())==before and not existing.use_fake_user
from unittest.mock import patch
with patch('package_inspector.inspect_package',return_value=dict(status='tables_inspected',ue4=518,ue5=None,sidecars=[])):
    try:tex.import_texture_batch([classic]);raise AssertionError('Unsupported native editor profile accepted')
    except NotImplementedError:pass
assert set(new_ids())==before and not existing.use_fake_user
images=tex.import_texture_batch([classic,ue5]); assert images[0]==existing and all(i.packed_file and i.use_fake_user for i in images)
assert bpy.ops.ueimport.native_texture(filepath=str(ue5),version='editor')=={'FINISHED'}
for profile in ('4.18','4.27','5.0'):
    root=Path(os.environ['MATYA_ASSETS'])/profile
    paths=sorted(root.glob('T_Worm_*.uasset'))
    assert len(paths)==3
    assert bpy.ops.ueimport.native_texture(directory=str(root), files=[{'name':p.name} for p in paths],version=profile)=={'FINISHED'}
    print('COOKED_TEXTURE_MENU_PASS',profile,len(paths),flush=True)
before=set(new_ids())
try:tex.import_texture_batch([classic,classic]);raise AssertionError('Duplicate accepted')
except ValueError:pass
assert set(new_ids())==before
from tempfile import TemporaryDirectory
with TemporaryDirectory() as d:
    bad=Path(d)/'broken.uasset';bad.write_bytes(paths[0].read_bytes())
    try:tex.import_texture_batch([paths[0],bad],'5.0');raise AssertionError('Missing sidecar accepted')
    except (ValueError,FileNotFoundError):pass
assert set(new_ids())==before
packed={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.get('UE_texture_format') and i.packed_file}
assert len(packed)==11 and not attempts and forbidden.isdisjoint(sys.modules)
out=os.environ['UE_TEXTURE_BATCH_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.get('UE_texture_format') and i.packed_file}
assert not attempts;tex.unregister();entry.unregister()
print('NATIVE_TEXTURE_BATCH_PASS',len(packed),'editor+3 cooked profiles, rollback and reopen',flush=True)
