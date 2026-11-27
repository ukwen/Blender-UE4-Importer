"""Genuine UE5 1004 PNG and instance acceptance, with saved packed bytes."""
import bpy, os, sys, json, hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from texture_blender import load_editor_texture
from ue5_editor_material import build_material
from ue5_legacy_editor import read_texture
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
p=next(root.rglob('T_GridChecker_A.uasset'));png,meta=read_texture(p);im=load_editor_texture(p);im.use_fake_user=True
assert im.packed_file and bytes(im.packed_file.data)==png and im.colorspace_settings.name=='Non-Color' and load_editor_texture(p)==im
records=[]
for stem,n in [('MI_PrototypeGrid_Gray_02',6),('MI_PrototypeGrid_TopDark',7)]:
    p=next(root.rglob(stem+'.uasset'));pkg='/Game/'+p.relative_to(root).with_suffix('').as_posix();m=build_material(root,pkg,True);m.use_fake_user=True
    graph=json.loads(m['UE_editor_graph']);issues=json.loads(m['UE_editor_material_issues']);assert len(graph['parameters'])==n and len(graph['chain'])==2;assert m['UE_editor_material_status']=='partial';records.append(dict(name=m.name,parameters=n,issues=issues))
name=im.name;bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));im=bpy.data.images[name];assert hashlib.sha256(im.packed_file.data).hexdigest()==meta['png_sha256'];assert all(len(json.loads(bpy.data.materials[r['name']]['UE_editor_graph'])['parameters'])==r['parameters'] for r in records)
out.with_suffix('.json').write_text(json.dumps(dict(texture=meta,materials=records,reopen=True),indent=2));print('LEGACY_EDITOR_PASS',flush=True)
