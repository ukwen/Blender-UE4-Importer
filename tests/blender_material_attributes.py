"""Controlled serialized attribute input, actual graph import and Cycles field evaluation."""
import io, struct, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset, umat, material_attributes as ma, material_instance as mi


def props(**items):
    p=uasset.Properties()
    for k,v in items.items(): p[k]=NS(value=v,type='StructProperty',struct_type='ExpressionInput')
    return p


def exp(name,kind,**items):
    return NS(object_name=name,export_class_type='MaterialExpression'+kind,properties=props(**items))


def link(e,index=0): return NS(node=e,node_index=1,node_output_i=index,mask=0,mask_rgba=(0,0,0,0))


# Native tagged 36-byte MaterialAttributesInput (FName layout).
a=exp('LayerA','MakeMaterialAttributes')
names=['None','MaterialAttributes','StructProperty','MaterialAttributesInput']
fn=lambda n:struct.pack('<ii',names.index(n),0)
raw=fn('MaterialAttributes')+fn('StructProperty')+struct.pack('<ii',36,0)+fn('MaterialAttributesInput')+bytes(16)+b'\0'+struct.pack('<9i',1,0,0,0,0,0,0,0,0)+fn('None')
f=uasset.ByteStream(io.BytesIO(raw))
asset=NS(f=f,names=names,summary=NS(version_ue4=522),GetExport=lambda i:a,TryReadPropertyGuid=lambda:f.ReadGuid() if f.ReadBool() else None)
p=uasset.Properties().Read(asset)
assert f.Position()==len(raw) and p['MaterialAttributes'].value.node is a
print('ATTRIBUTE_INPUT_BINARY_PASS')

bpy.ops.wm.read_factory_settings(use_empty=True)
colorA=exp('ColorA','Constant3Vector',Constant=NS(ToTupleRGB=lambda:(.2,.4,.6)))
colorB=exp('ColorB','Constant3Vector',Constant=NS(ToTupleRGB=lambda:(.6,.2,.4)))
rA=exp('RoughA','Constant',R=.2); rB=exp('RoughB','Constant',R=.8)
alpha=exp('Alpha','ScalarParameter',ParameterName='LayerWeight',DefaultValue=.25)
mask=exp('Mask','Constant',R=.3)
a.properties=props(BaseColor=link(colorA),Roughness=link(rA),OpacityMask=link(mask))
b=exp('LayerB','MakeMaterialAttributes',BaseColor=link(colorB),Roughness=link(rB))
blend=exp('Blend','BlendMaterialAttributes',A=link(a),B=link(b),Alpha=link(alpha))
br=exp('Break','BreakMaterialAttributes',MaterialAttributes=link(blend))
select=exp('SelectB','BlendMaterialAttributes',A=link(a),B=link(b),Alpha=link(alpha),PixelAttributeBlendType='UseB')
repack=exp('Repack','MakeMaterialAttributes',BaseColor=link(br,0),Roughness=link(br,3),OpacityMask=link(br,6))
expressions=[repack,br,blend,select,a,b,colorA,colorB,rA,rB,alpha,mask]
root=NS(object_name='AttributeSurface',export_class_type='Material',properties=props(bUseMaterialAttributes=True,MaterialAttributes=link(repack),Expressions=[NS(value=e) for e in expressions]))
class Fixture:
    def __enter__(self): return NS(exports=[root],f=NS(byte_stream=NS(name='controlled_attributes.uasset')))
    def __exit__(self,*args): pass
with patch.object(umat,'UAsset',return_value=Fixture()): mat,g=umat.ImportNodeGraph('controlled_attributes.uasset')
mat.use_fake_user=True; tree=mat.node_tree; shader=tree.nodes['Principled BSDF']
assert not tree.get('Error'),[(n.name,n.get('UE_attribute_error')) for n in tree.nodes]
assert mat['UE_material_status']=='graph_imported_unverified'
assert shader.inputs['Base Color'].links[0].from_node.name=='Repack'
assert shader.inputs['Roughness'].links[0].from_socket.name=='Roughness'
assert not shader.inputs['Alpha'].is_linked
assert shader.inputs['Normal'].links[0].from_node.type=='NORMAL_MAP'
assert shader.inputs['Emission Strength'].default_value==1
print('ATTRIBUTE_ROOT_IMPORT_PASS')
# Render field outputs (not a reference Unreal shader render).
bpy.ops.mesh.primitive_plane_add(size=2); bpy.context.object.data.materials.append(mat)
cam=bpy.data.objects.new('Camera',bpy.data.cameras.new('Camera')); bpy.context.collection.objects.link(cam)
cam.location=(0,0,3); cam.data.type='ORTHO'; cam.data.ortho_scale=1
scene=bpy.context.scene; scene.camera=cam; scene.render.engine='CYCLES'; scene.cycles.device='CPU'; scene.cycles.samples=4; scene.cycles.use_denoising=False
scene.render.resolution_x=4; scene.render.resolution_y=4; scene.render.resolution_percentage=100; scene.render.image_settings.file_format='OPEN_EXR'
em=tree.nodes.new('ShaderNodeEmission'); tree.links.new(em.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
with tempfile.TemporaryDirectory() as tmp:
    def render(node,field,expected):
        tree.links.new(tree.nodes[node].outputs[field],em.inputs['Color'])
        scene.render.filepath=str(Path(tmp)/'result.exr'); bpy.ops.render.render(write_still=True)
        im=bpy.data.images.load(scene.render.filepath); px=tuple(im.pixels[:4]); bpy.data.images.remove(im)
        err=max(abs(a-b) for a,b in zip(px,expected+(1.,))); print('ATTR_RENDER',node,field,err)
        assert err<.00001,(px,expected)
    render('Repack','BaseColor',(.3,.35,.55)); render('Repack','Roughness',(.35,)*3)
    render('Break','OpacityMask',(.475,)*3); render('Break','Opacity',(1.,)*3)
    render('SelectB','BaseColor',(.6,.2,.4))
    override=NS(value=props(ParameterName='layerweight',ParameterValue=.75))
    applied,issues=mi.apply_overrides(mat,g,props(ScalarParameterValues=[override]),None,None)
    assert not issues and applied[0]['targets']==1
    render('Repack','BaseColor',(.5,.25,.45)); render('Repack','Roughness',(.65,)*3)
    tree.links.new(shader.outputs[0],tree.nodes['Material Output'].inputs['Surface'])
    path=str(Path(tmp)/'attributes.blend'); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    mat=bpy.data.materials['AttributeSurface']; tree=mat.node_tree
    assert tree.nodes['Repack'].outputs['BaseColor'].is_linked and tree.nodes['Alpha'].outputs[0].default_value==.75
print('ATTRIBUTES_REOPEN_PASS')
# Unsupported connected field and bundle-to-scalar misuse must be marked.
mat=bpy.data.materials.new('UnsupportedAttributes'); mat.use_nodes=True; g=umat.GraphData(); tree=mat.node_tree
unsupported=exp('Unsupported','MakeMaterialAttributes',WorldPositionOffset=link(colorA))
node=umat.CreateNode(unsupported,tree,g.nodes_data,g).node
assert tree.get('Error') and 'WorldPositionOffset' in node['UE_attribute_error']
assert not umat.TryLinkSocket(tree,g.nodes_data,NS(node=tree.nodes['Principled BSDF'],input_remap=None),props(Roughness=link(unsupported))['Roughness'],'Roughness','Roughness')
print('ATTRIBUTE_UNSUPPORTED_PASS')
