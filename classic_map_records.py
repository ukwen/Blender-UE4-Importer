"""Map-owned object views of typed UE4 editor records.

Only fields consumed by placement and light reconstruction are interpreted.
The view supplies identity-stable references to existing integration contracts;
no inherited parser classes or arbitrary property payload interpretation.
"""
from dataclasses import dataclass
import math
import struct
from pathlib import Path
from package_records import read_package, ExportRecord
from ue4_property_records import read_records
from skeleton_native import Reader
from classic_actor_layout import string_value, require

_TRANSFORMS = {'RelativeLocation':'Vector', 'RelativeRotation':'Rotator', 'RelativeScale3D':'Vector'}
_OBJECTS = {'RootComponent','StaticMeshComponent','LightComponent','Mesh','CapsuleComponent','AttachParent','MasterPoseComponent','StaticMesh','SkeletalMesh'}
_BOOLS = {'bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale','CastShadows','bVisible','bAffectsWorld'}

@dataclass(frozen=True)
class VectorValue:
    x: float
    y: float
    z: float

@dataclass(frozen=True)
class ColorValue:
    r: int
    g: int
    b: int
    a: int

@dataclass(frozen=True)
class Value:
    value: object
    type: str = ''
    struct_type: str = ''
    len: int = 0

class Fields(dict):
    def TryGetValue(self, key, default=None):
        return self[key].value if key in self else default

class MapEntry:
    def __init__(self, owner, index, record):
        self.owner, self.index, self.record = owner, index, record
        self.object_name, self.outer_index = record.name, record.outer
        self.export_class_type = record.kind
        self.properties = None

    @property
    def export_class(self):
        return self.owner.ref(self.record.class_index) if isinstance(self.record, ExportRecord) else None

    @property
    def package_identity(self):
        return self.owner.table.package(self.index) if self.index < 0 else ''

    def ReadProperties(self, read_children=False):
        require(self.index > 0, 'Expected map export')
        if self.properties is None:
            self.properties = self.owner.fields(self.record)
        return self.properties

class MapRecords:
    def __init__(self, path):
        meta, self.raw, self.table = read_package(path)
        require(meta['ue4'] in (508,522) and meta['ue5'] is None and meta['licensee']==0, 'Unsupported classic map profile')
        self.meta = meta
        self.imports = tuple(MapEntry(self,-i,r) for i,r in enumerate(self.table.imports,1))
        self.exports = tuple(MapEntry(self,i,r) for i,r in enumerate(self.table.exports,1))

    def ref(self, index):
        self.table.reference(index)
        return self.imports[~index] if index < 0 else self.exports[index-1] if index else None

    def GetExport(self, index):
        require(index > 0,'Expected export index')
        return self.ref(index)

    def fields(self, record):
        p = read_records(Reader(self.raw[record.offset:record.offset+record.size]), self.table.names)
        result = Fields()
        for v in p:
            key, kind, raw = v.name, v.kind, v.data
            if v.index:
                require(key not in _OBJECTS|_BOOLS|set(_TRANSFORMS)|{'ActorLabel','AttachSocketName','OverrideMaterials','Intensity','LightColor'}, 'Indexed placement property unsupported')
                continue
            value = None
            if kind == 'ObjectProperty':
                require(len(raw)==4, 'Invalid object property: '+key)
                value = self.ref(struct.unpack('<i',raw)[0])
            elif key in _OBJECTS:
                raise ValueError('Invalid object field: '+key)
            elif key in _TRANSFORMS:
                require(kind=='StructProperty' and v.parameters==(_TRANSFORMS[key],) and len(raw)==12,'Invalid transform: '+key)
                values=struct.unpack('<3f',raw); require(all(map(math.isfinite,values)), 'Nonfinite transform: '+key)
                value=VectorValue(*values)
            elif key in _BOOLS:
                require(kind=='BoolProperty','Invalid boolean: '+key); value=v.boolean
            elif key=='ActorLabel':
                value=string_value({key:v},key,'')
            elif key=='AttachSocketName':
                require(kind=='NameProperty' and len(raw)==8,'Invalid socket name');value=Reader(raw).name(self.table.names)
            elif key=='OverrideMaterials':
                require(kind=='ArrayProperty' and v.parameters==('ObjectProperty',),'Invalid material override array')
                r=Reader(raw);value=[Value(self.ref(r.i())) for _ in range(r.count(4096))];require(r.pos==len(raw),'Material override trailer')
            elif key=='Intensity':
                require(kind=='FloatProperty' and len(raw)==4,'Invalid light intensity');value=struct.unpack('<f',raw)[0]
            elif key=='LightColor':
                require(kind=='StructProperty' and v.parameters==('Color',) and len(raw)==4,'Invalid light color');b,g,r,a=raw;value=ColorValue(r,g,b,a)
            result[key]=Value(value,kind,v.parameters[0] if v.parameters else '',len(raw))
        return result


def owned_export(value, asset):
    # Identity membership, not duck-typed arbitrary package objects.
    if isinstance(value,MapEntry):
        return value.owner is asset and value.index>0
    return value is not None and any(value is entry for entry in asset.exports)


def apply_component_transform(entry, obj):
    from classic_layout_blender import apply_transform
    fields=entry.properties
    triples=[]
    for key,default in [('RelativeLocation',(0.,0.,0.)),('RelativeRotation',(0.,0.,0.)),('RelativeScale3D',(1.,1.,1.))]:
        v=fields.TryGetValue(key)
        triples.append((v.x,v.y,v.z) if v is not None else default)
    apply_transform(obj,*triples)
