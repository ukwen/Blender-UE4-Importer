"""Controlled coordinate and address modes, plus genuine textured Goblin scene acceptance."""
import os, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uasset, umat, uv_semantics


def props(**items):
    p=uasset.Properties()
    for k,v in items.items(): p[k]=NS(value=v)
    return p


bpy.ops.wm.read_factory_settings(use_empty=True)
mat=bpy.data.materials.new('UVSemantics'); mat.use_nodes=True
mat.use_fake_user=True; tree=mat.node_tree
# Build through the actual expression constructor/linker, not a parallel implementation.
exp=NS(object_name='Coord',export_class_type='MaterialExpressionTextureCoordinate',properties=props(CoordinateIndex=0,UTiling=2.,VTiling=.5))
g=umat.GraphData(); coord=umat.CreateNode(exp,tree,g.nodes_data,g)
assert coord.node.uv_map=='UV0'
transform=coord.link_indirect[0].node
assert tuple(transform.inputs[1].default_value)==(2,-.5,0)
assert tuple(transform.inputs[2].default_value)==(0,.5,0)
tex=tree.nodes.new('ShaderNodeTexImage')
inp=NS(node=exp,node_output_i=0,mask=0,mask_rgba=(0,0,0,0))
prop=NS(struct_type='ExpressionInput',value=inp)
assert umat.TryLinkSocket(tree,g.nodes_data,NS(node=tex,input_remap=None),prop,'Coordinates','Vector')
convert=tex.inputs['Vector'].links[0].from_node
assert convert.inputs[0].links[0].from_node==transform
assert tuple(convert.inputs[1].default_value)==(1,-1,0) and tuple(convert.inputs[2].default_value)==(0,1,0)
# Actual render of coordinate conversion with UV1 active, a deliberately different layer.
bpy.ops.mesh.primitive_plane_add(size=2)
obj=bpy.context.object; obj.data.materials.append(mat)
uv0=obj.data.uv_layers.active; uv0.name='UV0'
for item in uv0.data: item.uv=(.2,.7)
uv1=obj.data.uv_layers.new(name='UV1')
for item in uv1.data: item.uv=(.9,.1)
obj.data.uv_layers.active=uv1; uv1.active_render=True
em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(convert.outputs[0],em.inputs['Color']); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
cam=bpy.data.cameras.new('Camera'); cam.type='ORTHO'; cam.ortho_scale=1
camera=bpy.data.objects.new('Camera',cam); bpy.context.collection.objects.link(camera); camera.location=(0,0,3)
scene=bpy.context.scene; scene.camera=camera; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=16; scene.cycles.use_denoising=False
scene.render.resolution_x=8; scene.render.resolution_y=8; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
with tempfile.TemporaryDirectory() as d:
    scene.render.filepath=str(Path(d)/'uv.exr'); bpy.ops.render.render(write_still=True)
    img=bpy.data.images.load(scene.render.filepath); px=tuple(img.pixels[4*(4*8+4):4*(4*8+4)+4]); print('UV_RENDER_PIXEL',px)
    assert max(abs(a-b) for a,b in zip(px,(.4,.85,0,1)))<.002, px
    bpy.data.images.remove(img)
# Default UV0 is explicit and shared, not active UV.
a=tree.nodes.new('ShaderNodeTexImage'); b=tree.nodes.new('ShaderNodeTexImage')
uv_semantics.texture_coordinates(tree,a,props()); uv_semantics.texture_coordinates(tree,b,props())
assert a.inputs['Vector'].links[0].from_node==b.inputs['Vector'].links[0].from_node
assert a.inputs['Vector'].links[0].from_node.uv_map=='UV0'
image=bpy.data.images.new('Sampler',2,2)
for addr,ext in [('TA_Wrap','REPEAT'),('TA_Clamp','EXTEND'),('TA_Mirror','MIRROR')]:
    image['UE_address_x']=image['UE_address_y']=addr
    umat.SetNodeTexture(a,image); assert a.extension==ext
# Shared sampler overrides texture asset; mixed axes remain explicitly unresolved.
a['UE_sampler_source']='SSM_Clamp_WorldGroupSettings'; umat.SetNodeTexture(a,image); assert a.extension=='EXTEND'
a['UE_sampler_source']='SSM_FromTextureAsset'; image['UE_address_y']='TA_Clamp'; umat.SetNodeTexture(a,image)
assert tree['Error'] and a.get('UE_address_unsupported')
print('SAMPLER_ADDRESS_PASS')
# Load scene produced by genuine native project test and check bindings on all original images.
bpy.ops.wm.open_mainfile(filepath=os.environ['UE_UV_SCENE'])
materials=[m for m in bpy.data.materials if m.get('UE_instance_chain')]
assert len(materials)==2
for m in materials:
    for n in m.node_tree.nodes:
        if n.type!='TEX_IMAGE': continue
        assert n.image.packed_file and n.inputs['Vector'].links[0].from_node.uv_map=='UV0'
        assert 'UE_address_x' in n.image and 'UE_address_y' in n.image
        assert n.extension=='REPEAT' and not n.get('UE_address_unsupported')
    print('GENUINE_UV0_PASS',m.name)
print('UV_SEMANTICS_PASS')
