"""Controlled serialized function expressions -> actual independent layer render."""
import importlib.abc, json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from dataclasses import replace
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in {'uasset','umat','umesh','umap'}:raise AssertionError('Inherited import: '+fullname)
sys.meta_path.insert(0,Block())
from layer_function_graph import compile_function
from test_layer_function_graph import fixture
from material_layers import build
from layer_records import decode_stack
from test_layer_records import TABLE,default_record
from material_stage import incomplete_graph
bpy.ops.wm.read_factory_settings(use_empty=True)
base=fixture();blend=fixture(True);upper=replace(base,name='Upper',expressions=(replace(base.expressions[0],value=.8),)+base.expressions[1:])
def load(package,mesh,stack):
    return compile_function({'/Game/A':base,'/Game/B':upper,'/Game/Blend':blend}[package])
mat=bpy.data.materials.new('TypedLayerFunction');mat.use_nodes=True;mat.use_fake_user=True;tree=mat.node_tree
# The controlled stack's active second layer is A; use B for distinct roughness.
from layer_records import LayerStack
stack=LayerStack(('/Game/A','/Game/B'),('/Game/Blend',),(True,True))
data=NS(export=NS(object_name='Stack',properties={}));graph=NS(stack=(),scoped_param_nodes={},param_nodes={})
node=build(tree,data,graph,load,None,records=stack);assert not incomplete_graph(tree)
assert len(graph.scoped_param_nodes)==3
assert all(n.node_tree.get('UE_typed_layer_function') for n in node.node_tree.nodes if n.bl_idname=='ShaderNodeGroup')
bpy.ops.mesh.primitive_plane_add(size=2);bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));bpy.context.collection.objects.link(cam);cam.location=(0,0,3);cam.data.type='ORTHO';cam.data.ortho_scale=1
scene=bpy.context.scene;scene.camera=cam;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.cycles.use_denoising=False;scene.render.resolution_x=4;scene.render.resolution_y=4;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission');tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface']);tree.links.new(node.outputs['Roughness'],em.inputs[0]);errors=[]
with tempfile.TemporaryDirectory() as tmp:
    def render(expected):
        scene.render.filepath=str(Path(tmp)/'out.exr');bpy.ops.render.render(write_still=True);image=bpy.data.images.load(scene.render.filepath);pixel=tuple(image.pixels[:4]);bpy.data.images.remove(image);err=max(abs(a-b) for a,b in zip(pixel,(expected,expected,expected,1.)));errors.append(err);assert err<1e-5,(pixel,expected)
    render(.35)
    graph.scoped_param_nodes['LayerParameter',1,'shared'][0].node.outputs[0].default_value=.6
    render(.3)
    before={g.as_pointer() for g in bpy.data.node_groups}
    bad=replace(blend,expressions=blend.expressions[:-1])
    try:compile_function(bad)
    except ValueError:pass
    else:raise AssertionError('Invalid interface accepted')
    assert before=={g.as_pointer() for g in bpy.data.node_groups}
    path=str(Path(tmp)/'typed.blend');bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path)
    assert len([g for g in bpy.data.node_groups if g.get('UE_typed_layer_function')])==3
    scene=bpy.context.scene;render(.3)
assert not {'uasset','umat','umesh','umap'}&set(sys.modules)
print('TYPED_LAYER_FUNCTION_PASS',json.dumps(dict(controlled=True,errors=errors,max_error=max(errors),functions=3,legacy_imports=0,reopen=True)))
