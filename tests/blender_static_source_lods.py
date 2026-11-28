"""Genuine UE4 editor meshes plus controlled duplicated LOD headers and a batch UI check."""
import io, json, os, sys, tempfile, struct
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset, umesh

bpy.ops.wm.read_factory_settings(use_empty=True)
root=Path(os.environ['UE_ROPE_ASSET']).parent
paths=sorted(root.glob('SM_*.uasset'))
expected={'SM_Prop_Rope_01':(32,60),'SM_Chr_Attach_Straw_01':(12,20),'SM_Env_Skydome_01':(91,160),'SM_Veh_War_Balloon_01_OarLock_R':(71,142)}
assert set(p.stem for p in paths)>=set(expected)
objects=[]
for path in paths:
    if path.stem not in expected: continue
    decoded=[]
    decoder=umesh.decode_mesh_description
    def capture(payload):
        data=decoder(payload); decoded.append(data); return data
    with patch.object(umesh,'decode_mesh_description',side_effect=capture):
        result=umesh.ImportUMeshAsObject(str(path),materials=False,all_lods=True)
    assert len(result)==len(decoded)==1
    obj=result[0]; mesh=obj.data; data=decoded[0]
    assert (len(mesh.vertices),len(mesh.polygons))==expected[path.stem]
    assert mesh['UE_lod_index']==0 and mesh['UE_source_lod_count']==1
    assert json.loads(mesh['UE_missing_source_lods'])==[]
    assert mesh.has_custom_normals and len(mesh.uv_layers)==2
    corners=[c for _,cs in data['triangles'] for c in cs]
    tangent=mesh.attributes['UE_source_tangent']; sign=mesh.attributes['UE_source_binormal_sign']
    assert tangent.domain==sign.domain=='CORNER'
    for i,c in enumerate(corners):
        x,y,z=data['tangents'][c]
        assert tuple(tangent.data[i].vector)==(y,x,z)
        assert sign.data[i].value==data['signs'][c][0]
    vertices={v:i for i,v in enumerate(sorted(data['vertices']))}
    hard={tuple(sorted(vertices[v] for v in data['edges'][i])):flag for i,flag in data['hard_edges'].items()}
    assert len(hard)==len(mesh.edges)
    assert all(item.value==hard[tuple(sorted(edge.vertices))] for item,edge in zip(mesh.attributes['UE_source_hard_edge'].data,mesh.edges))
    assert all(item.value==0 for item in mesh.attributes['UE_source_material_index'].data)
    print('GENUINE_STATIC',path.stem,len(mesh.vertices),len(mesh.polygons),len(corners),sum(hard.values()))
    objects.append(obj)
assert len(objects)==4
# Controlled multi-LOD source header constructed from real Rope binary. Original bulk payload
# is unchanged and decoded twice at its original offsets. LOD1 is explicitly absent.
path=root/'SM_Prop_Rope_01.uasset'
with uasset.UAsset(str(path),False) as asset:
    export=next(e for e in asset.exports if e.export_class_type=='StaticMesh')
    export.ReadProperties(False,False); start=asset.f.Position()
    original=umesh.ReadMeshBulkData; bounds=[]
    def record(e,a,f):
        before=f.Position(); mesh=original(e,a,f); bounds.append((before,f.Position())); return mesh
    with patch.object(umesh,'ReadMeshBulkData',side_effect=record):
        primary=umesh.ImportStaticMesh(export,False,False)
    end=asset.f.Position(); b,e=bounds[0]; finish=e+16+4
    raw=path.read_bytes()
    assert struct.unpack_from('<i',raw,b-4)[0]==1
    block=raw[b-4:finish]
    appended=raw[start:b-4]+block+struct.pack('<i',0)+block+raw[finish:end]
    class NamedBytes(io.BytesIO): name='controlled_lods.uasset'
    stream=NamedBytes(raw+appended); stream.seek(len(raw))
    asset.f=uasset.ByteStream(stream)
    source=export.properties['SourceModels'].value[0]
    export.properties['SourceModels'].value=[source]*3
    lods=umesh.ImportStaticMesh(export,False,False,all_lods=True)
    assert [m['UE_lod_index'] for m in lods]==[0,2]
    assert all(m['UE_source_lod_count']==3 and json.loads(m['UE_missing_source_lods'])==[1] for m in lods)
    assert all((len(m.vertices),len(m.polygons))==(32,60) for m in lods)
    with patch.object(umesh,'ImportMeshUAsset',return_value=lods):
        linked=umesh.ImportUMeshAsObject('controlled_lods.uasset',materials=False,all_lods=True)
    assert not linked[0].hide_get() and linked[1].hide_get() and linked[1].hide_render
    stream.seek(len(raw)); primary_only=umesh.ImportStaticMesh(export,False,False)
    assert primary_only['UE_lod_index']==0 and primary_only['UE_source_lod_count']==3
    bpy.data.meshes.remove(primary_only); bpy.data.meshes.remove(primary)
print('CONTROLLED_MULTI_LOD_PASS')
# Actual file browser multi-select, one missing path between two valid assets.
import asset_entrypoints
asset_entrypoints.register()
try:
    before=len(bpy.data.objects)
    result=getattr(bpy.ops,"import").umesh(directory=str(root)+os.sep, files=[{'name':'SM_Prop_Rope_01.uasset'},{'name':'not_present.uasset'},{'name':'SM_Chr_Attach_Straw_01.uasset'}],materials=False,all_lods=True)
    assert result=={'FINISHED'} and len(bpy.data.objects)==before+2
finally: asset_entrypoints.unregister()
print('BATCH_CONTINUES_AFTER_MISSING_PASS')
# Remove controlled and duplicate objects before saving genuine outputs.
keep={o.as_pointer() for o in objects}
for obj in list(bpy.data.objects):
    if obj.as_pointer() not in keep: bpy.data.objects.remove(obj,do_unlink=True)
for mesh in list(bpy.data.meshes):
    if not mesh.users: bpy.data.meshes.remove(mesh)
# Arrange original geometry for inspection without changing mesh data.
for i,obj in enumerate(objects): obj.location.x=i*3
out=os.environ['UE_STATIC_LOD_OUTPUT']
bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
assert len(bpy.data.objects)==4
assert all(o.data.attributes.get('UE_source_tangent') and o.data.attributes.get('UE_source_hard_edge') for o in bpy.data.objects)
print('STATIC_SOURCE_LODS_PASS')
