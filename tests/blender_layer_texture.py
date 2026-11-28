"""Controlled layer graph + original packed UE4.27 texture, menu, replay and rollback."""
import hashlib, importlib.abc, json, os, shutil, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
from uuid import UUID
import bpy
sys.path[:0]=[str(Path(__file__).resolve().parents[1]),str(Path(__file__).resolve().parent)]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in {'uasset','umat','umesh','umap'}:raise AssertionError('Inherited import: '+fullname)
sys.meta_path.insert(0,Block())
from layer_function_graph import compile_function, read_function, load_function
from test_layer_function_graph import texture_fixture_data
from asset_entrypoints import register, unregister
from project_session import new_ids
from scoped_parameters import ParameterValue
from material_instance import apply_overrides
from shader_texture_binding import assign_image
from material_layers import build
from layer_records import LayerStack
from native_texture import png_bytes
bpy.ops.wm.read_factory_settings(use_empty=True);register()
root=Path(__file__).resolve().parents[1]
source=Path(os.environ['UE_CLASSIC_MATERIAL_FIXTURES'])/'T_PolygonGoblinWarCamp_Texture_01_A.uasset'
expected=json.loads((root/'docs/CLASSIC_MATERIAL_FIXTURES.json').read_text())[source.name]['sha256'];assert hashlib.sha256(source.read_bytes()).hexdigest()==expected
raw_fixture=texture_fixture_data()
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp);content=project/'Content';content.mkdir();(project/'Fixture.uproject').write_text('{}');shutil.copyfile(source,content/'Source.uasset')
    # The function package records are controlled; texture bytes are original.
    p=content/'Function.uasset';p.write_bytes(b'controlled')
    # Scope fake package dispatch to the function alone; real texture decoding remains unmodified.
    from package_inspector import inspect_package as original_inspect
    from package_records import read_package as original_read
    with patch('layer_function_graph.read_package',return_value=raw_fixture),patch('package_inspector.inspect_package',side_effect=lambda path,*a,**k:raw_fixture[0] if Path(path)==p else original_inspect(path,*a,**k)),patch('package_records.read_package',side_effect=lambda path,*a,**k:raw_fixture if Path(path)==p else original_read(path,*a,**k)):
        assert getattr(bpy.ops,'import').umat(filepath=str(p))=={'FINISHED'}
        standalone=next(g for g in bpy.data.node_groups if g.get('UE_typed_layer_function'));assert standalone.use_fake_user
        fn=read_function(p)
        mat=bpy.data.materials.new('LayerTexture');mat.use_nodes=True;mat.use_fake_user=True;tree=mat.node_tree
        graph=NS(stack=(),scoped_param_nodes={},param_nodes={});data=NS(export=NS(object_name='Stack',properties={}))
        node=build(tree,data,graph,lambda *a:load_function(p),None,records=LayerStack(('/Game/Layer',),(),(True,)))
    target=graph.scoped_param_nodes['LayerParameter',0,'tex'][0].node;image=target.image
    assert image.packed_file and tuple(image.size)==(4096,4096)
    digest=hashlib.sha256(image.packed_file.data).hexdigest();assert digest==json.loads((root/'docs/CLASSIC_TEXTURE522_BASELINE.json').read_text())[source.name]['sha256'],digest
    assert target['UE_texture_package']=='/Game/Source'
    def packed(name,rgba):
        f=project/(name+'.png');f.write_bytes(png_bytes(2,2,bytes(rgba)*4));im=bpy.data.images.load(str(f));im.pack();return im
    # Refusal must remove a newly allocated image as well as the function group.
    before=set(new_ids())
    def bad_loader(package):
        im=packed('Wrong',(255,0,0,255));im.colorspace_settings.name='Non-Color';return im
    try:compile_function(fn,bad_loader)
    except NotImplementedError:pass
    else:raise AssertionError('Mismatched color-space accepted')
    assert set(new_ids())==before
    override=packed('Override',(0,255,0,255))
    applied,issues=apply_overrides(mat,graph,None,None,assign_image,native_snapshot=None,native_parameters=(ParameterValue('texture','Tex','/Game/Override','LayerParameter',0,UUID(int=1)),),native_texture_loader=lambda p:override)
    assert len(applied)==1 and not issues,(applied,issues);assert target.image==override and target['UE_texture_package']=='/Game/Override'
    before=set(new_ids())
    applied,issues=apply_overrides(mat,graph,None,None,assign_image,native_snapshot=None,native_parameters=(ParameterValue('texture','Tex','/Game/Invalid','LayerParameter',0,UUID(int=1)),),native_texture_loader=bad_loader)
    assert not applied and issues and set(new_ids())==before and target.image==override
    bpy.ops.mesh.primitive_plane_add(size=2);obj=bpy.context.object;obj.data.uv_layers.active.name='UV0';obj.data.materials.append(mat)
    cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera'));bpy.context.collection.objects.link(cam);cam.location=(0,0,3);cam.data.type='ORTHO';cam.data.ortho_scale=1
    scene=bpy.context.scene;scene.camera=cam;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.cycles.use_denoising=False;scene.render.resolution_x=4;scene.render.resolution_y=4;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR'
    em=tree.nodes.new('ShaderNodeEmission');tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface']);tree.links.new(node.outputs['BaseColor'],em.inputs[0]);errors=[]
    def render():
        scene.render.filepath=str(project/'out.exr');bpy.ops.render.render(write_still=True);im=bpy.data.images.load(scene.render.filepath);pixel=tuple(im.pixels[:4]);bpy.data.images.remove(im);err=max(abs(a-b) for a,b in zip(pixel,(0.,1.,0.,1.)));errors.append(err);assert err<1e-5,pixel
    render();blend=str(project/'test.blend');bpy.ops.wm.save_as_mainfile(filepath=blend);bpy.ops.wm.open_mainfile(filepath=blend);scene=bpy.context.scene;render()
    assert any(g.use_fake_user and g.get('UE_typed_layer_function') for g in bpy.data.node_groups)
    assert any(i.packed_file and hashlib.sha256(i.packed_file.data).hexdigest()==digest for i in bpy.data.images)
assert not {'uasset','umat','umesh','umap'}&set(sys.modules)
unregister();print('LAYER_TEXTURE_PASS',json.dumps(dict(controlled_graph=True,original_texture_sha256=digest,original_texture_size=[4096,4096],errors=errors,rollback=True,reopen=True,menu=True,legacy_imports=0)))
