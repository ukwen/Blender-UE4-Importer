"""Synthetic FRawMesh payload, exercising the actual legacy binary decoder."""
import struct
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace
import bpy
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uasset, umesh, umat


def array(fmt, values):
    return struct.pack('<i', len(values)) + b''.join(struct.pack('<'+fmt, *v) for v in values)


def fixture(path):
    payload = struct.pack('<ii', 0, 0)
    payload += array('i', [(0,)]) + array('I', [(1,)])
    payload += array('fff', [(0,0,0),(100,0,0),(0,100,0)])
    payload += array('i', [(0,),(1,),(2,)])
    payload += array('fff', []) * 2
    payload += array('fff', [(0,0,1)]*3)
    payload += array('ff', [(0,0),(1,0),(0,1)])
    payload += array('ff', [])
    payload += array('ff', [(0.25,0.25),(0.75,0.25),(0.25,0.75)])
    payload += array('ff', []) * 5
    payload += array('BBBB', [(0,0,255,255)]*3)
    offset = 64
    header = struct.pack('<IIIq', 0x10001, len(payload), len(payload), offset)
    path.write_bytes(header + bytes(offset-len(header)) + payload)

with tempfile.TemporaryDirectory() as temp:
    path = Path(temp) / 'triangle.raw'
    fixture(path)
    with path.open('rb') as file:
        stream = uasset.ByteStream(file)
        asset = SimpleNamespace(f=stream, summary=SimpleNamespace(version_ue4=522, compression_flags=0, bulk_data_offset=0, custom_versions={}))
        exp = SimpleNamespace(object_name='SyntheticTriangle', asset=asset)
        mesh = umesh.ReadMeshBulkData(exp, asset, stream)
        assert len(mesh.vertices)==3 and len(mesh.polygons)==1
        assert {tuple(round(x,5) for x in v.co) for v in mesh.vertices} == {(0,0,0),(0,1,0),(1,0,0)}
        assert [uv.name for uv in mesh.uv_layers]==['UV0','UV2']
        expected={(0.25,0.75),(0.75,0.75),(0.25,0.25)}
        assert {tuple(round(x,5) for x in uv.uv) for uv in mesh.uv_layers['UV2'].data}==expected
        assert mesh.has_custom_normals
        assert mesh.color_attributes.get('Color') is not None
        assert stream.Position()==20
        bpy.context.collection.objects.link(bpy.data.objects.new('SyntheticTriangle',mesh))
    print('PASS native raw mesh payload: 3 vertices, 1 triangle, 1m scale, sparse UV channels, color, custom normals')
    umat.TryAppendNodeGroups()
    groups = len(bpy.data.node_groups)
    assert groups > 0 and bpy.data.node_groups.get('AdditiveSurface')
    umat.TryAppendNodeGroups()
    assert len(bpy.data.node_groups) == groups
    print('PASS bundled shader library idempotence', groups)
    out=Path(temp)/'result.blend'
    bpy.ops.wm.save_as_mainfile(filepath=str(out))
    bpy.ops.wm.open_mainfile(filepath=str(out))
    assert bpy.data.objects['SyntheticTriangle'].data.uv_layers.get('UV2')
    print('PASS saved and reopened reconstructed synthetic mesh')
