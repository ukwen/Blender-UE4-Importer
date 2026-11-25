"""Controlled package exports through actual function/root graph importer."""
import sys,tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset,umat,material_attributes as ma

def props(**items):
    p=uasset.Properties()
    for k,v in items.items(): p[k]=NS(value=v,type='StructProperty',struct_type='ExpressionInput')
    return p

def exp(name,kind,**items):
    return NS(object_name=name,export_class_type='MaterialExpression'+kind,properties=props(**items))

def link(e,index=0): return NS(node=e,node_index=1,node_output_i=index,mask=0,mask_rgba=(0,0,0,0))

def root(name,kind,expressions,**items):
    return NS(object_name=name,export_class_type=kind,properties=props(**items,**{('FunctionExpressions' if kind=='MaterialFunction' else 'Expressions'):[NS(value=e) for e in expressions]}))

class Fixture:
    def __init__(self,export): self.export=export
    def __enter__(self): return NS(exports=[self.export],f=NS(byte_stream=NS(name='controlled.uasset')))
    def __exit__(self,*args): pass

bpy.ops.wm.read_factory_settings(use_empty=True)
# Function receives a bundle and a scalar; blends with another bundle.
fi=exp('Input','FunctionInput',InputType='FunctionInput_MaterialAttributes',InputName='Surface',Id='in-bundle')
weight=exp('Weight','FunctionInput',InputType='FunctionInput_Scalar',InputName='Weight',Id='in-scalar')
rough=exp('Rough','Constant',R=.8)
other=exp('Other','MakeMaterialAttributes',Roughness=link(rough))
blend=exp('Blend','BlendMaterialAttributes',A=link(fi),B=link(other),Alpha=link(weight))
fo=exp('Out','FunctionOutput',OutputName='Surface',Id='out-bundle',A=link(blend))
so=exp('ScalarOut','FunctionOutput',OutputName='Weight',Id='out-scalar',A=link(weight))
fn=root('AttributeFunction','MaterialFunction',[fo,so,blend,other,rough,weight,fi])
color=exp('Color','Constant3Vector',Constant=NS(ToTupleRGB=lambda:(.4,.6,.8)))
base=exp('Base','MakeMaterialAttributes',BaseColor=link(color))
alpha=exp('Alpha','Constant',R=.25)
call=exp('Call','MaterialFunctionCall',MaterialFunction=NS(object_name='AttributeFunction'),FunctionInputs=[props(ExpressionInputId='in-bundle',Input=link(base)),props(ExpressionInputId='in-scalar',Input=link(alpha))],FunctionOutputs=[props(ExpressionOutputId='out-scalar'),props(ExpressionOutputId='out-bundle')])
call2=exp('Call2','MaterialFunctionCall',MaterialFunction=NS(object_name='AttributeFunction'),FunctionInputs=[props(ExpressionInputId='in-bundle',Input=link(call,1)),props(ExpressionInputId='in-scalar',Input=link(alpha))],FunctionOutputs=[props(ExpressionOutputId='out-scalar'),props(ExpressionOutputId='out-bundle')])
matroot=root('FunctionSurface','Material',[call2,call,base,color,alpha],bUseMaterialAttributes=True,MaterialAttributes=link(call2,1))
def load(*args,**kwargs):
    with patch.object(umat,'UAsset',return_value=Fixture(fn)): return umat.ImportNodeGraph('controlled_function.uasset')
with patch.object(umat,'UAsset',return_value=Fixture(matroot)),patch.object(umat,'ImportMaterialFunction',side_effect=load):
    mat,g=umat.ImportNodeGraph('controlled_material.uasset')
mat.use_fake_user=True; tree=mat.node_tree
from material_stage import incomplete_graph
assert not incomplete_graph(tree),[(n.name,n.get('UE_attribute_error')) for n in tree.nodes]
assert tree.nodes['Call'].node_tree!=tree.nodes['Call2'].node_tree
assert set(g.nodes_data['Call'].function_bundles)=={1}
assert tree.nodes['Principled BSDF'].inputs['Roughness'].links[0].from_node.name=='Call2'
assert len([s for s in tree.nodes['Call2'].inputs if s.is_linked])==9
bpy.ops.mesh.primitive_plane_add(size=2); bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera')); bpy.context.collection.objects.link(cam)
cam.location=(0,0,3); cam.data.type='ORTHO'; cam.data.ortho_scale=1
scene=bpy.context.scene; scene.camera=cam; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=4; scene.cycles.use_denoising=False
scene.render.resolution_x=4; scene.render.resolution_y=4; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
with tempfile.TemporaryDirectory() as tmp:
    def render(src,expected):
        tree.links.new(src,em.inputs['Color']); scene.render.filepath=str(Path(tmp)/'render.exr'); bpy.ops.render.render(write_still=True)
        im=bpy.data.images.load(scene.render.filepath); px=tuple(im.pixels[:4]); bpy.data.images.remove(im)
        err=max(abs(a-b) for a,b in zip(px,expected+(1.,))); print('FUNCTION_RENDER',err,px); assert err<.00001
    render(g.nodes_data['Call'].function_bundles[1]['BaseColor'],(.3,.45,.6))
    render(g.nodes_data['Call2'].function_bundles[1]['BaseColor'],(.225,.3375,.45))
    render(g.nodes_data['Call2'].function_bundles[1]['Roughness'],(.63125,)*3)
    render(g.nodes_data['Call2'].link_indirect[0],(.25,)*3)
    out=str(Path(tmp)/'function.blend'); bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
    assert bpy.data.materials['FunctionSurface'].node_tree.nodes['Call2'].inputs['Surface.BaseColor'].is_linked
print('ATTRIBUTE_FUNCTION_PASS')
