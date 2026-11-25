"""Default layer stack routing, scoped overrides, and controlled CPU render."""
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


# Tagged DefaultLayers array reader with object indices, bools, null blend, disabled layer.
names=['None','DefaultLayers','StructProperty','MaterialLayersFunctions','Layers','Blends','LayerStates','ArrayProperty','ObjectProperty','BoolProperty']
fn=lambda n:struct.pack('<ii',names.index(n),0)
def array(key,kind,payload,count):
    return fn(key)+fn('ArrayProperty')+struct.pack('<ii',4+len(payload),0)+fn(kind)+b'\0'+struct.pack('<i',count)+payload
refs={-1:'layer',-2:'disabled',-3:'blend',0:None}
inner=array('Layers','ObjectProperty',struct.pack('<3i',-1,-2,-1),3)+array('Blends','ObjectProperty',struct.pack('<2i',0,-3),2)+array('LayerStates','BoolProperty',bytes([1,0,1]),3)+fn('None')
raw=fn('DefaultLayers')+fn('StructProperty')+struct.pack('<ii',len(inner),0)+fn('MaterialLayersFunctions')+bytes(16)+b'\0'+inner+fn('None')
f=uasset.ByteStream(io.BytesIO(raw)); asset=NS(f=f,names=names,summary=NS(version_ue4=522),DecodePackageIndex=refs.__getitem__,TryReadPropertyGuid=lambda:f.ReadGuid() if f.ReadBool() else None)
p=uasset.Properties().Read(asset); assert f.Position()==len(raw)
assert ml.stack_records(p)==(['layer','disabled','layer'],[None,'blend'],[True,False,True])
print('TAGGED_LAYER_ARRAYS_PASS')

bpy.ops.wm.read_factory_settings(use_empty=True)
# Same function appears twice, with independent parameter instances.
r=exp('Value','ScalarParameter',ParameterName='Shared',DefaultValue=.2)
make=exp('Make','MakeMaterialAttributes',Roughness=link(r))
layer=root('Layer','MaterialFunctionMaterialLayer',[make,r,exp('Out','FunctionOutput',Id='out',A=link(make))])
a=exp('Bottom','FunctionInput',InputType='FunctionInput_MaterialAttributes',InputName='Bottom',Id='a',SortPriority=0)
b=exp('Top','FunctionInput',InputType='FunctionInput_MaterialAttributes',InputName='Top',Id='b',SortPriority=1)
w=exp('Weight','ScalarParameter',ParameterName='Shared',DefaultValue=.25)
blend=exp('Blend','BlendMaterialAttributes',A=link(a),B=link(b),Alpha=link(w))
blendfn=root('Blend','MaterialFunctionMaterialLayerBlend',[b,a,w,blend,exp('Out','FunctionOutput',Id='out',A=link(blend))])
stack=exp('Stack','MaterialAttributeLayers'); stack.properties=p
G=exp('Global','ScalarParameter',ParameterName='Shared',DefaultValue=.9)
matroot=root('StackMaterial','Material',[stack,G],bUseMaterialAttributes=True,MaterialAttributes=link(stack))
loaded=[]
def load(ref,*args):
    loaded.append(ref)
    with patch.object(umat,'UAsset',return_value=Fixture({'layer':layer,'blend':blendfn}[ref])): return umat.ImportNodeGraph(ref+'.uasset')
with patch.object(umat,'UAsset',return_value=Fixture(matroot)),patch.object(umat,'ImportMaterialFunction',side_effect=load):
    mat,g=umat.ImportNodeGraph('controlled_layers.uasset')
assert loaded==['layer','layer','blend']
assert not incomplete_graph(mat.node_tree),[(n.name,n.get('UE_attribute_error')) for n in mat.node_tree.nodes]
assert set(g.scoped_param_nodes)=={('LayerParameter',0,'shared'),('LayerParameter',2,'shared'),('BlendParameter',1,'shared')}
assert len(g.param_nodes['Shared'])==1
assert g.scoped_param_nodes['LayerParameter',0,'shared'][0].node!=g.scoped_param_nodes['LayerParameter',2,'shared'][0].node

def record(scope,index,value):
    return NS(value=props(ParameterInfo=props(Name='SHARED',Association=scope,Index=index),ParameterValue=value))

p1=props(ScalarParameterValues=[record(0,2,.8),record(1,1,.5),record(2,-1,.1)])
assert not mi.apply_overrides(mat,g,p1,None,None)[1]
assert abs(g.param_nodes['Shared'][0].node.outputs[0].default_value-.1)<1e-6
assert abs(g.scoped_param_nodes['LayerParameter',0,'shared'][0].node.outputs[0].default_value-.2)<1e-6
assert abs(g.scoped_param_nodes['LayerParameter',2,'shared'][0].node.outputs[0].default_value-.8)<1e-6
mat.use_fake_user=True; tree=mat.node_tree
bpy.ops.mesh.primitive_plane_add(size=2); bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera')); bpy.context.collection.objects.link(cam)
cam.location=(0,0,3); cam.data.type='ORTHO'; cam.data.ortho_scale=1
scene=bpy.context.scene; scene.camera=cam; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=4; scene.cycles.use_denoising=False
scene.render.resolution_x=4; scene.render.resolution_y=4; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface']); tree.links.new(tree.nodes['Stack'].outputs['Roughness'],em.inputs['Color'])
with tempfile.TemporaryDirectory() as tmp:
    def render(expected):
        scene.render.filepath=str(Path(tmp)/'render.exr'); bpy.ops.render.render(write_still=True)
        im=bpy.data.images.load(scene.render.filepath); px=tuple(im.pixels[:4]); bpy.data.images.remove(im)
        err=max(abs(a-b) for a,b in zip(px,(expected,expected,expected,1.))); print('LAYER_RENDER',err,px); assert err<.00001
    render(.5)
    assert not mi.apply_overrides(mat,g,props(ScalarParameterValues=[record('LayerParameter',0,.4)]),None,None)[1]
    render(.6)
    # Disabled layer must not redirect to an active layer or a global parameter.
    assert mi.apply_overrides(mat,g,props(ScalarParameterValues=[record('LayerParameter',1,.99)]),None,None)[1]
    # Topology overrides are unsupported, so block index-specific overrides and future descendants.
    assert mi.apply_overrides(mat,g,props(MaterialLayersParameters=[1],ScalarParameterValues=[record('LayerParameter',2,.99)]),None,None)[1]
    assert mi.apply_overrides(mat,g,props(ScalarParameterValues=[record('LayerParameter',2,.99)]),None,None)[1]
    render(.6)
    out=str(Path(tmp)/'layers.blend'); bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
    assert json.loads(bpy.data.materials['StackMaterial'].node_tree.nodes['Stack']['UE_layer_states'])==[True,False,True]
print('MATERIAL_LAYER_SCOPE_PASS')
