"""Controlled serialized layer topology -> independent Blender composition/replay."""
import importlib.abc, json, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in {'uasset','umat','umesh','umap'}: raise AssertionError('Inherited import: '+fullname)
sys.meta_path.insert(0,Block())
from test_layer_records import TABLE, IDS, default_record, override_fields
from layer_records import decode_stack,decode_override
from material_attributes import FIELDS, interface_bundle, by_id
from material_layers import build, replace_snapshot
from material_instance import apply_overrides
from material_stage import incomplete_graph

class Props(dict):
    def TryGetValue(self,key,default=None):
        p=self.get(key);return p.value if p else default

def props(**kw):return Props({k:NS(value=v) for k,v in kw.items()})

def loader(package,mesh,stack):
    if package not in ('/Game/A','/Game/B','/Game/Blend'):raise ValueError('Missing test function')
    group=bpy.data.node_groups.new(package,'ShaderNodeTree');out=group.nodes.new('NodeGroupOutput');inp=group.nodes.new('NodeGroupInput')
    output=interface_bundle(group,'Result','OUTPUT');inputs={};registry={}
    param=group.nodes.new('ShaderNodeValue');param.outputs[0].default_value=.2 if package=='/Game/A' else .8 if package=='/Game/B' else .25
    registry['Shared']=[NS(classname='MaterialExpressionScalarParameter',node=param)]
    if package=='/Game/Blend':
        for k in ('Bottom','Top'):inputs[k]=interface_bundle(group,k,'INPUT')
        for field,value in FIELDS.items():
            mix=group.nodes.new('ShaderNodeMix');vector=isinstance(value,tuple);mix.data_type='VECTOR' if vector else 'FLOAT';mix.clamp_factor=False
            group.links.new(param.outputs[0],mix.inputs[0]);group.links.new(by_id(inp.outputs,inputs['Bottom'][field]),mix.inputs[4 if vector else 2]);group.links.new(by_id(inp.outputs,inputs['Top'][field]),mix.inputs[5 if vector else 3]);group.links.new(mix.outputs[1 if vector else 0],by_id(out.inputs,output[field]))
    else:
        group.links.new(param.outputs[0],by_id(out.inputs,output['Roughness']))
    group['UE_function_usage']='MaterialLayerBlend' if package=='/Game/Blend' else 'MaterialLayer'
    group['UE_input_ids']=json.dumps(inputs);group['UE_input_order']=json.dumps(list(inputs));group['UE_output_ids']=json.dumps({'out':output})
    return group,NS(param_nodes=registry)

bpy.ops.wm.read_factory_settings(use_empty=True)
mat=bpy.data.materials.new('NativeLayerRecords');mat.use_nodes=True;mat.use_fake_user=True;tree=mat.node_tree
stack=decode_stack(default_record(),TABLE);graph=NS(stack=(),scoped_param_nodes={},param_nodes={});data=NS(export=NS(object_name='Stack',properties=props(ParameterName='Stack')))
node=build(tree,data,graph,loader,None,records=stack);assert not incomplete_graph(tree)
assert not apply_overrides(mat,graph,props(),None,None,decode_override(override_fields(),TABLE))[1]
def set_scalar(index,value):
    entry=NS(value=props(ParameterInfo=props(Name='Shared',Association='LayerParameter',Index=index),ParameterValue=value))
    assert not apply_overrides(mat,graph,props(ScalarParameterValues=[entry]),None,None)[1]
set_scalar(2,.8)
bpy.ops.mesh.primitive_plane_add(size=2);bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));bpy.context.collection.objects.link(cam);cam.location=(0,0,3);cam.data.type='ORTHO';cam.data.ortho_scale=1
scene=bpy.context.scene;scene.camera=cam;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.cycles.use_denoising=False;scene.render.resolution_x=4;scene.render.resolution_y=4;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission');tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface']);tree.links.new(tree.nodes['Stack'].outputs['Roughness'],em.inputs[0]);errors=[]
with tempfile.TemporaryDirectory() as tmp:
    def render(expected):
        scene.render.filepath=str(Path(tmp)/'out.exr');bpy.ops.render.render(write_still=True);image=bpy.data.images.load(scene.render.filepath);pixel=tuple(image.pixels[:4]);bpy.data.images.remove(image);err=max(abs(a-b) for a,b in zip(pixel,(expected,expected,expected,1.)));errors.append(err);assert err<1e-5,(pixel,expected)
    render(.35)
    # Move active layer GUID from slot 2 to slot 1, and keep its override.
    new=decode_override(override_fields(guids=(IDS[0],IDS[2],IDS[1]),indices=(-1,-1,-2),blends=(-3,0),states=(1,1,0)),TABLE)
    assert not apply_overrides(mat,graph,props(),None,None,new)[1];render(.35)
    assert abs(graph.scoped_param_nodes['LayerParameter',1,'shared'][0].node.outputs[0].default_value-.8)<1e-6
    current=tree.nodes['Stack'].node_tree;before={g.as_pointer() for g in bpy.data.node_groups}
    try:replace_snapshot(mat,graph,(['/Game/Missing','/Game/A','/Game/B'],['/Game/Blend',None],[True,True,False]),list(new.guids))
    except ValueError:pass
    else:raise AssertionError('Missing function accepted')
    assert tree.nodes['Stack'].node_tree==current and before=={g.as_pointer() for g in bpy.data.node_groups};render(.35)
    path=str(Path(tmp)/'native.blend');bpy.ops.wm.save_as_mainfile(filepath=path);bpy.ops.wm.open_mainfile(filepath=path)
    assert json.loads(bpy.data.materials['NativeLayerRecords'].node_tree.nodes['Stack']['UE_layer_guids'])==list(map(str,new.guids))
assert not {'uasset','umat','umesh','umap'}&set(sys.modules)
print('NATIVE_LAYER_RECORDS_PASS',json.dumps(dict(render_errors=errors,max_error=max(errors),reopen=True,rollback=True,controlled=True,legacy_imports=0)))
