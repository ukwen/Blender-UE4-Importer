"""Actual UE5 source art, explicit UV0 and direct normal source-art preview.
CPU emission probes validate shader sampling, not Unreal renderer parity.
"""
import bpy, os, sys, json, math, hashlib, tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
output=Path(os.environ['UE56_EDITOR_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
def pkg(stem):return '/Game/'+next(root.rglob(stem+'.uasset')).relative_to(root).with_suffix('').as_posix()
materials=[]; checks=[]; packed={}
for stem in ('MI_Quinn_01','MI_Manny_02_New'):
    mat=build_material(root,pkg(stem),True);mat.use_fake_user=True;materials.append(mat)
    normals=[n for n in mat.node_tree.nodes if n.type=='NORMAL_MAP' and n.get('UE_normal_profile')]
    assert len(normals)==1,stem
    normal=normals[0];assert normal.uv_map=='UV0';assert normal['UE_normal_green_inverted']
    tex=[n for n in mat.node_tree.nodes if n.type=='TEX_IMAGE']; assert len(tex)>=3
    for n in tex:
        assert n.image.packed_file
        v=n.inputs['Vector'];assert v.is_linked
        if n['UE_texture_package']==normal['UE_normal_source_texture']:
            assert v.links[0].from_node.uv_map=='UV0'
        packed[n.image.name]=hashlib.sha256(n.image.packed_file.data).hexdigest()
    checks.append(dict(material=stem,texture_count=len(tex),normal_texture=normal['UE_normal_source_texture'],inverted=bool(normal['UE_normal_green_inverted'])))
# Save the original translated graphs before adding the emission-only probe.
bpy.ops.wm.save_as_mainfile(filepath=str(output));bpy.ops.wm.open_mainfile(filepath=str(output))
assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
mat=bpy.data.materials['MI_Quinn_01'];tree=mat.node_tree
normal=next(n for n in tree.nodes if n.type=='NORMAL_MAP' and n.get('UE_normal_profile'));assert normal.uv_map=='UV0'
tex=next(n for n in tree.nodes if n.get('UE_texture_package')==normal['UE_normal_source_texture']);im=tex.image
# Select a real source texel with a measurable green inversion and a different
# texel for UV1, using the original packed non-color image.
w,h=im.size
candidates=[(x,y) for y in range(16,h-16,31) for x in range(16,w-16,37)]
def pixel(x,y):return tuple(im.pixels[4*(y*w+x):4*(y*w+x)+4])
a=next((x,y) for x,y in candidates if abs(pixel(x,y)[1]-.5)>.08)
p=pixel(*a);b=next((x,y) for x,y in candidates if max(abs(v-z) for v,z in zip(pixel(x,y)[:3],p[:3]))>.12)
bpy.ops.mesh.primitive_plane_add(size=2);obj=bpy.context.object;obj.data.materials.append(mat)
uv=obj.data.uv_layers.active;uv.name='UV0'
for v in uv.data:v.uv=((a[0]+.5)/w,(a[1]+.5)/h)
uv1=obj.data.uv_layers.new(name='UV1')
for v in uv1.data:v.uv=((b[0]+.5)/w,(b[1]+.5)/h)
obj.data.uv_layers.active=uv1;uv1.active_render=True
# Force nearest only for this numerical probe, not the saved material.
tex.interpolation='Closest'
em=tree.nodes.new('ShaderNodeEmission');tree.links.new(normal.inputs['Color'].links[0].from_socket,em.inputs['Color']);tree.links.new(em.outputs[0],next(n for n in tree.nodes if n.type=='OUTPUT_MATERIAL').inputs['Surface'])
cam=bpy.data.cameras.new('Probe');cam.type='ORTHO';cam.ortho_scale=1;ob=bpy.data.objects.new('Probe',cam);bpy.context.collection.objects.link(ob);ob.location=(0,0,3)
scene=bpy.context.scene;scene.camera=ob;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=8;scene.cycles.use_denoising=False;scene.render.resolution_x=8;scene.render.resolution_y=8;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR';scene.render.image_settings.color_depth='32'
with tempfile.TemporaryDirectory() as d:
    scene.render.filepath=str(Path(d)/'probe.exr');bpy.ops.render.render(write_still=True);res=bpy.data.images.load(scene.render.filepath);observed=tuple(res.pixels[4*36:4*37]);expected=(p[0],1-p[1],p[2],1.)
error=max(abs(a-b) for a,b in zip(observed,expected));assert error<.003,(observed,expected,error)
report=dict(materials=checks,packed_images=len(packed),reopen=True,uv0_texel=a,active_uv1_texel=b,expected_linear_rgba=expected,observed_linear_rgba=observed,max_error=error,scope='direct source-art RGB emission sampling only; no UE runtime normal compression or tangent parity')
output.with_suffix('.json').write_text(json.dumps(report,indent=2));print('SAMPLER_FIDELITY_PASS',report,flush=True)
