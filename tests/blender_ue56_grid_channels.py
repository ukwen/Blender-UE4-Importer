"""Independent planar grid mask acceptance; no claim of Unreal-rendered parity."""
import bpy, os, sys, json, hashlib
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material
from ue5_legacy_editor import read_texture
from texture_blender import load_editor_texture
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
path=next(root.rglob('T_GridChecker_A.uasset'));png,meta=read_texture(path);im=load_editor_texture(path);im.use_fake_user=True
assert bytes(im.packed_file.data)==png
raw=np.empty(512*512*4,dtype=np.float32);im.pixels.foreach_get(raw);raw=raw.reshape(512,512,4)
assert raw[:,:,0].max()==0 and raw[:,:,2].max()==1 and raw[:,:,3].min()==1
pkg='/Game/LevelPrototyping/Materials/MI_PrototypeGrid_Gray_02';mat=build_material(root,pkg,True);assert mat['UE_editor_material_status']=='partial';assert any(n.get('UE_legacy_png_channel_preview')=='BGR to RGB' for n in mat.node_tree.nodes)
# Evaluate the original material's connected base-color branch as unlit emission
# to isolate coordinates and mask values from light, BSDF, and exposure.
nt=mat.node_tree;bs=next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED');sink=next(n for n in nt.nodes if n.type=='OUTPUT_MATERIAL');src=bs.inputs['Base Color'].links[0].from_socket
emit=nt.nodes.new('ShaderNodeEmission');nt.links.new(src,emit.inputs['Color']);nt.links.new(emit.outputs[0],sink.inputs['Surface'])
bpy.ops.mesh.primitive_plane_add(size=2,location=(0,0,0));bpy.context.object.data.materials.append(mat)
bpy.ops.object.camera_add(location=(0,0,3));cam=bpy.context.object;cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=2.;scene=bpy.context.scene;scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=1;scene.cycles.use_denoising=False;scene.render.resolution_x=1024;scene.render.resolution_y=1024;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR';scene.render.image_settings.color_depth='32';scene.render.filepath=str(out.with_suffix('.exr'))
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));bpy.ops.render.render(write_still=True)
render=bpy.data.images.load(str(out.with_suffix('.exr')),check_existing=False);v=np.empty(1024*1024*4,dtype=np.float32);render.pixels.foreach_get(v);v=v.reshape(1024,1024,4)[:,:,0]
# Top view +Z: selected XY plane, world meters -> centimeters, Unreal XY
# permutation. The source wire and subwire repeat at 100cm and 20cm.
# Compare only flat interiors far from filtering boundaries. The raw PNG is
# loaded in Blender bottom-up, so the V reversal is explicit below.
a=(np.arange(1024)+.5)/512-1
x,y=np.meshgrid(a,a);u=y;vv=x
# Pixel-center bilinear reference, independent of the shader node graph.
def sample(u,v,channel):
    ix=(u%1)*512-.5;iy=((1-v)%1)*512-.5;lo=np.floor(ix).astype(int);lj=np.floor(iy).astype(int);fx=ix-lo;fy=iy-lj
    return (1-fy)*((1-fx)*raw[lj%512,lo%512,channel]+fx*raw[lj%512,(lo+1)%512,channel])+fy*((1-fx)*raw[(lj+1)%512,lo%512,channel]+fx*raw[(lj+1)%512,(lo+1)%512,channel])
main=sample(u,vv,2);sub=sample(u*5,vv*5,2)
# Select deep wire and surface pixels; sampling jitter affects edges and fine
# subgrid boundaries, so do not assert exact per-pixel equality there.
main_pixels=main>.99
interior=(main<.001)&(sub<.001)
# Exclude areas within a pixel of a subgrid boundary.
for a0 in (u*5,vv*5):interior &= np.minimum(a0%1,1-a0%1)>.035
major_mean=float(np.median(v[main_pixels]));interior_mean=float(np.median(v[interior]));assert abs(major_mean-.026241)<.012,(major_mean,interior_mean);assert abs(interior_mean-.18)<.002,(major_mean,interior_mean)
assert interior_mean-major_mean>.12
assert hashlib.sha256(bpy.data.images['T_GridChecker_A'].packed_file.data).hexdigest()==meta['png_sha256']
report=dict(major_grid_m=1.,subgrid_m=.2,major_wire_pixels=int(main_pixels.sum()),interior_pixels=int(interior.sum()),wire_median=major_mean,interior_median=interior_mean,expected_wire=.026241,expected_interior=.18,source_png_sha256=meta['png_sha256'],reopen=True,unreal_pixel_parity=False)
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('GRID_CHANNELS_PASS',report,flush=True)
