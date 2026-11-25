"""Typed switch evaluation through the actual importer and CPU Cycles."""
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
a=expression('ScalarA','Constant',R=-2.)
b=expression('ScalarB','Constant',R=3.)
s=expression('ScalarSwitch','StaticSwitchParameter',A=link(a),B=link(b),ParameterName='Choice',DefaultValue=True)
x=expression('VectorA','Constant2Vector',R=2.,G=-1.)
y=expression('VectorB','Constant2Vector',R=-2.,G=3.)
v=expression('VectorSwitch','StaticSwitchParameter',A=link(x),B=link(y),ParameterName='Choice',DefaultValue=True)
z=expression('BroadcastSwitch','StaticSwitchParameter',A=link(a),B=link(y),ParameterName='Choice',DefaultValue=True)
p=expression('Vector3A','Constant3Vector',Constant=NS(ToTupleRGB=lambda:(.1,.2,.3)))
q=expression('Vector3B','Constant3Vector',Constant=NS(ToTupleRGB=lambda:(.7,.6,.5)))
w=expression('Vector3Switch','StaticSwitchParameter',A=link(p),B=link(q),ParameterName='Choice',DefaultValue=True)
flag=expression('Flag','StaticBool',Value=False)
nested=expression('Nested','StaticSwitch',A=link(a),B=link(s),Value=link(flag))
# Create downstream nodes first: inference cannot rely on Blender creation order.
for e in (nested,z,v,s,w,a,b,x,y,p,q,flag): umat.CreateNode(e,tree,g.nodes_data,g)
for d in g.nodes_data.values(): umat.LinkSockets(tree,g.nodes_data,d)
assert not tree.get('Error'), tree.get('Error')
for e,width in ((s,1),(v,2),(z,2),(w,3),(nested,1)):
    d=g.nodes_data[e.object_name]; assert d.node['UE_switch_width']==width
    assert d.link_indirect[0].type==('VALUE' if width==1 else 'VECTOR')
    assert d.node.inputs[d.mapping.inputs['A']].is_linked and d.node.inputs[d.mapping.inputs['B']].is_linked

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
        err=max(abs(a-b) for a,b in zip(px,target)); print('TYPED_RENDER',e.object_name,px,target,err)
        assert err<.00001
    render(s,(-2,-2,-2)); render(v,(2,-1,0)); render(z,(-2,-2,-2)); render(nested,(-2,-2,-2)); render(w,(.1,.2,.3))
    record=NS(value=props(ParameterName='choice',bOverride=True,Value=False))
    applied,issues=mi.apply_overrides(mat,g,props(StaticSwitchParameters=[record]),None,None)
    assert not issues and applied[0]['targets']==4
    render(s,(3,3,3)); render(v,(-2,3,0)); render(z,(-2,3,0)); render(nested,(3,3,3)); render(w,(.7,.6,.5))
    path=str(Path(d)/'typed.blend'); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.data.materials['TypedSwitch'].node_tree.nodes['ScalarSwitch'].inputs[0].default_value==0
# Unsupported type must not be declared a successful typed translation.
mat=bpy.data.materials.new('Unsupported'); mat.use_nodes=True; g=umat.GraphData()
unknown=expression('Unknown','Constant4Vector')
u=expression('UnknownSwitch','StaticSwitchParameter',A=link(unknown),B=link(a),DefaultValue=True)
d=umat.CreateNode(u,mat.node_tree,g.nodes_data,g)
assert mat.node_tree.get('Error') and d.node.get('UE_switch_unsupported')
print('TYPED_SWITCH_PASS')
