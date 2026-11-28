"""Actual editor texture load via legacy material bridge, without external process."""
import bpy,os,sys,tempfile,hashlib
from pathlib import Path
from types import SimpleNamespace as NS
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import umat
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
p=next(root.rglob('T_UE_Logo_M.uasset'));source_sha=hashlib.sha256(p.read_bytes()).hexdigest()
ref=NS(import_ref=NS(object_name='/Game/Test'),asset=NS(ToProjectPath=lambda _:str(p),uproject=os.environ['UE56_EDITOR_PROJECT']))
with tempfile.TemporaryDirectory() as d:
    im=umat.TryGetExtractedImport(ref,d);assert im and im.packed_file and im.get('UE_source_rgba_sha256');assert umat.TryGetExtractedImport(ref,d)==im
    bad=NS(import_ref=NS(object_name='/Game/Missing'),asset=NS(ToProjectPath=lambda _:str(Path(d)/'missing.uasset'),uproject=None));assert umat.TryGetExtractedImport(bad,d) is None
    assert not list(Path(d).iterdir());assert hashlib.sha256(p.read_bytes()).hexdigest()==source_sha
    im.use_fake_user=True;name=im.name;digest=hashlib.sha256(im.packed_file.data).hexdigest();out=str(Path(d)/'native.blend');bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out);assert hashlib.sha256(bpy.data.images[name].packed_file.data).hexdigest()==digest
print('NATIVE_TEXTURE_BOUNDARY_PASS',flush=True)
