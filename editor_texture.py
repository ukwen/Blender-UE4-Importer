"""Bounded UE4 editor Texture2D source-art reader (versioned monolithic assets).
Source-art serialization: UObject properties, GUID marker, strip flags,
FByteBulkData, Texture2D strip flags and cooked marker. UE5 editor bulk data
is deliberately not supported here.
"""
import struct
import zlib
from pathlib import Path
from native_texture import MAX_BYTES, png_bytes

PNG = b'\x89PNG\r\n\x1a\n'


def validate_png(data, width, height):
    """Check source PNG framing, checksums, dimensions and bounded scanline size."""
    if not data.startswith(PNG):
        raise ValueError('Source is not PNG')
    pos = 8; parts = []; channels = None
    while pos < len(data):
        if len(data)-pos < 12: raise ValueError('Truncated PNG chunk')
        n, kind = struct.unpack_from('>I4s', data, pos)
        if n > len(data)-pos-12: raise ValueError('Truncated PNG payload')
        chunk = data[pos+8:pos+8+n]
        crc = struct.unpack_from('>I', data, pos+8+n)[0]
        if zlib.crc32(kind+chunk)&0xffffffff != crc: raise ValueError('PNG CRC mismatch')
        if pos == 8:
            if kind != b'IHDR' or n != 13: raise ValueError('Missing PNG header')
            w,h,depth,ctype,comp,filter_method,interlace = struct.unpack('>2I5B',chunk)
            if (w,h)!=(width,height) or depth!=8 or comp or filter_method or interlace:
                raise NotImplementedError('Unsupported PNG dimensions, depth or interlace')
            channels = {0:1,2:3,4:2,6:4}.get(ctype)
            if channels is None: raise NotImplementedError('Unsupported PNG color type')
        elif kind == b'IHDR': raise ValueError('Duplicate PNG header')
        elif kind == b'IDAT': parts.append(chunk)
        elif kind == b'IEND':
            if n or pos+12 != len(data) or not parts: raise ValueError('Invalid PNG ending')
            expected = height*(1+width*channels)
            if expected > MAX_BYTES: raise ValueError('PNG exceeds decoded size limit')
            dec=zlib.decompressobj(); raw=dec.decompress(b''.join(parts),expected+1)
            if len(raw)!=expected or not dec.eof or dec.unconsumed_tail or dec.unused_data:
                raise ValueError('Invalid PNG scanline length')
            if any(raw[i]>4 for i in range(0,expected,1+width*channels)):
                raise ValueError('Invalid PNG row filter')
            return data
        elif kind[0] & 32 == 0: raise NotImplementedError('Unsupported critical PNG chunk')
        pos += n+12
    raise ValueError('Missing PNG ending')


def source_png(data, width, height, fmt, mips, compressed):
    if not 1 <= width <= 8192 or not 1 <= height <= 8192 or width*height*4 > MAX_BYTES:
        raise ValueError('Source texture size limit')
    if fmt not in ('TSF_BGRA8','TSF_RGBA8','TSF_G8'):
        raise NotImplementedError('Unsupported source pixel format '+str(fmt))
    if not 1 <= mips <= max(width,height).bit_length(): raise ValueError('Invalid source mip count')
    if compressed:
        if mips != 1: raise NotImplementedError('Compressed source with multiple mips')
        return validate_png(data,width,height)
    bpp = 1 if fmt=='TSF_G8' else 4
    expected = sum(max(1,width>>i)*max(1,height>>i)*bpp for i in range(mips))
    if len(data)!=expected: raise ValueError('Source mip size mismatch')
    raw=data[:width*height*bpp]
    if fmt=='TSF_BGRA8':
        rgba=bytearray(raw); rgba[0::4]=raw[2::4]; rgba[2::4]=raw[0::4]
    elif fmt=='TSF_RGBA8': rgba=raw
    else:
        rgba=bytearray(width*height*4)
        rgba[0::4]=rgba[1::4]=rgba[2::4]=raw; rgba[3::4]=b'\xff'*(width*height)
    return png_bytes(width,height,rgba)


def read_editor_texture(filepath, project=None):
    """Return (PNG, metadata); use export and source bulk offsets, never thumbnails."""
    import uasset
    from umesh import DecodeCompressedRawMesh
    path=Path(filepath); size=path.stat().st_size
    if size>MAX_BYTES: raise ValueError('Editor package size limit')
    if any(path.with_suffix(ext).exists() for ext in ('.uexp','.ubulk','.uptnl')):
        raise NotImplementedError('Split editor source packages unsupported')
    asset=uasset.UAsset(str(path), False, project)
    try:
        asset.Read(False); s=asset.summary; f=asset.f
        if s.version_legacy != -7 or not 513 <= s.version_ue4 <= 522 or s.version_ue4_licensee or s.package_flags & (0x8|0x2000):
            raise NotImplementedError('Unsupported UE4 editor source package profile')
        exports=[e for e in asset.exports if e.export_class_type=='Texture2D']
        if len(exports)!=1: raise ValueError('Expected one Texture2D export')
        e=exports[0]; start=e.serial_desc.offset; end=start+e.serial_desc.count
        if not s.header_size <= start < end <= size: raise ValueError('Invalid texture export range')
        f.Seek(start)
        props=uasset.Properties().Read(asset,read_children=False)
        src=props.TryGetValue('Source')
        if not isinstance(src,uasset.Properties): raise ValueError('Missing decoded TextureSource properties')
        source_prop=props['Source']
        if getattr(source_prop,'raw',None) is not None: raise ValueError('Source property length mismatch')
        get=src.TryGetValue
        w,h,mips=get('SizeX'),get('SizeY'),get('NumMips')
        fmt=get('Format')
        if get('NumSlices')!=1 or not all(type(x) is int for x in (w,h,mips)):
            raise NotImplementedError('Unsupported source dimensions/slices')
        if not 1<=w<=8192 or not 1<=h<=8192 or w*h*4>MAX_BYTES:
            raise ValueError('Source texture size limit')
        compression=get('CompressionFormat')
        if compression not in (None,'TSCF_None','TSCF_PNG'): raise NotImplementedError('Unsupported source compression')
        compressed=bool(get('bPNGCompressed',False) or compression=='TSCF_PNG')
        if f.Position()+30>end: raise ValueError('Truncated texture native header')
        guid=f.ReadInt32()
        if guid not in (0,1): raise ValueError('Invalid object GUID marker')
        if guid: f.ReadGuid()
        strip=f.ReadBytes(2)
        if len(strip)!=2 or strip[0]&1: raise NotImplementedError('Editor source stripped')
        flags,count,packed,offset=f.ReadStruct('<IIIq',20)
        if flags & ~(1|2|8|0x40|0x10000) or not 0<count<=MAX_BYTES or not 0<packed<=MAX_BYTES:
            raise NotImplementedError('Unsupported source bulk flags or size')
        inline=bool(flags&0x40); external=bool(flags&1)
        if inline==external: raise NotImplementedError('Unknown source bulk placement')
        here=f.Position()
        if not flags&0x10000: offset+=s.bulk_data_offset
        if inline:
            if offset!=here or here+packed+6!=end: raise ValueError('Invalid inline source range')
            data=f.ReadBytes(packed)
        else:
            if not max(end,s.bulk_data_offset)<=offset or offset+packed>size-4:
                raise ValueError('Invalid external source range')
            f.Seek(offset); data=f.ReadBytes(packed); f.Seek(here)
        if len(data)!=packed or f.Position()+6!=end: raise ValueError('Source export length mismatch')
        f.ReadBytes(2)
        if f.ReadInt32()!=0: raise NotImplementedError('Cooked Texture2D is not editor source')
        if flags&2:
            try: data=DecodeCompressedRawMesh(data,count)
            except zlib.error as exc: raise ValueError('Invalid compressed editor source') from exc
        elif len(data)!=count: raise ValueError('Source bulk size mismatch')
        png=source_png(data,w,h,fmt,mips,compressed)
        return png, {'width':w,'height':h,'format':fmt,'mips':mips,'source_png':compressed,
                     'srgb':props.TryGetValue('SRGB',True),'flip_y':props.TryGetValue('bFlipGreenChannel',False),
                     'address_x':props.TryGetValue('AddressX','TA_Wrap'),'address_y':props.TryGetValue('AddressY','TA_Wrap'),
                     'clamp':props.TryGetValue('AddressX','TA_Wrap')=='TA_Clamp' and props.TryGetValue('AddressY','TA_Wrap')=='TA_Clamp',
                     'nearest':props.TryGetValue('Filter')=='TF_Nearest'}
    finally: asset.Close()
