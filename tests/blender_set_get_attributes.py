"""Controlled GUID-array parsing and editable Set/Get material attributes."""
import io, struct, sys, tempfile
from pathlib import Path
from types import SimpleNamespace as NS
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset, umat, material_attributes as ma


def props(**items):
    p=uasset.Properties()
    for k,v in items.items(): p[k]=NS(value=v,type='StructProperty',struct_type='ExpressionInput')
    return p


def exp(name,kind,**items):
    return NS(object_name=name,export_class_type='MaterialExpression'+kind,properties=props(**items))


def link(e,index=0): return NS(node=e,node_index=1,node_output_i=index,mask=0,mask_rgba=(0,0,0,0))


def record(e,index=0): return NS(value=link(e,index),type='StructProperty',struct_type='ExpressionInput')


# Actual FGuid bytes, not UUID textual ordering. Deliberately noncanonical field order.
names=['None','AttributeSetTypes','AttributeGetTypes','Inputs','ArrayProperty','StructProperty','Guid','ExpressionInput']
fn=lambda n:struct.pack('<ii',names.index(n),0)
def array(key,kind,records):
    payload=b''.join(records)
    inner=struct.pack('<i',len(records))+fn(key)+fn('StructProperty')+struct.pack('<q',len(payload))+fn(kind)+bytes(16)+b'\0'+payload
    return fn(key)+fn('ArrayProperty')+struct.pack('<ii',len(inner),0)+fn('StructProperty')+b'\0'+inner

def guid(key):
    ident=next(g for g,k in ma.GUID_FIELDS.items() if k==key)
    return struct.pack('<4I',*(int(ident[i:i+8],16) for i in range(0,32,8)))

base=exp('Base','MakeMaterialAttributes')
rough=exp('NewRough','Constant',R=.7)
metal=exp('NewMetal','Constant',R=.8)
exports=[base,rough,metal]
raw=array('AttributeSetTypes','Guid',[guid('Roughness'),guid('Metallic')])+array('Inputs','ExpressionInput',[struct.pack('<9i',i,0,0,0,0,0,0,0,0) for i in (1,2,3)])+fn('None')
def parse(raw):
    f=uasset.ByteStream(io.BytesIO(raw))
    asset=NS(f=f,names=names,summary=NS(version_ue4=522),GetExport=lambda i:exports[i-1],TryReadPropertyGuid=lambda:f.ReadGuid() if f.ReadBool() else None)
    p=uasset.Properties().Read(asset)
    assert f.Position()==len(raw)
    return p
p=parse(raw)
assert ma.selected_fields(p,'AttributeSetTypes')==['Roughness','Metallic']
assert len(p['Inputs'].value)==3 and p['Inputs'].value[1].value.node is rough
assert ma.selected_fields(parse(array('AttributeGetTypes','Guid',[])+fn('None')),'AttributeGetTypes')==[]
print('GUID_AND_EXPRESSION_ARRAY_PASS')

bpy.ops.wm.read_factory_settings(use_empty=True)
umat.TryAppendNodeGroups()
mat=bpy.data.materials.new('SetGet'); mat.use_nodes=True; mat.use_fake_user=True; tree=mat.node_tree; g=umat.GraphData()
color=exp('OriginalColor','Constant3Vector',Constant=NS(ToTupleRGB=lambda:(.2,.4,.6)))
opacity=exp('OriginalOpacity','Constant',R=.45)
base.properties=props(BaseColor=link(color),Opacity=link(opacity))
setting=exp('Set','SetMaterialAttributes'); setting.properties=p
getting=exp('Get','GetMaterialAttributes'); getting.properties=parse(array('AttributeGetTypes','Guid',[guid('Metallic'),guid('BaseColor'),guid('Opacity'),guid('Roughness')])+fn('None'))
getting.properties.update(props(MaterialAttributes=link(setting)))
# output index 0 is bundle passthrough; requested fields follow in GUID order.
breaker=exp('Break','BreakMaterialAttributes',MaterialAttributes=link(getting))
repack=exp('Repack','MakeMaterialAttributes',Metallic=link(getting,1),BaseColor=link(getting,2),Opacity=link(getting,3),Roughness=link(getting,4))
for e in (repack,breaker,getting,setting,base,color,opacity,rough,metal): umat.CreateNode(e,tree,g.nodes_data,g)
for d in g.nodes_data.values(): umat.LinkSockets(tree,g.nodes_data,d)
assert not tree.get('Error'),[(n.name,n.get('UE_attribute_error')) for n in tree.nodes]
assert [s.name for s in g.nodes_data['Get'].link_indirect[1:]]==['Metallic','BaseColor','Opacity','Roughness']
assert tree.nodes['Break'].inputs['BaseColor'].links[0].from_node.name=='Get'
assert tree.nodes['Repack'].inputs['Roughness'].links[0].from_socket.name=='Roughness'
# evaluate actual linked fields using CPU Cycles, including untouched original bundle.
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
        err=max(abs(a-b) for a,b in zip(px,expected+(1.,))); print('SET_GET_RENDER',node,field,err)
        assert err<.00001,(px,expected)
    render('Repack','Metallic',(.8,)*3); render('Repack','Roughness',(.7,)*3); render('Repack','BaseColor',(.2,.4,.6)); render('Repack','Opacity',(.45,)*3)
    render('Break','Roughness',(.7,)*3); render('Base','Roughness',(.5,)*3)
    path=str(Path(tmp)/'setget.blend'); bpy.ops.wm.save_as_mainfile(filepath=path); bpy.ops.wm.open_mainfile(filepath=path)
    assert bpy.data.materials['SetGet'].node_tree.nodes['Repack'].inputs['Metallic'].links[0].from_socket.name=='Metallic'
# Malformed and unknown IDs cannot silently shift output order.
for ids in ([bytes(16)],[guid('Metallic'),guid('Metallic')]):
    invalid=exp('Invalid','GetMaterialAttributes'); invalid.properties=parse(array('AttributeGetTypes','Guid',ids)+fn('None'))
    mat=bpy.data.materials.new('Invalid'); mat.use_nodes=True; g=umat.GraphData()
    n=umat.CreateNode(invalid,mat.node_tree,g.nodes_data,g).node
    assert mat.node_tree.get('Error') and n.get('UE_attribute_error')
print('SET_GET_ATTRIBUTES_PASS')
