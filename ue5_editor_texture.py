"""UE5 editor Texture2D: local BGRA8 single-mip UEDELTA source, 32-row stripes.
Profile verified on original ShooterSam assets. Validate serialized color extrema.
"""
import struct
import hashlib
from pathlib import Path
from skeleton_native import Reader
from ue5_blueprint import read_tables, require
from ue5_editor_tags import export_tags,read_tags,read_tag_stream
from ue5_editor_payload import read_trailer,extract_payload
from native_texture import MAX_BYTES,png_bytes


def decode_delta(data,w,h):
    import numpy as np
    require(1<=w<=8192 and 1<=h<=8192 and w*h*4<=MAX_BYTES and len(data)==w*h*4,'Invalid delta texture extent')
    src=np.frombuffer(data,dtype=np.uint8).reshape(h,w,4); out=np.empty_like(src)
    for y in range(0,h,32):
        np.cumsum(src[y:y+32],axis=0,dtype=np.uint8,out=out[y:y+32])
    return out


def read_texture(path,decoder=None):
    import numpy as np
    m,b,im,ex,ref,pkg=read_tables(path); names=m['names']
    require(m['ue5'] in (1013,1017),'Unsupported UE5 editor texture profile')
    roots=[e for e in ex if not e['outer'] and e['kind']=='Texture2D'];require(len(roots)==1,'Expected one Texture2D root');e=roots[0]
    tags=export_tags(b,e,names); src=tags['Source'];require(src['type']==['StructProperty','TextureSource','/Script/Engine'],'Invalid TextureSource')
    s=read_tags(src['data'],names)
    def integer(k):
        t=s[k];require(t['type']==['IntProperty'] and len(t['data'])==4,'Invalid source integer');return struct.unpack('<i',t['data'])[0]
    def enum(t,kind):
        require(t['type']==['ByteProperty',kind,'/Script/Engine'] and len(t['data'])==8,'Invalid texture enum');return Reader(t['data']).name(names)
    def boolean(k,default):
        t=tags.get(k)
        if t is None:return default
        require(t['type']==['BoolProperty'] and not t['data'] and t['flags'] in (0,16),'Unsupported texture Boolean');return bool(t['flags']&16)
    w,h,n,sl=map(integer,('SizeX','SizeY','NumMips','NumSlices'))
    require(n==sl==1 and 1<=w<=8192 and 1<=h<=8192 and w*h*4<=MAX_BYTES,'Unsupported editor texture extent')
    require(enum(s['Format'],'ETextureSourceFormat')=='TSF_BGRA8' and enum(s['CompressionFormat'],'ETextureSourceCompressionFormat')=='TSCF_UEDELTA','Unsupported source pixel/compression format')
    if 'LayerFormat' in s:
        require(s['LayerFormat']['type']==['ArrayProperty','ByteProperty','ETextureSourceFormat','/Script/Engine'],'Invalid layer format')
        r=Reader(s['LayerFormat']['data']);require(r.i()==1 and r.name(names)=='TSF_BGRA8' and r.pos==len(r.data),'Unsupported texture layers')
    require(s['BlockDataOffsets']['data']==struct.pack('<iq',1,0),'Unsupported texture blocks')
    tail=b[e['offset']+e['script_end']:e['offset']+e['size']]
    require(len(tail)==60 and tail[:10]==bytes.fromhex('00000000000000020000') and tail[-6:]==bytes(6),'Unsupported texture bulk reference')
    digest=tail[26:46].hex();size=struct.unpack_from('<Q',tail,46)[0];require(size==w*h*4,'Invalid source byte size')
    raw,info=extract_payload(b,read_trailer(b,max(x['offset']+x['size'] for x in ex)),digest,size,decoder)
    a=decode_delta(raw,w,h);rgba=a[:,:,[2,1,0,3]]
    # Independent serialized extrema from source layer metadata; 8-bit normalized values.
    color=s['LayerColorInfo_LockProtected'];require(color['type']==['ArrayProperty','StructProperty','TextureSourceLayerColorInfo','/Script/Engine'],'Invalid source color metadata')
    r=Reader(color['data']);require(r.i()==1,'Unsupported source color layers'); c=read_tag_stream(r,names);require(r.pos==len(r.data),'Unexpected source color metadata tail')
    for k,actual in [('ColorMin',rgba.min(axis=(0,1))),('ColorMax',rgba.max(axis=(0,1)))]:
        t=c.get(k);require(t and t['type']==['StructProperty','LinearColor','/Script/CoreUObject'] and len(t['data'])==16,'Missing source color extrema')
        expected=struct.unpack('<4f',t['data']); values=[float(x)/255 for x in actual]
        if boolean('bUseLegacyGamma',False) and boolean('SRGB',True): values[:3]=[x**2.2 for x in values[:3]]
        require(all(abs(x-y)<1e-6 for x,y in zip(values,expected)),f'Serialized {k} mismatch: {actual} vs {expected}')
    # Raw pixels are preserved. Green-channel flip is a material operation, not baked.
    addr=lambda k:enum(tags[k],'TextureAddress') if k in tags else 'TA_Wrap'
    meta=dict(width=w,height=h,format='TSF_BGRA8',mips=1,source_png=False,srgb=boolean('SRGB',True),flip_y=boolean('bFlipGreenChannel',False),address_x=addr('AddressX'),address_y=addr('AddressY'),nearest=enum(tags['Filter'],'TextureFilter')=='TF_Nearest' if 'Filter' in tags else False,profile='UE5 editor UEDELTA',source_hash=info['hash'],rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest(),color_extrema_verified=True)
    meta['clamp']=meta['address_x']==meta['address_y']=='TA_Clamp'
    return png_bytes(w,h,rgba.tobytes()),meta
