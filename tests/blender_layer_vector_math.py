"""Controlled tagged vector and scalar functions, actual CPU rendering and reopen."""
import importlib.abc, json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in {'uasset','umat','umesh','umap'}:raise AssertionError('Inherited import: '+fullname)
sys.meta_path.insert(0,Block())
from layer_function_graph import compile_function
from test_layer_function_graph import math_fixture
from layer_records import LayerStack
from material_layers import build
from material_instance import apply_overrides
from scoped_parameters import ParameterValue
from material_stage import incomplete_graph
bpy.ops.wm.read_factory_settings(use_empty=True)
fn=math_fixture()
mat=bpy.data.materials.new('VectorMath');mat.use_nodes=True;mat.use_fake_user=True;tree=mat.node_tree
stack=LayerStack(('/Game/Math',),(),(True,));graph=NS(stack=(),scoped_param_nodes={},param_nodes={});data=NS(export=NS(object_name='Stack',properties={}))
node=build(tree,data,graph,lambda *args:compile_function(fn),None,records=stack)
assert not incomplete_graph(tree)
bpy.ops.mesh.primitive_plane_add(size=2);bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));bpy.context.collection.objects.link(cam);cam.location=(0,0,3);cam.data.type='ORTHO';cam.data.ortho_scale=1
scene=bpy.context.scene;scene.camera=cam;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.cycles.use_denoising=False;scene.render.resolution_x=4;scene.render.resolution_y=4;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission');tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface']);errors=[]
with tempfile.TemporaryDirectory() as tmp:
    def render(expected):
        scene.render.filepath=str(Path(tmp)/'out.exr');bpy.ops.render.render(write_still=True);image=bpy.data.images.load(scene.render.filepath);pixel=tuple(image.pixels[:4]);bpy.data.images.remove(image);err=max(abs(a-b) for a,b in zip(pixel,(*expected,1.)));errors.append(err);assert err<1e-5,(pixel,expected)
    tree.links.new(node.outputs['BaseColor'],em.inputs[0]);render((.2,.4,.6))
    tree.links.new(node.outputs['Roughness'],em.inputs[0]);render((.8,)*3)
    # Replay via the production override API, not a manual socket edit.
    from uuid import UUID
    from scoped_parameters import ParameterValue
    target=graph.scoped_param_nodes['LayerParameter',0,'tint'][0].node
    assert abs(target.inputs['A'].default_value-.75)<1e-6
    # Populate detached typed vector record using the real decoder dataclass.
    value=ParameterValue('vector','Tint',(.7,.3,.1,.9),'LayerParameter',0,UUID(int=1))
    applied,issues=apply_overrides(mat,graph,None,None,None,native_snapshot=None,native_parameters=(value,))
    assert len(applied)==1 and not issues,(applied,issues)
    assert abs(target.inputs['A'].default_value-.9)<1e-6
    tree.links.new(node.outputs['BaseColor'],em.inputs[0]);render((.7,.3,.1))
    path=str(Path(tmp)/'vector-math.blend');bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path)
    scene=bpy.context.scene;render((.7,.3,.1))
    fn_group=next(g for g in bpy.data.node_groups if g.get('UE_typed_layer_function'))
    target=next(n for n in fn_group.nodes if n.label=='Tint');assert abs(target.inputs['A'].default_value-.9)<1e-6
assert not {'uasset','umat','umesh','umap'}&set(sys.modules)
print('LAYER_VECTOR_MATH_PASS',json.dumps(dict(controlled=True,errors=errors,max_error=max(errors),renders=len(errors),legacy_imports=0,alpha_preserved=True,reopen=True)))
