"""Render mixed-axis sampling and an explicit UV0 tangent basis in Blender CPU Cycles."""
import os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import umat, uv_semantics
bpy.ops.wm.read_factory_settings(use_empty=True)
mat=bpy.data.materials.new('SamplerNormalTest'); mat.use_nodes=True
tree=mat.node_tree; shader=tree.nodes['Principled BSDF']
bpy.ops.mesh.primitive_plane_add(size=2); obj=bpy.context.object; obj.data.materials.append(mat)
uv=obj.data.uv_layers.active; uv.name='UV0'
for loop in obj.data.loops:
    x,y,z=obj.data.vertices[loop.vertex_index].co; uv.data[loop.index].uv=((x+1)/2,(y+1)/2)
uv1=obj.data.uv_layers.new(name='UV1')
for i, item in enumerate(uv.data): uv1.data[i].uv=(item.uv.y,1-item.uv.x)
obj.data.uv_layers.active=uv1; uv1.active_render=True
camera=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera')); bpy.context.collection.objects.link(camera)
camera.location=(0,0,3); camera.data.type='ORTHO'; camera.data.ortho_scale=1
scene=bpy.context.scene; scene.camera=camera; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=8; scene.cycles.use_denoising=False
scene.render.resolution_x=4; scene.render.resolution_y=4; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
def render(source, expected):
    tree.links.new(source,em.inputs['Color'])
    with tempfile.TemporaryDirectory() as d:
        scene.render.filepath=str(Path(d)/'result.exr'); bpy.ops.render.render(write_still=True)
        img=bpy.data.images.load(scene.render.filepath); px=tuple(img.pixels[0:4]); bpy.data.images.remove(img)
    error=max(abs(a-b) for a,b in zip(px,expected)); print('PIXEL',px,'EXPECTED',expected,'ERROR',error)
    assert error<.002, (px,expected)
# 2x2 data texture: bottom red, green; top blue, white.
image=bpy.data.images.new('Data',2,2,float_buffer=True); image.colorspace_settings.name='Non-Color'
image.pixels[:]=[1,0,0,1, 0,1,0,1, 0,0,1,1, 1,1,1,1]; image.update()
tex=tree.nodes.new('ShaderNodeTexImage'); coords=tree.nodes.new('ShaderNodeCombineXYZ')
coords.inputs[0].default_value=1.25; coords.inputs[1].default_value=1.4
uv_semantics.connect_sample(tree,tex,coords.outputs[0]); image['UE_address_x']='TA_Wrap'; image['UE_address_y']='TA_Clamp'
umat.SetNodeTexture(tex,image)
render(tex.outputs['Color'],(0,0,1,1))
# Bilinear filtering across the wrapped U seam, without blending through the clamped V edge.
coords.inputs[0].default_value=1.0
render(tex.outputs['Color'],(.5,.5,1,1))
# Mirror U, wrap V: negative U mirrors to .75, negative V wraps to .25.
coords.inputs[0].default_value=-.75; coords.inputs[1].default_value=-.75
image['UE_address_x']='TA_Mirror'; image['UE_address_y']='TA_Wrap'; umat.SetNodeTexture(tex,image)
render(tex.outputs['Color'],(0,1,0,1))
# Change source after the helper exists; update sampler to uniform mode and verify restoration.
new=tree.nodes.new('ShaderNodeCombineXYZ'); new.inputs[0].default_value=.25; new.inputs[1].default_value=.25
uv_semantics.connect_sample(tree,tex,new.outputs[0]); image['UE_address_x']='TA_Clamp'; image['UE_address_y']='TA_Clamp'; umat.SetNodeTexture(tex,image)
assert not tex.get('UE_address_helper') and tex.inputs['Vector'].links[0].from_node==new
render(tex.outputs['Color'],(1,0,0,1))
# Tangent vector (0.6,0,0.8) in UV0 should point toward +X in world space.
umat.TryAppendNodeGroups(); data=NS(node=shader,input_remap=None)
class Props(dict):
    def TryGetValue(self,key,default=None): return self.get(key,default)
umat.TryRemapNormal(Props(Normal=True),tree,data)
normal=next(n for n in tree.nodes if n.type=='NORMAL_MAP'); assert normal.uv_map=='UV0'
data.input_remap['Normal'].default_value=(.6,0,.8)
encode=tree.nodes.new('ShaderNodeVectorMath'); encode.operation='MULTIPLY_ADD'; encode.inputs[1].default_value=(.5,.5,.5); encode.inputs[2].default_value=(.5,.5,.5); tree.links.new(normal.outputs[0],encode.inputs[0])
render(encode.outputs[0],(.8,.5,.9,1))
print('MIXED_ADDRESS_NORMAL_RENDER_PASS')

# Check the genuine scene produced by the expanded fixture regression.
bpy.ops.wm.open_mainfile(filepath=os.environ['UE_UV_SCENE'])
materials=[m for m in bpy.data.materials if m.get('UE_instance_chain')]
assert len(materials)==2
for m in materials:
    maps=[n for n in m.node_tree.nodes if n.type=='NORMAL_MAP']
    assert len(maps)==1 and maps[0].uv_map=='UV0'
    assert len([n for n in m.node_tree.nodes if n.type=='TEX_IMAGE' and n.image.packed_file])==3
print('GENUINE_NORMAL_UV0_REOPEN_PASS')
