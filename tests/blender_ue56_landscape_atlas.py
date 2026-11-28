"""Original finest-mip atlas, exact packed bytes, duplicate borders, one-click import/reopen."""
import os,sys,json,hashlib,struct,zlib
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_landscape import records
from ue5_full_scene import reconstruct
p=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);content=p.parent/'Content';level=content/'MyStuff/Maps/MainLevel.umap'
bpy.ops.wm.read_factory_settings(use_empty=True);surface={};plans,skips=records(content,level,surface_data=surface);assert len(plans)==1 and not skips
rec,grid=plans[0];atlas=surface[rec['source'],rec['actor']];meta=rec['source_atlas'];root,report=reconstruct(str(level),partial=True);terrain=report['stages']['geometry']['landscape_report'];assert terrain['actors']==1 and not terrain['skipped'],terrain
assert atlas.shape==(1024,1024,4);assert len(meta['tiles'])==64
assert all(c['material_bindings']['instances'][0]['chain'][0]['texture_parameters'][0]['value']['name']==c['texture'] for c in rec['components'])
assert all(c['material_bindings']['instances'][0]['chain'][0]['texture_parameters'][0]['name']=='Heightmap' for c in rec['components'])
assert all(c['material_bindings']['lod_indices']==[0]*6 for c in rec['components'])
# Read original PNG bytes independently of Blender pixel conversion and the PNG writer.
def png_raw(data):
    assert data[:8]==b'\x89PNG\r\n\x1a\n';i=8;chunks=[]
    while i<len(data):
        length=struct.unpack_from('>I',data,i)[0];kind=data[i+4:i+8];payload=data[i+8:i+8+length];assert zlib.crc32(kind+payload)&0xffffffff==struct.unpack_from('>I',data,i+8+length)[0];i+=12+length
        if kind==b'IHDR':assert struct.unpack('>2I5B',payload)==(1024,1024,8,6,0,0,0)
        if kind==b'IDAT':chunks.append(payload)
    a=np.frombuffer(zlib.decompress(b''.join(chunks)),dtype=np.uint8).reshape(1024,4097);assert not a[:,0].any();return a[:,1:].reshape(1024,1024,4)

def verify():
    ob=next(o for o in bpy.data.objects if o.get('UE_landscape_record'));mesh=ob.data;assert len(mesh.vertices)==1009**2 and len(mesh.polygons)==1008**2
    im=bpy.data.images[ob['UE_landscape_source_atlas']];assert im.packed_file and im.alpha_mode=='CHANNEL_PACKED' and im.colorspace_settings.name=='Non-Color';packed=bytes(im.packed_file.data);raw=png_raw(packed);np.testing.assert_array_equal(raw,atlas)
    decoded=np.empty(raw.size,dtype=np.float32);im.pixels.foreach_get(decoded);pixel_error=float(np.max(abs(decoded.reshape(raw.shape)-raw[::-1].astype(np.float32)/255)));assert pixel_error<1e-6,pixel_error
    for tile in meta['tiles']:
        x,y=tile['atlas_offset'];assert hashlib.sha256(raw[y:y+128,x:x+128].tobytes()).hexdigest()==tile['rgba_sha256']
    uv=np.empty(len(mesh.loops)*2,dtype=np.float32);mesh.uv_layers[ob['UE_landscape_source_uv']].data.foreach_get('uv',uv);uv=uv.reshape(1008,1008,4,2)
    comp=np.empty(len(mesh.polygons),dtype=np.int32);mesh.attributes['UE_landscape_component_index'].data.foreach_get('value',comp);comp=comp.reshape(1008,1008)
    # Independent subsection-by-subsection verification of all corners and original heights.
    error=0.;corners=0;aux_edges=0
    for ty in range(8):
        for tx in range(8):
            for sy in range(2):
                for sx in range(2):
                    y=ty*126+sy*63;x=tx*126+sx*63;v=ty*128+sy*64;u=tx*128+sx*64
                    actual=uv[y:y+63,x:x+63];yy,xx=np.indices((63,63));expected=np.stack([np.stack(((u+xx+dx+.5)/1024,1-(v+yy+dy+.5)/1024),axis=-1) for dx,dy in [(0,0),(0,1),(1,1),(1,0)]],axis=2)
                    error=max(error,float(np.max(abs(actual-expected))));assert np.all(comp[y:y+63,x:x+63]==ty*8+tx)
                    a=raw[v:v+64,u:u+64];heights=a[:,:,0].astype(np.int32)*256+a[:,:,1].astype(np.int32)-32768;np.testing.assert_array_equal(heights,grid[y:y+64,x:x+64]);corners+=63*63*4
            a=raw[ty*128:(ty+1)*128,tx*128:(tx+1)*128];aux_edges+=int(np.count_nonzero(np.any(a[:,63,2:]!=a[:,64,2:],axis=-1)))+int(np.count_nonzero(np.any(a[63,:,2:]!=a[64,:,2:],axis=-1)))
    assert error==0 and aux_edges>0 and ob['UE_unresolved_material'];return dict(corners=corners,max_uv_error=error,auxiliary_seam_differences=aux_edges,atlas_sha256=hashlib.sha256(raw.tobytes()).hexdigest(),packed_png_sha256=hashlib.sha256(packed).hexdigest(),component_bindings=len(rec['components']),max_decoded_rgba_error=pixel_error,weight_layers_status=rec['weight_layers_status'])
a=verify();print('ATLAS_PRE',a,flush=True);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));b=verify();assert a==b;# Controlled malformed atlas: retain the valid base geometry and record why enrichment failed.
from unittest.mock import patch
from ue5_editor_landscape import source_atlas,extend_landscapes
from project_session import new_ids
col=bpy.data.collections.new('Controlled fallback');bpy.context.scene.collection.children.link(col)
_,small_meta=source_atlas({(0,0):np.zeros((4,4,4),dtype=np.uint8)},2,1,2)
small_record=dict(actor='Controlled',source='fixture',fields=dict(RelativeLocation=(0,0,0),RelativeRotation=(0,0,0),RelativeScale3D=(1,1,1)),grid_origin=(0,0),material_package='',components=[{}],source_atlas=small_meta,source_atlas_status='validated')
def fake_records(*args,surface_data=None,**kwargs):
    surface_data['fixture','Controlled']=np.ones((4,4,4),dtype=np.uint8)
    return [(small_record,np.zeros((3,3),dtype=np.int32))],[]
ids=set(new_ids())
with patch('ue5_editor_landscape.records',fake_records):
    fallback=extend_landscapes(content,level,col)
assert fallback['actors']==1 and fallback['vertices']==9 and fallback['records'][0]['source_atlas_status']=='build_failed' and fallback['records'][0]['source_atlas_image'] is None
assert len(set(new_ids())-ids)==2 and len(col.objects)==1
out.with_suffix('.json').write_text(json.dumps(dict(before=a,after=b,reopen=True,controlled_corrupt_atlas_fallback=True,scope='Original source RGBA and derived atlas texel-center UV; no terrain material or normal parity',scene_counts=report['counts']),indent=2));print('ATLAS_ACCEPTANCE_PASS',b,flush=True)
