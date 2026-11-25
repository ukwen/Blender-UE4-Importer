"""Typed channel operation evaluation through the actual importer and CPU Cycles."""
import sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uasset, umat, material_instance as mi


def props(**items):
    p = uasset.Properties()
    for k,v in items.items(): p[k] = NS(value=v, type='StructProperty', struct_type='ExpressionInput')
    return p


def link(exp):
    return NS(node=exp,node_output_i=0,mask=0,mask_rgba=(0,0,0,0))


def expression(name, kind, **kwargs):
    return NS(object_name=name,export_class_type='MaterialExpression'+kind,properties=props(**kwargs))


bpy.ops.wm.read_factory_settings(use_empty=True)
umat.TryAppendNodeGroups()
mat=bpy.data.materials.new('TypedSwitch'); mat.use_nodes=True
mat.use_fake_user=True; tree=mat.node_tree; g=umat.GraphData()
a=expression('A','Constant',R=-2.)
b=expression('B','Constant',R=3.)
x=expression('X','Constant2Vector',R=.25,G=-.75)
y=expression('Y','Constant2Vector',R=2.,G=1.)
ab=expression('AB','AppendVector',A=link(a),B=link(b))
abc=expression('ABC','AppendVector',A=link(ab),B=link(a))
full=expression('Full','AppendVector',A=link(x),B=link(y))
mask=expression('MaskGA','ComponentMask',Input=link(full),G=True,A=True)
mask2=expression('MaskRB','ComponentMask',Input=link(abc),R=True,B=True)
mask3=expression('MaskB','ComponentMask',Input=link(full),B=True)
combined=expression('Combined','AppendVector',A=link(mask),B=link(mask3))
for e in (combined,mask3,mask2,mask,full,abc,ab,a,b,x,y): umat.CreateNode(e,tree,g.nodes_data,g)
for d in g.nodes_data.values(): umat.LinkSockets(tree,g.nodes_data,d)
assert not tree.get('Error')
assert g.nodes_data['Full'].node['UE_channel_width']==4

bpy.ops.mesh.primitive_plane_add(size=2); bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera')); bpy.context.collection.objects.link(cam)
cam.location=(0,0,3); cam.data.type='ORTHO'; cam.data.ortho_scale=1
scene=bpy.context.scene; scene.camera=cam; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=4; scene.cycles.use_denoising=False
scene.render.resolution_x=4; scene.render.resolution_y=4; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
encode=tree.nodes.new('ShaderNodeVectorMath'); encode.operation='MULTIPLY_ADD'; encode.inputs[1].default_value=(.1,.1,.1); encode.inputs[2].default_value=(.5,.5,.5); tree.links.new(encode.outputs[0],em.inputs['Color'])
with tempfile.TemporaryDirectory() as d:
    def render(e,expected):
        tree.links.new(g.nodes_data[e.object_name].link_indirect[0],encode.inputs[0])
        scene.render.filepath=str(Path(d)/'result.exr'); bpy.ops.render.render(write_still=True)
        im=bpy.data.images.load(scene.render.filepath); px=tuple(im.pixels[:4]); bpy.data.images.remove(im)
        target=tuple(.5+.1*f for f in expected)+(1,)
        err=max(abs(a-b) for a,b in zip(px,target)); print('CHANNEL_RENDER',e.object_name,px,target,err)
        assert err<.00001
    render(ab,(-2,3,0)); render(abc,(-2,3,-2)); render(mask,(-.75,1,0)); render(mask2,(-2,-2,0)); render(mask3,(2,2,2)); render(combined,(-.75,1,2))
    path=str(Path(d)/'channels.blend'); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.data.materials['TypedSwitch'].node_tree.nodes['Full']['UE_channel_width']==4
print('CHANNEL_OPS_PASS')
