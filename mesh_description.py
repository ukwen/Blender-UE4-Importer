"""Bounded legacy UE4 MeshDescription decoder, observed editor layout.
Not a UE5 decoder. Fail closed on unknown serialization or inconsistent references.
"""
import math
import struct


class Reader:
    def __init__(self, data):
        self.data = memoryview(data)
        self.pos = 0

    def take(self, size):
        if size < 0 or size > len(self.data) - self.pos:
            raise ValueError('Truncated MeshDescription')
        result = self.data[self.pos:self.pos+size]
        self.pos += size
        return result

    def integer(self):
        return struct.unpack('<i', self.take(4))[0]

    def count(self, limit=2_000_000):
        value = self.integer()
        if not 0 <= value <= limit:
            raise ValueError('Invalid MeshDescription count')
        return value

    def string(self):
        n = self.integer()
        if not 0 < abs(n) <= 4096:
            raise ValueError('Invalid MeshDescription string length')
        raw = bytes(self.take(n if n > 0 else -2*n))
        end = b'\0' if n > 0 else b'\0\0'
        if not raw.endswith(end):
            raise ValueError('Unterminated MeshDescription string')
        return raw[:-len(end)].decode('utf-8' if n > 0 else 'utf-16-le')

    def sparse(self, width):
        count = self.count()
        words = (count+31)//32
        masks = struct.unpack('<'+'I'*words, self.take(words*4))
        if words and count%32 and masks[-1] >> (count%32):
            raise ValueError('Invalid sparse allocation mask')
        ids = [i for i in range(count) if masks[i//32] & (1 << (i%32))]
        values = struct.iter_unpack('<'+'i'*width, self.take(len(ids)*width*4)) if width else [()] * len(ids)
        return count, dict(zip(ids, values))

    def attributes(self, count):
        if self.count() != count:
            raise ValueError('Attribute element count mismatch')
        result = {}
        formats = {0:'4f', 1:'3f', 2:'2f', 3:'f', 4:'i', 5:'B'}
        for _ in range(self.count(128)):
            name = self.string().strip()
            kind = self.integer()
            if name in result or self.count() != count:
                raise ValueError('Invalid attribute header')
            channels = self.count(16)
            arrays = []
            for _ in range(channels):
                if kind == 6:
                    if self.count() != count: raise ValueError('Name array count mismatch')
                    arrays.append([self.string() for _ in range(count)])
                elif kind in formats:
                    fmt = '<'+formats[kind]
                    width = struct.calcsize(fmt)
                    if self.integer() != width or self.count() != count:
                        raise ValueError('Attribute array shape mismatch')
                    arrays.append(list(struct.iter_unpack(fmt, self.take(width*count))))
                else:
                    raise NotImplementedError(f'Unknown MeshDescription attribute type {kind}')
            if kind == 6: self.string()
            elif kind in formats: self.take(4 if kind == 5 else struct.calcsize('<'+formats[kind]))
            else: raise NotImplementedError(f'Unknown MeshDescription attribute type {kind}')
            self.integer()  # attribute flags
            result[name] = (kind, arrays)
        return result


def decode_mesh_description(payload):
    r = Reader(payload)
    nv, vertices = r.sparse(0)
    ni, instances = r.sparse(1)
    ne, edges = r.sparse(2)
    np, polygons = r.sparse(2)
    ng, groups = r.sparse(0)
    va, ia, ea, pa, ga = (r.attributes(n) for n in (nv, ni, ne, np, ng))
    nt, triangles = r.sparse(4)
    ta = r.attributes(nt)
    if r.pos != len(payload): raise ValueError('Unexpected trailing MeshDescription data')
    def required(attrs, name, kind, channels=None):
        if name not in attrs or attrs[name][0] != kind:
            raise ValueError('Missing or invalid attribute '+name)
        arrays = attrs[name][1]
        if not arrays or channels is not None and len(arrays) != channels:
            raise ValueError('Invalid attribute channels '+name)
        return arrays
    pos = required(va,'Position',1,1)[0]
    normals = required(ia,'Normal',1,1)[0]
    uvs = required(ia,'TextureCoordinate',2) if 'TextureCoordinate' in ia else []
    colors = required(ia,'Color',0,1)[0] if 'Color' in ia else None
    tangents = required(ia,'Tangent',1,1)[0] if 'Tangent' in ia else None
    signs = required(ia,'BinormalSign',3,1)[0] if 'BinormalSign' in ia else None
    hard_edges = required(ea,'IsHard',5,1)[0] if 'IsHard' in ea else None
    slots = required(ga,'ImportedMaterialSlotName',6,1)[0]
    if not vertices or not triangles or not groups: raise ValueError('Empty MeshDescription')
    if any(v[0] not in vertices for v in instances.values()): raise ValueError('Invalid vertex instance reference')
    if any(a not in vertices or b not in vertices or a == b for a,b in edges.values()): raise ValueError('Invalid edge reference')
    if any(g[0] != 0 or g[1] not in groups for g in polygons.values()): raise ValueError('Invalid polygon group reference')
    for *corners,poly in triangles.values():
        if poly not in polygons or any(c not in instances for c in corners): raise ValueError('Invalid triangle reference')
        if len({instances[c][0] for c in corners}) != 3: raise ValueError('Degenerate triangle')
    for values in [pos,normals,*uvs]+[v for v in (colors,tangents,signs) if v is not None]:
        if any(not math.isfinite(x) for item in values for x in item): raise ValueError('Non-finite mesh attribute')
    return dict(vertices={i:pos[i] for i in vertices}, instances={i:v[0] for i,v in instances.items()},
                triangles=[(polygons[p][1],tuple(c)) for *c,p in triangles.values()], normals=normals,
                uvs=uvs, colors=colors, tangents=tangents, signs=signs,
                slots={i:slots[i] for i in groups}, edges=edges,
                hard_edges={i:bool(hard_edges[i][0]) for i in edges} if hard_edges is not None else None)
