"""Explicit-version cooked Texture2D sidecar reader for validated legacy mip layouts."""
import argparse
import re
import struct
import zlib
from pathlib import Path

MAGIC = b'\xc1\x83\x2a\x9e'
FORMATS = {'PF_DXT1': 8, 'PF_BC4': 8, 'PF_BC5': 16}
MAX_BYTES = 128 * 1024 * 1024


def read_limited(path):
    if path.stat().st_size > MAX_BYTES:
        raise ValueError('Texture sidecar exceeds safety limit')
    return path.read_bytes()


def read_texture(path, version):
    """Return largest mip after validating the entire candidate platform block.

    Does not decode arbitrary unversioned properties. Caller supplies known version.
    Only split cooked packages with exactly one supported 2D platform block.
    """
    if version=='5.5':
        from ue5_modern_texture import read_texture55
        w,h,fmt,mips=read_texture55(path)
        return w,h,fmt,mips[0],len(mips)
    if version not in ('4.18', '4.27', '5.0'):
        raise NotImplementedError('Unsupported cooked texture profile')
    path = Path(path)
    header = read_limited(path)
    data = read_limited(path.with_suffix('.uexp'))
    bulk_path = path.with_suffix('.ubulk')
    bulk = read_limited(bulk_path) if bulk_path.is_file() else b''
    if header[:4] != MAGIC or not data.endswith(MAGIC):
        raise ValueError('Invalid package or sidecar signature')
    # Require the serialized pixel format to occur in the package's name table bytes.
    candidates = []
    for match in re.finditer(rb'PF_(?:DXT1|BC4|BC5)\x00', data):
        try:
            p = match.start()
            fmt = match.group()[:-1].decode('ascii')
            if match.group() not in header or p < 16:
                continue
            w, h, slices, length = struct.unpack_from('<4i', data, p-16)
            if slices != 1 or length != len(match.group()) or not (1 <= w <= 8192 and 1 <= h <= 8192):
                continue
            p = match.end()
            first, count = struct.unpack_from('<2i', data, p); p += 8
            if first != 0 or not 1 <= count <= 15:
                continue
            if version == '4.18':
                if struct.unpack_from('<i', data, p)[0] != 1: continue
                p += 4
            mipmaps = []
            ranges = []
            for i in range(count):
                if version == '4.27':
                    if struct.unpack_from('<i', data, p)[0] != 1: raise ValueError('Not cooked mip')
                    p += 4
                flags, elements, size, offset = struct.unpack_from('<Iiiq', data, p); p += 20
                mw, mh = max(4, w >> i), max(4, h >> i)
                expected = ((mw+3)//4)*((mh+3)//4)*FORMATS[fmt]
                if size != expected or elements != size:
                    raise ValueError('Mip payload size mismatch')
                if flags == 0x48:
                    if offset != len(header)+p or p+size > len(data)-4:
                        raise ValueError('Invalid inline mip offset')
                    raw = data[p:p+size]; p += size
                elif flags == (0x501 if version == '4.18' else 0x10501):
                    start = offset + len(header)+len(data)-4 if version == '4.18' else offset
                    if start < 0 or start+size > len(bulk) or any(start < b and start+size > a for a,b in ranges):
                        raise ValueError('Invalid external mip range')
                    ranges.append((start,start+size)); raw = bulk[start:start+size]
                else:
                    raise ValueError('Unsupported bulk flags')
                dims = struct.unpack_from('<2i', data, p); p += 8
                if dims != (mw,mh): raise ValueError('Mip dimensions mismatch')
                if version != '4.18' or i < count-1:
                    if struct.unpack_from('<i', data, p)[0] != 1: raise ValueError('Unsupported depth')
                    p += 4
                mipmaps.append(raw)
            tail = 12 if version == '4.18' else 16
            if len(data)-p != tail: raise ValueError('Unexpected platform tail')
            if version != '4.18':
                if data[p:p+4] != bytes(4): raise ValueError('Virtual texture not supported')
                p += 4
            name_index, number = struct.unpack_from('<ii', data, p)
            if not 0 <= name_index < 100000 or number != 0: raise ValueError('Invalid terminal FName')
            if ranges and (min(a for a,b in ranges) != 0 or sum(b-a for a,b in ranges) != len(bulk)):
                raise ValueError('Unexpected external payload layout')
            candidates.append((w,h,fmt,mipmaps[0],count))
        except (ValueError, struct.error, OverflowError):
            continue
    if len(candidates) != 1:
        raise ValueError(f'Expected one validated texture block, found {len(candidates)}')
    return candidates[0]


def alpha_block(block):
    a,b = block[:2]
    palette = [a,b]+([( (7-i)*a+i*b)//7 for i in range(1,7)] if a>b else [((5-i)*a+i*b)//5 for i in range(1,5)]+[0,255])
    indices = int.from_bytes(block[2:8], 'little')
    return [palette[(indices >> (3*i)) & 7] for i in range(16)]


def rgb565(value):
    r,g,b = value>>11, (value>>5)&63, value&31
    return ((r<<3)|(r>>2), (g<<2)|(g>>4), (b<<3)|(b>>2), 255)


def decode_rgba(w,h,fmt,data):
    stride = FORMATS[fmt]
    if not (1 <= w <= 8192 and 1 <= h <= 8192) or w*h*4 > MAX_BYTES:
        raise ValueError('Image size limit')
    if len(data) != ((w+3)//4)*((h+3)//4)*stride:
        raise ValueError('Compressed image size mismatch')
    out = bytearray(w*h*4); p = 0
    for y in range(0,h,4):
        for x in range(0,w,4):
            block = data[p:p+stride]; p += stride
            if fmt == 'PF_DXT1':
                a,b,indices = struct.unpack('<HHI',block)
                c,d = rgb565(a),rgb565(b)
                mix = lambda i,j,k: tuple((i*u+j*v)//k for u,v in zip(c,d))
                palette = [c,d,mix(2,1,3),mix(1,2,3)] if a>b else [c,d,mix(1,1,2),(0,0,0,0)]
                pixels = [palette[(indices>>(2*i))&3] for i in range(16)]
            elif fmt == 'PF_BC4':
                pixels = [(v,v,v,255) for v in alpha_block(block)]
            else:
                # Preserve BC5 channels, do not assume normal-map semantics.
                pixels = [(r,g,0,255) for r,g in zip(alpha_block(block[:8]),alpha_block(block[8:]))]
            for i,rgba in enumerate(pixels):
                xx,yy=x+i%4,y+i//4
                if xx<w and yy<h:
                    offset=(yy*w+xx)*4; out[offset:offset+4]=bytes(rgba)
    return bytes(out)


def png_bytes(w,h,rgba):
    def chunk(kind,data):
        return struct.pack('>I',len(data))+kind+data+struct.pack('>I',zlib.crc32(kind+data)&0xffffffff)
    rows = b''.join(b'\0'+rgba[y*w*4:(y+1)*w*4] for y in range(h))
    return b'\x89PNG\r\n\x1a\n'+chunk(b'IHDR',struct.pack('>2I5B',w,h,8,6,0,0,0))+chunk(b'IDAT',zlib.compress(rows))+chunk(b'IEND',b'')


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('asset',type=Path); p.add_argument('output',type=Path)
    p.add_argument('--version',required=True,choices=['4.18','4.27','5.0','5.5'])
    a=p.parse_args()
    w,h,fmt,raw,count=read_texture(a.asset,a.version)
    with a.output.open('xb') as f: f.write(png_bytes(w,h,decode_rgba(w,h,fmt,raw)))
    print(f'{w}x{h} {fmt}, {count} mips validated; largest mip extracted')
