"""Check recovered textures on genuine original assets, packing and cache isolation."""
import os, sys, json, hashlib
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from texture_blender import load_editor_texture
from ue5_editor_material import build_material
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);audit=json.loads(Path(os.environ['UE56_TEXTURE_REPORT']).read_text())
changed=('T_EnemySkull_Mask','T_EFX_Beam_Electricity_02','T_Lensflare_01','T_SquareMaskTightEdge','T_FX_CameraDistort','T_FX_ColorDistort','T_Caustics_2','T_muzzle_flashes','holo_layer_1_5','MagGun_Decals')
bpy.ops.wm.read_factory_settings(use_empty=True);records=[]
for stem in changed:
    p=next(root.rglob(stem+'.uasset'));expected=audit[str(p.relative_to(root))];assert expected['status']=='pass'
    # Pretend a packed old-profile image exists. It must not be reused.
    if stem=='MagGun_Decals':
        old=bpy.data.images.new('old delta profile',1,1);old.pack();old['UE_editor_texture_key']=f'{p.resolve()}|{p.stat().st_size}|{p.stat().st_mtime_ns}';old['UE_address_x']=old['UE_address_y']='TA_Wrap';old.use_fake_user=True
    im=load_editor_texture(p);im.use_fake_user=True
    assert tuple(im.size)==(expected['width'],expected['height']) and im.packed_file
    assert im['UE_source_rgba_sha256']==expected['rgba_sha256'] and json.loads(im['UE_delta_regions'])==expected['delta_regions']
    assert load_editor_texture(p)==im
    if stem=='MagGun_Decals':assert im!=old and old.size[0]==1
    records.append(dict(name=im.name,sha=im['UE_source_rgba_sha256'],packed_sha=hashlib.sha256(im.packed_file.data).hexdigest(),regions=expected['delta_regions'],size=list(im.size)))
for stem in ('MI_Quinn_01','MI_Manny_02_New'):
    p=next(root.rglob(stem+'.uasset'));pkg='/Game/'+p.relative_to(root).with_suffix('').as_posix();m=build_material(root,pkg,True);m.use_fake_user=True
    assert json.loads(m['UE_editor_preserved_outputs'])==['AmbientOcclusion']
    ao=next(n for n in m.node_tree.nodes if n.label.startswith('Unreal Ambient Occlusion'));assert ao.inputs[0].is_linked and not ao.outputs[0].is_linked
    assert all(n.extension=='REPEAT' for n in m.node_tree.nodes if n.type=='TEX_IMAGE')
    if stem=='MI_Manny_02_New':assert 'ScaleUVsByCenter' in m['UE_editor_graph']
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));
for r in records:
    im=bpy.data.images[r['name']];assert im.packed_file and hashlib.sha256(im.packed_file.data).hexdigest()==r['packed_sha'] and im['UE_source_rgba_sha256']==r['sha'];assert tuple(im.size)==tuple(r['size'])
out.with_suffix('.json').write_text(json.dumps(dict(recovered_images=records,legacy_cache_isolated=True,ao_preserved=True,reopen=True),indent=2));print('EDITOR_TEXTURE_REGION_PASS',len(records),flush=True)
