"""Opt-in source-driven UE4.18 surface preview on original M_Worm."""
import hashlib, importlib.abc, json, os, shutil, sys, tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
core={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in core: attempts.append(fullname);raise ImportError(fullname)
sys.meta_path.insert(0,Block())
from asset_entrypoints import import_material, register
from project_session import new_ids
from native_texture import read_texture,decode_rgba,png_bytes
from cooked_material_preview import texture_srgb
bpy.ops.wm.read_factory_settings(use_empty=True);register()
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp);(root/'Worm.uproject').write_text('{}');content=root/'Content';shutil.copytree(Path(os.environ['MATYA_ASSETS'])/'4.18',content)
    p=content/'M_Worm.uasset'
    raw=import_material(p,profile='4.18');raw_images={n.image.name:bytes(n.image.packed_file.data) for n in raw.node_tree.nodes if n.type=='TEX_IMAGE'}
    before=set(bpy.data.materials)
    assert getattr(bpy.ops,'import').umat(filepath=str(p),profile='4.18',allow_partial=True)=={'FINISHED'}
    m,=set(bpy.data.materials)-before
    def check(m):
        assert m['UE_material_status']=='partial_surface_preview' and m['UE_unresolved_material']
        nodes=m.node_tree.nodes;links=m.node_tree.links
        assert len(links)==14, len(links)
        bsdf=next(n for n in nodes if n.type=='BSDF_PRINCIPLED');out=next(n for n in nodes if n.type=='OUTPUT_MATERIAL')
        samples={n['UE_preview_input']:n for n in nodes if n.get('UE_preview_input')}
        assert set(samples)=={'BaseColor','Opacity','Normal'}
        assert samples['BaseColor'].image.colorspace_settings.name=='sRGB'
        assert samples['Normal'].image.colorspace_settings.name=='Non-Color' and samples['Normal'].image['UE_normal_z_reconstructed']
        assert samples['Opacity'].image.colorspace_settings.name=='Non-Color'
        assert bsdf.inputs['Base Color'].links[0].from_node==samples['BaseColor']
        assert bsdf.inputs['Alpha'].links[0].from_socket.name=='Red'
        assert bsdf.inputs['Normal'].links[0].from_node.type=='NORMAL_MAP'
        assert out.inputs['Surface'].links[0].from_node==bsdf
        assert all(n.inputs['Vector'].links[0].from_node.uv_map=='UV0' for n in samples.values())
        assert all(i.packed_file and bytes(i.packed_file.data)==data for name,data in raw_images.items() for i in [bpy.data.images[name]])
        return samples
    samples=check(m);name=m.name
    w,h,fmt,raw_bytes,count=read_texture(content/'T_Worm_N.uasset','4.18');rgba=bytearray(decode_rgba(w,h,fmt,raw_bytes))
    for i in range(0,len(rgba),4):
        x,y=rgba[i]/127.5-1,rgba[i+1]/127.5-1;rgba[i+2]=round((max(0,1-x*x-y*y)**.5+1)*127.5)
    assert bytes(samples['Normal'].image.packed_file.data)==png_bytes(w,h,rgba)
    assert texture_srgb(content/'T_Worm_D.uasset','/Game/T_Worm_D') and not texture_srgb(content/'T_Worm_A.uasset','/Game/T_Worm_A') and not texture_srgb(content/'T_Worm_N.uasset','/Game/T_Worm_N')
    image_count=len(bpy.data.images);reuse=import_material(p,True,'4.18');check(reuse);assert len(bpy.data.images)==image_count
    # Unknown source semantics do not silently connect approximate nodes.
    with patch('cooked_material_preview.texture_srgb',return_value=False):
        blocked=import_material(p,True,'4.18');assert blocked['UE_material_status']=='shader_unresolved' and 'UE_cooked_preview_issue' in blocked
        assert not any(n.type=='BSDF_PRINCIPLED' for n in blocked.node_tree.nodes)
    before=set(new_ids())
    with patch('cooked_material_preview.build_preview',side_effect=RuntimeError('injected late failure')):
        try:import_material(p,True,'4.18')
        except RuntimeError:pass
        else:raise AssertionError('expected rollback')
    assert set(new_ids())==before
    (content/'T_Worm_N.uasset').unlink();missing=import_material(p,True,'4.18')
    assert missing['UE_material_status']=='shader_unresolved' and not any(n.type=='BSDF_PRINCIPLED' for n in missing.node_tree.nodes)
    out=Path(os.environ['UE_COOKED_SURFACE_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));samples=check(bpy.data.materials[name])
    evidence=dict(profile='4.18',source='M_Worm',preview_links=len(bpy.data.materials[name].node_tree.links),raw_images_unchanged=len(raw_images),packed_normal_sha256=hashlib.sha256(samples['Normal'].image.packed_file.data).hexdigest(),reopen=True,reuse=True,missing_refusal=True,colorspace_refusal=True,rollback=True,inherited_import_attempts=attempts,render_equivalence=False)
    assert not attempts
    out.with_suffix('.json').write_text(json.dumps(evidence,indent=2));print('COOKED_SURFACE_PREVIEW_PASS',evidence,flush=True)
