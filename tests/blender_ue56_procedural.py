"""Original radial ramp node branch compared against independent source formula."""
import bpy, os, sys, json
import numpy as np
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material, resolve_material
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
def pkg(stem):return '/Game/'+next(root.rglob(stem+'.uasset')).relative_to(root).with_suffix('').as_posix()
p=pkg('M_radial_ramp_soft');d=resolve_material(root,p);ns={n['kind']:n for n in d['nodes'].values()};assert ns['Constant2Vector']['value']==[.5,.5] and ns['Power']['exponent']==5 and ns['SphereMask']['hardness_percent']==0
mat=build_material(root,p,True);assert mat['UE_editor_material_status']=='partial';assert 'Opacity' in json.loads(mat['UE_editor_preserved_outputs']);strict=build_material(root,p,False);assert strict['UE_editor_material_status']=='metadata_only';assert not any(s.is_linked for s in next(n for n in strict.node_tree.nodes if n.type=='BSDF_PRINCIPLED').inputs)
nt=mat.node_tree;branch=next(n for n in nt.nodes if n.get('UE_preserved_output')=='Opacity');emit=nt.nodes.new('ShaderNodeEmission');nt.links.new(branch.outputs[0],emit.inputs['Color']);sink=next(n for n in nt.nodes if n.type=='OUTPUT_MATERIAL');nt.links.new(emit.outputs[0],sink.inputs['Surface'])
bpy.ops.mesh.primitive_plane_add(size=2);plane=bpy.context.object;plane.data.uv_layers.active.name='UV0';plane.data.materials.append(mat)
bpy.ops.object.camera_add(location=(0,0,3));cam=bpy.context.object;cam.rotation_euler=(0,0,0);cam.data.type='ORTHO';cam.data.ortho_scale=2;sc=bpy.context.scene;sc.camera=cam
sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=16;sc.cycles.use_denoising=False;sc.render.resolution_x=256;sc.render.resolution_y=256;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='OPEN_EXR';sc.render.image_settings.color_depth='32';sc.render.filepath=str(out.with_suffix('.exr'))
# Additional genuine effects material inventory. A Panner branch may be incomplete
# due to other unsupported particle expressions; verify a reachable saved branch.
panners={}
for stem in ('M_MuzzleGlow','M_WP_Linkgun_Connection','M_ImpactSmoke'):
    m=build_material(root,pkg(stem),True);m.use_fake_user=True;data=json.loads(m['UE_editor_graph']);speeds=[n['speed'] for n in data['nodes'].values() if n['kind']=='Panner'];times=[n for n in m.node_tree.nodes if n.get('UE_preview_time_seconds')];panners[stem]={'source_speeds':speeds,'time_inputs':len(times),'built_panners':sum(n.type=='COMBXYZ' and 'Panner' in n.label for n in m.node_tree.nodes)};assert len(times)<=1
assert sum(v['built_panners'] for v in panners.values())>0,panners
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));bpy.ops.render.render(write_still=True)
im=bpy.data.images.load(str(out.with_suffix('.exr')),check_existing=False);raw=np.empty(256*256*4,dtype=np.float32);im.pixels.foreach_get(raw);raw=raw.reshape(256,256,4)[:,:,0]
a=(np.arange(256)+.5)/256;x,y=np.meshgrid(a,a);expected=np.maximum(0,1-np.hypot(x-.5,y-.5)/.6000000238418579)**5;err=np.abs(raw-expected);report=dict(pixels=raw.size,mean_error=float(err.mean()),p99_error=float(np.quantile(err,.99)),max_error=float(err.max()),center=float(raw[127:129,127:129].mean()),panners=panners,reopen=True,unreal_pixel_parity=False)
assert report['mean_error']<.001 and report['p99_error']<.008 and report['center']>.95,report
# Reopened Linkgun branch: compare all three original panners at two editable
# times against explicit source UV scale, Unreal V reversal and serialized speeds.
m=bpy.data.materials['M_WP_Linkgun_Connection'];plane=next(o for o in bpy.context.scene.objects if o.type=='MESH');plane.data.materials[0]=m;nt=m.node_tree;sink=next(n for n in nt.nodes if n.type=='OUTPUT_MATERIAL');emit=nt.nodes.new('ShaderNodeEmission');nt.links.new(emit.outputs[0],sink.inputs['Surface']);clock=next(n for n in nt.nodes if n.get('UE_preview_time_seconds'));sc=bpy.context.scene
checks=[]
for suffix,scale,speed in [(0,.5,(.2,-.05)),(1,1.,(-3.,0.)),(2,.2,(-.2,.05))]:
    branch=next(n for n in nt.nodes if n.type=='COMBXYZ' and n.label==f'MaterialExpressionPanner_{suffix}');nt.links.new(branch.outputs[0],emit.inputs['Color'])
    for t in (0.,.1):
        clock.outputs[0].default_value=t;sc.render.filepath=str(out.with_name(f'panner-{suffix}-{t}.exr'));bpy.ops.render.render(write_still=True);im=bpy.data.images.load(sc.render.filepath,check_existing=False);v=np.empty(256*256*4,dtype=np.float32);im.pixels.foreach_get(v);v=v.reshape(256,256,4);bpy.data.images.remove(im)
        expected_u=x*scale+t*speed[0];expected_v=(1-y)*scale+t*speed[1];mask=(x>.02)&(x<.98)&(y>.02)&(y<.98)&(expected_u>.05)&(expected_v>.05)&(expected_u<.95)&(expected_v<.95);error=np.maximum(np.abs(v[:,:,0]-expected_u),np.abs(v[:,:,1]-expected_v))[mask];check=dict(branch=suffix,time=t,pixels=int(mask.sum()),mean_error=float(error.mean()),p99_error=float(np.quantile(error,.99)));assert check['p99_error']<.004,check;checks.append(check)
report['panner_checks']=checks
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('PROCEDURAL_PASS',report,flush=True)
