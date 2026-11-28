"""Original saved instance provenance and unclamped RGB lerp in CPU Cycles."""
import bpy,os,sys,json,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
def pkg(stem):return '/Game/'+next(root.rglob(stem+'.uasset')).relative_to(root).with_suffix('').as_posix()
materials={}
for stem in ('MI_ThirdPersonColWay','MI_PrototypeGrid_TopDark','MI_Enemy_Face','MI_GlowNT','M_SimpleGlow'):
    m=build_material(root,pkg(stem),True);m.use_fake_user=True;materials[stem]=json.loads(m['UE_parameter_audit'])
assert sum(x['status']=='unmatched' for x in materials['MI_Enemy_Face'])==5
assert len(next(x for x in materials['MI_PrototypeGrid_TopDark'] if x['name']=='ObjectAligned')['matched_nodes'])==4
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
assert materials=={stem:json.loads(bpy.data.materials[stem]['UE_parameter_audit']) for stem in materials}
m=bpy.data.materials['M_SimpleGlow'];nt=m.node_tree
# Probe the actual original graph's emissive expression, bypassing the
# transparent surface for the numerical test, not in the saved scene.
bs=next(n for n in nt.nodes if n.type=='BSDF_PRINCIPLED');socket=bs.inputs['Emission Color'].links[0].from_socket
em=nt.nodes.new('ShaderNodeEmission');nt.links.new(socket,em.inputs['Color']);nt.links.new(em.outputs[0],next(n for n in nt.nodes if n.type=='OUTPUT_MATERIAL').inputs['Surface'])
for label,val in [('Color (alpha parameter)',1.),('Custom Prim Switch',0.)]:next(n for n in nt.nodes if n.label==label).outputs[0].default_value=val
next(n for n in nt.nodes if n.type=='VALUE' and 'preview alpha' in n.label).outputs[0].default_value=1.
a=(.3,.4,.5);b=(.5,.6,.7)
next(n for n in nt.nodes if n.label=='Color').outputs[0].default_value=(*b,1.)
next(n for n in nt.nodes if n.type=='RGB' and 'preview RGB' in n.label).outputs[0].default_value=(*a,1.)
factor=next(n for n in nt.nodes if n.label=='Custom Prim Switch').outputs[0]
bpy.ops.mesh.primitive_plane_add(size=2);bpy.context.object.data.materials.append(m);bpy.ops.object.camera_add(location=(0,0,3));cam=bpy.context.object;cam.data.type='ORTHO';cam.data.ortho_scale=1
sc=bpy.context.scene;sc.camera=cam;sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=8;sc.cycles.use_denoising=False;sc.cycles.use_adaptive_sampling=False;sc.render.resolution_x=sc.render.resolution_y=8;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='OPEN_EXR';sc.render.image_settings.color_depth='32';checks=[]
with tempfile.TemporaryDirectory() as d:
    for f in (-.5,.25,1.5):
        factor.default_value=f;sc.render.filepath=str(Path(d)/'probe.exr');bpy.ops.render.render(write_still=True);im=bpy.data.images.load(sc.render.filepath,check_existing=False);observed=list(im.pixels[4*36:4*36+3]);bpy.data.images.remove(im);expected=[x+(y-x)*f for x,y in zip(a,b)];error=max(abs(x-y) for x,y in zip(observed,expected));assert error<1e-5,(f,observed,expected);checks.append(dict(factor=f,expected=expected,observed=observed,max_error=error))
out.with_suffix('.json').write_text(json.dumps(dict(materials=materials,lerp=checks,reopen=True,scope='original source graph, diagnostic emission probe, edited factor values; no Unreal runtime parity'),indent=2));print('INSTANCE_FIDELITY_PASS',checks,flush=True)
