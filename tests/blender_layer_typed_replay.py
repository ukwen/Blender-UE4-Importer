"""Explicit detached layer snapshot replacement and rollback, CPU render."""
import io, json, struct, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset, umat, material_layers as ml, material_instance as mi
from material_stage import incomplete_graph


def props(**items):
    p=uasset.Properties()
    for k,v in items.items(): p[k]=NS(value=v,type='StructProperty',struct_type='ExpressionInput')
    return p


def exp(name,kind,**items):
    return NS(object_name=name,export_class_type='MaterialExpression'+kind,properties=props(**items))


def link(e): return NS(node=e,node_index=1,node_output_i=0,mask=0,mask_rgba=(0,0,0,0))


def root(name,kind,expressions,**items):
    return NS(object_name=name,export_class_type=kind,properties=props(**items,**{('Expressions' if kind=='Material' else 'FunctionExpressions'):[NS(value=e) for e in expressions]}))


class Fixture:
    def __init__(self,export): self.export=export
    def __enter__(self): return NS(exports=[self.export],f=NS(byte_stream=NS(name='controlled.uasset')))
    def __exit__(self,*args): pass


from uuid import UUID
from native_texture import png_bytes
bpy.ops.wm.read_factory_settings(use_empty=True)
ids=[UUID(int=i) for i in (1,2,3)]
def entries(values): return [NS(value=v) for v in values]
def layers(states,guids):
    return props(Layers=entries(['layer']*3),Blends=entries([None,None]),LayerStates=entries(states),LayerGuids=entries(guids),LayerLinkStates=entries(['UnlinkedFromParent']*3))
def snapshot(states,guids):
    return props(MaterialLayersParameters=entries([props(ParameterInfo=props(Name='Layers',Association='GlobalParameter',Index=-1),bOverride=True,Value=layers(states,guids))]))
def ref(name,image):
    r=uasset.Import.__new__(uasset.Import); r.object_name='/Game/'+name; r.asset=NS(extract_dir=''); r.image=image
    return r
with tempfile.TemporaryDirectory() as tmp:
    def image(name,rgba):
        path=Path(tmp)/(name+'.png'); path.write_bytes(png_bytes(2,2,bytes(rgba)*4))
        im=bpy.data.images.load(str(path)); im.colorspace_settings.name='Non-Color'; im.pack(); return im
    default=ref('Default',image('Default',(255,0,0,255)))
    override=ref('Override',image('Override',(0,255,0,255)))
    override.image['nearest']=True; override.image['UE_address_x']=override.image['UE_address_y']='TA_Clamp'
    t=exp('Tex','TextureSampleParameter2D',ParameterName='Shared',Texture=default); t.asset=default.asset
    v=exp('Tint','VectorParameter',ParameterName='Shared',DefaultValue=uasset.FLinearColor(.1,.2,.3,.4))
    a=exp('A','Constant',R=.8); b=exp('B','Constant',R=.2)
    switch=exp('Switch','StaticSwitchParameter',ParameterName='Shared',A=link(a),B=link(b),DefaultValue=False)
    scalar=exp('Scalar','ScalarParameter',ParameterName='Shared',DefaultValue=.1)
    make=exp('Make','MakeMaterialAttributes',BaseColor=link(t),EmissiveColor=link(v),Roughness=link(switch),Metallic=link(scalar))
    layer=root('Layer','MaterialFunctionMaterialLayer',[make,t,v,a,b,switch,scalar,exp('Out','FunctionOutput',Id='out',A=link(make))])
    stack=exp('Stack','MaterialAttributeLayers',DefaultLayers=layers([True,True,False],ids),ParameterName='Layers')
    matroot=root('TypedReplay','Material',[stack],bUseMaterialAttributes=True,MaterialAttributes=link(stack))
    def load(ref,*args):
        if ref!='layer': raise ValueError('Missing test function')
        with patch.object(umat,'UAsset',return_value=Fixture(layer)),patch.object(umat,'TryGetExtractedImport',side_effect=lambda r,_:r.image):
            return umat.ImportNodeGraph(ref+'.uasset')
    with patch.object(umat,'UAsset',return_value=Fixture(matroot)),patch.object(umat,'ImportMaterialFunction',side_effect=load):
        mat,g=umat.ImportNodeGraph('controlled_typed_layers.uasset')
    assert not incomplete_graph(mat.node_tree)
    assert not mi.apply_overrides(mat,g,snapshot([True,True,False],ids),None,None)[1]
    def entry(index,value,**extra):
        return NS(value=props(ParameterInfo=props(Name='SHARED',Association='LayerParameter',Index=index),ParameterValue=value,**extra))
    records=props(ScalarParameterValues=[entry(1,.6)],VectorParameterValues=[entry(1,uasset.FLinearColor(.3,.5,.7,.9))],TextureParameterValues=[entry(1,override)],StaticSwitchParameters=[entry(1,True,bOverride=True,Value=True)])
    applied,issues=mi.apply_overrides(mat,g,records,lambda r,_:r.image,umat.SetNodeTexture)
    assert not issues and len(applied)==4 and len(g.scoped_records)==4
    def check(index):
        targets={mi.CLASSES[t.classname]:t.node for t in g.scoped_param_nodes['LayerParameter',index,'shared']}
        assert abs(targets['scalar'].outputs[0].default_value-.6)<1e-6
        assert max(abs(x-y) for x,y in zip(targets['vector'].inputs['RGB'].default_value,(.3,.5,.7,.9)))<1e-6
        assert abs(targets['vector'].inputs['A'].default_value-.9)<1e-6
        assert targets['switch'].inputs[0].default_value==1
        tex=targets['texture']; assert tex.image==override.image and tex.image.packed_file
        assert tex.extension=='EXTEND' and tex.interpolation=='Closest' and tex['UE_texture_package']=='/Game/Override'
        other={mi.CLASSES[t.classname]:t.node for t in g.scoped_param_nodes['LayerParameter',0,'shared']}
        assert other['texture'].image==default.image and other['switch'].inputs[0].default_value==0
    check(1)
    mat.use_fake_user=True; tree=mat.node_tree
    bpy.ops.mesh.primitive_plane_add(size=2); bpy.context.object.data.materials.append(mat)
    cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera')); bpy.context.collection.objects.link(cam)
    cam.location=(0,0,3); cam.data.type='ORTHO'; cam.data.ortho_scale=1
    scene=bpy.context.scene; scene.camera=cam; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=4; scene.cycles.use_denoising=False
    scene.render.resolution_x=4; scene.render.resolution_y=4; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
    em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
    def render(field,expected):
        tree.links.new(tree.nodes['Stack'].outputs[field],em.inputs['Color'])
        scene.render.filepath=str(Path(tmp)/'typed.exr'); bpy.ops.render.render(write_still=True)
        im=bpy.data.images.load(scene.render.filepath); px=tuple(im.pixels[:4]); bpy.data.images.remove(im)
        error=max(abs(a-b) for a,b in zip(px,expected+(1.,))); print('TYPED_REPLAY_RENDER',field,error,px); assert error<.00001
    for order,states in ((ids,[True,True,False]),([ids[0],ids[2],ids[1]],[True,False,True]),(ids,[True,True,False])):
        assert not mi.apply_overrides(mat,g,snapshot(states,order),None,None)[1]
        check(order.index(ids[1]))
        for field,expected in [('BaseColor',(0.,1.,0.)),('EmissiveColor',(.3,.5,.7)),('Roughness',(.8,)*3),('Metallic',(.6,)*3)]: render(field,expected)
    current=tree.nodes['Stack'].node_tree; before={x.as_pointer() for x in bpy.data.node_groups}
    override.image.unpack(method='REMOVE')
    try: ml.replace_snapshot(mat,g,(['layer']*3,[None,None],[True,False,True]),[ids[0],ids[2],ids[1]])
    except ValueError: pass
    else: raise AssertionError('Unpacked inherited image accepted')
    assert tree.nodes['Stack'].node_tree==current and {x.as_pointer() for x in bpy.data.node_groups}==before
    override.image.pack(); check(1)
    out=str(Path(tmp)/'typed.blend'); bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
    assert bpy.data.images['Override.png'].packed_file
    assert json.loads(bpy.data.materials['TypedReplay'].node_tree.nodes['Stack']['UE_layer_guids'])==[str(i) for i in ids]
print('TYPED_REPLAY_PASS')
