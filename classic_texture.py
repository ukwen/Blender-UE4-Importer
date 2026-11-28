"""Read editor TextureSource from typed UE4 508/522 package records.

Only verified monolithic source-art payload profiles are interpreted. Texture
payload offset and size checks use the serialized export and bulk-data bounds.
"""
from pathlib import Path
import struct
import zlib
from package_records import read_package,root_export
from skeleton_native import Reader
from ue4_property_records import read_records
from source_compression import decompress_chunks
from native_texture import MAX_BYTES


def require(ok,message):
    if not ok: raise ValueError(message)


def properties(reader,names):
    rows=read_records(reader,names)
    require(all(p.index==0 for p in rows),'Indexed texture properties unsupported')
    return {p.name:p for p in rows}


def read_source(path):
    from editor_texture import source_png
    path=Path(path)
    require(path.stat().st_size<=MAX_BYTES,'Editor package size limit')
    meta,raw,table=read_package(path)
    require(meta['ue4'] in (508,522) and meta['ue5'] is None and not meta['flags']&8 and meta['licensee']==0,'Unsupported classic texture profile')
    if meta['ue4']==522:
        from package_inspector import inspect_package
        summary=inspect_package(path,include_bulk_522=True)
        require(summary.get('status')=='tables_inspected' and 'bulk_data_offset' in summary and summary['size']==len(raw),'Unsupported 522 bulk-data summary')
        meta['bulk_data_offset']=summary['bulk_data_offset']
    e=root_export(table,'Texture2D'); end=e.offset+e.size
    r=Reader(raw[e.offset:end]); p=properties(r,table.names)
    src=p.get('Source'); require(src is not None and src.kind=='StructProperty' and src.parameters==('TextureSource',),'Missing texture source properties')
    nested=Reader(src.data); s=properties(nested,table.names);require(nested.pos==len(src.data),'Unexpected source property trailer')
    def integer(key):
        v=s.get(key);require(v is not None and v.kind=='IntProperty' and len(v.data)==4,'Invalid source '+key)
        return struct.unpack('<i',v.data)[0]
    def named(fields,key,default=None):
        v=fields.get(key)
        if v is None: return default
        require(v.kind in ('ByteProperty','EnumProperty','NameProperty') and len(v.data)==8,'Invalid texture name '+key)
        return Reader(v.data).name(table.names)
    def boolean(fields,key,default=False):
        v=fields.get(key)
        if v is None:return default
        require(v.kind=='BoolProperty','Invalid texture boolean '+key)
        return v.boolean
    w,h,mips=integer('SizeX'),integer('SizeY'),integer('NumMips');fmt=named(s,'Format')
    require(integer('NumSlices')==1 and 1<=w<=8192 and 1<=h<=8192 and w*h*4<=MAX_BYTES,'Unsupported source dimensions/slices')
    compression=named(s,'CompressionFormat')
    if compression not in (None,'TSCF_None','TSCF_PNG'):raise NotImplementedError('Unsupported source compression')
    compressed=boolean(s,'bPNGCompressed') or compression=='TSCF_PNG'
    marker=r.i();require(marker in (0,1),'Invalid object GUID marker')
    if marker:r.take(16)
    require(not r.take(2)[0]&1,'Editor source stripped')
    flags,count,packed,offset=r.unpack('IIIq')
    if flags & ~(1|2|8|0x40|0x10000):raise NotImplementedError('Unsupported source bulk flags')
    require(0<count<=MAX_BYTES and 0<packed<=MAX_BYTES,'Invalid source bulk extent')
    inline,external=bool(flags&0x40),bool(flags&1)
    require(inline!=external,'Unknown source bulk placement')
    if not flags&0x10000:offset+=meta['bulk_data_offset']
    if inline:
        require(offset==e.offset+r.pos,'Invalid inline source offset');data=r.take(packed)
    else:
        require(offset>=max(end,meta['bulk_data_offset']) and offset+packed<=len(raw)-4,'Invalid external source range');data=raw[offset:offset+packed]
    require(len(data)==packed and len(r.data)-r.pos==6,'Invalid source export length')
    r.take(2)
    if r.i()!=0:raise NotImplementedError('Cooked Texture2D is not editor source')
    if flags&2:
        try:data=decompress_chunks(data,count)
        except zlib.error as exc:raise ValueError('Invalid compressed editor source') from exc
    else:require(len(data)==count,'Source bulk size mismatch')
    ax,ay=named(p,'AddressX','TA_Wrap'),named(p,'AddressY','TA_Wrap')
    return source_png(data,w,h,fmt,mips,compressed),dict(width=w,height=h,format=fmt,mips=mips,source_png=compressed,srgb=boolean(p,'SRGB',True),flip_y=boolean(p,'bFlipGreenChannel'),address_x=ax,address_y=ay,clamp=ax==ay=='TA_Clamp',nearest=named(p,'Filter')=='TF_Nearest')
