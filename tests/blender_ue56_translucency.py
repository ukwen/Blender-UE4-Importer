"""Original unlit radial surface preview: validate actual surface alpha and emission."""
import bpy, os, sys, json
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
def pkg(stem):return '/Game/'+next(root.rglob(stem+'.uasset')).relative_to(root).with_suffix('').as_posix()
def surface(m):return next(n for n in m.node_tree.nodes if n.type=='OUTPUT_MATERIAL').inputs['Surface'].links[0].from_node
results={}
for name in ('M_radial_ramp_soft','M_SimpleGlow','M_WP_Linkgun_Connection','M_Mannequin','M_LensFlare_02'):
    m=build_material(root,pkg(name),True);m.use_fake_user=True
    results[name]=dict(surface=surface(m).type,preview=m.get('UE_surface_preview','none'),issues=json.loads(m['UE_editor_material_issues']))
    if name in ('M_radial_ramp_soft','M_SimpleGlow'):assert surface(m).type=='MIX_SHADER' and m.get('UE_surface_preview')=='unlit_translucent',results[name]
    if name in ('M_Mannequin','M_LensFlare_02'):assert not m.get('UE_surface_preview')
    strict=build_material(root,pkg(name),False);assert strict['UE_editor_material_status']=='metadata_only' and not strict.get('UE_surface_preview') and surface(strict).type=='BSDF_PRINCIPLED';bpy.data.materials.remove(strict)
mat=bpy.data.materials['M_radial_ramp_soft'];bpy.ops.mesh.primitive_plane_add(size=2);plane=bpy.context.object;plane.data.uv_layers.active.name='UV0';plane.data.materials.append(mat)
bpy.ops.object.camera_add(location=(0,0,3));cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=2;sc=bpy.context.scene;sc.camera=cam
sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=128;sc.cycles.use_denoising=False;sc.cycles.use_adaptive_sampling=False;sc.render.film_transparent=True;sc.render.resolution_x=128;sc.render.resolution_y=128;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='OPEN_EXR';sc.render.image_settings.color_depth='32';sc.render.image_settings.color_mode='RGBA';sc.render.threads_mode='FIXED';sc.render.threads=4
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));sc=bpy.context.scene;mat=bpy.data.materials['M_radial_ramp_soft'];assert surface(mat).get('UE_unlit_translucent_preview');assert surface(mat).inputs[0].is_linked
rgb=next(n for n in mat.node_tree.nodes if n.type=='RGB' and 'preview RGB' in n.label);alpha=next(n for n in mat.node_tree.nodes if n.type=='VALUE' and 'preview alpha' in n.label);rgb.outputs[0].default_value=(.2,.4,.8,1.)
a=(np.arange(128)+.5)/128;x,y=np.meshgrid(a,a);radial=np.maximum(0,1-np.hypot(x-.5,y-.5)/.6000000238418579)**5
checks=[]
for value in (1.,.4):
    alpha.outputs[0].default_value=value;sc.render.filepath=str(out.with_name(f'translucent-{value}.exr'));bpy.ops.render.render(write_still=True);im=bpy.data.images.load(sc.render.filepath,check_existing=False);raw=np.empty(128*128*4,dtype=np.float32);im.pixels.foreach_get(raw);raw=raw.reshape(128,128,4);bpy.data.images.remove(im)
    expected=radial*value;err=np.abs(raw[:,:,3]-expected);rgb_err=np.abs(raw[:,:,:3]-raw[:,:,3,None]*np.array([.2,.4,.8]));check=dict(particle_alpha=value,pixels=err.size,mean_alpha_error=float(err.mean()),p99_alpha_error=float(np.quantile(err,.99)),mean_alpha_bias=float((raw[:,:,3]-expected).mean()),mean_premultiplied_rgb_error=float(rgb_err.mean()),max_premultiplied_rgb_error=float(rgb_err.max()));print('CHECK',check,flush=True);assert check['mean_alpha_error']<.025 and check['p99_alpha_error']<.12 and abs(check['mean_alpha_bias'])<.005 and check['mean_premultiplied_rgb_error']<.001,check;checks.append(check)
# Verify the original vector-parameter alpha branch and editable switch with
# a constant spatial result derived independently from the saved Lerp graph.
mat=bpy.data.materials['M_SimpleGlow'];next(o for o in sc.objects if o.type=='MESH').data.materials[0]=mat
nt=mat.node_tree
for label,value in [('Custom Prim Switch',.25),('Color (alpha parameter)',.6)]:next(n for n in nt.nodes if n.label==label).outputs[0].default_value=value
next(n for n in nt.nodes if n.label=='Color').outputs[0].default_value=(.8,.2,.4,1.)
next(n for n in nt.nodes if n.type=='RGB' and 'preview RGB' in n.label).outputs[0].default_value=(.2,.4,.8,1.)
next(n for n in nt.nodes if n.type=='VALUE' and 'preview alpha' in n.label).outputs[0].default_value=.4
sc.render.filepath=str(out.with_name('simple-glow-071.exr'));bpy.ops.render.render(write_still=True);im=bpy.data.images.load(sc.render.filepath,check_existing=False);raw=np.empty(128*128*4,dtype=np.float32);im.pixels.foreach_get(raw);raw=raw.reshape(128,128,4)[2:-2,2:-2];bpy.data.images.remove(im)
expected_alpha=.4*.75+.6*.25;expected_color=(np.array([.2,.4,.8])*.4*.75+np.array([.8,.2,.4])*.6*.25)*expected_alpha
simple=dict(pixels=int(raw.shape[0]*raw.shape[1]),expected_alpha=expected_alpha,expected_premultiplied_rgb=expected_color.tolist(),max_alpha_error=float(np.abs(raw[:,:,3]-expected_alpha).max()),max_rgb_error=float(np.abs(raw[:,:,:3]-expected_color).max()));print('SIMPLE_GLOW',simple,flush=True);assert simple['max_alpha_error']<1e-4 and simple['max_rgb_error']<1e-4,simple
report=dict(materials=results,checks=checks,simple_glow=simple,reopened=True,strict_mode_preserved=True,unreal_render_parity=False);out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('TRANSLUCENCY_PASS',flush=True)
