"""Bounded UE4 editor Texture2D source-art reader (versioned monolithic assets).
Source-art serialization: UObject properties, GUID marker, strip flags,
FByteBulkData, Texture2D strip flags and cooked marker. UE5 editor bulk data
is deliberately not supported here.
"""
import struct
import zlib
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
    from package_inspector import inspect_package
    meta=inspect_package(filepath)
    if meta.get('ue4') in (508,522) and meta.get('ue5') is None:
        from classic_texture import read_source
        return read_source(filepath)
    raise NotImplementedError('Unsupported native UE4 editor source texture profile')
