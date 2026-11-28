"""Verify generated groups, existing-name isolation, CPU evaluation and persistence."""
import bpy, sys, tempfile, json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import generated_shader_groups as lib
import umat
bpy.ops.wm.read_factory_settings(use_empty=True)
foreign=bpy.data.node_groups.new('RGBA','ShaderNodeTree')
groups=lib.ensure();assert len(groups)==22 and groups['RGBA']!=foreign
assert lib.ensure()==groups
assert all(g.nodes and g.links and g.get('UI_generated_schema')==lib.SCHEMA for g in groups.values())
mat=bpy.data.materials.new('GeneratedTest');mat.use_nodes=True;mat.use_fake_user=True;t=mat.node_tree
bpy.ops.mesh.primitive_plane_add(size=2);bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));bpy.context.collection.objects.link(cam);cam.location=(0,0,3);cam.data.type='ORTHO';cam.data.ortho_scale=1
s=bpy.context.scene;s.camera=cam;s.render.engine='CYCLES';s.cycles.samples=2;s.cycles.use_denoising=False;s.render.resolution_x=4;s.render.resolution_y=4;s.render.resolution_percentage=100;s.render.image_settings.file_format='OPEN_EXR'
em=t.nodes.new('ShaderNodeEmission');t.links.new(em.outputs[0],t.nodes['Material Output'].inputs['Surface'])
with tempfile.TemporaryDirectory() as d:
    def evaluate(key,inputs,expected,output=0):
        n=t.nodes.new('ShaderNodeGroup');n.node_tree=groups[key]
        for i,v in enumerate(inputs):n.inputs[i].default_value=v
        t.links.new(n.outputs[output],em.inputs['Color']);s.render.filepath=str(Path(d)/'pixel.exr');bpy.ops.render.render(write_still=True)
        im=bpy.data.images.load(s.render.filepath);px=tuple(im.pixels[:3]);bpy.data.images.remove(im);err=max(abs(a-b) for a,b in zip(px,expected));assert err<.002,(key,px,expected);print('PASS',key,err,flush=True)
    evaluate('Log',[8,2],(3,3,3));evaluate('Step',[.5,.5],(1,1,1));evaluate('SmoothStep',[0,1,.25],(.15625,)*3);evaluate('Sine',[.25,1],(1,1,1));evaluate('NormalToRGB',[(.6,0,.8)],(.8,.5,.9));evaluate('RGBA',[(.2,.4,.6,1),.8],(.2,.4,.6));evaluate('RGBA',[(.2,.4,.6,1),.8],(.8,)*3,4)
    path=str(Path(d)/'test.blend');bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path);assert lib.find('RGBA') and lib.find('RGBA').name!='RGBA'
print('GENERATED_GROUPS_PASS',flush=True)
