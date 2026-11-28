"""Bounded classic UE4 property tag records, with opaque native payloads.

Layout reference: UAssetAPI PropertyTypes/Objects/PropertyData.cs (MIT; see
third_party/UAssetAPI-LICENSE.txt) and original versioned UE4 522 editor
fixtures. No inherited UProperty objects or Blender imports. Only supported
header types are interpreted; container contents remain opaque.
"""
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PropertyRecord:
    name: str
    kind: str
    index: int
    parameters: tuple[str, ...]
    data: bytes
    boolean: bool | None = None
    property_guid: bytes | None = None
    struct_guid: bytes | None = None


_PLAIN = frozenset(('IntProperty', 'FloatProperty', 'ObjectProperty', 'NameProperty',
                    'StrProperty', 'Int64Property', 'UInt32Property', 'DoubleProperty',
                    'TextProperty', 'SoftObjectProperty'))
_ONE = frozenset(('ArrayProperty', 'SetProperty', 'ByteProperty', 'EnumProperty'))


def read_records(reader, names):
    """Advance a bounded reader through the None terminator, not the native tail."""
    entries = []
    seen = set()
    while True:
        key = reader.name(names)
        if key == 'None':
            return tuple(entries)
        if len(entries) >= 10000:
            raise ValueError('Property count limit')
        kind = reader.name(names)
        size, index = reader.unpack('ii')
        if size < 0 or not 0 <= index < 4096 or (key, index) in seen:
            raise ValueError('Invalid or repeated property tag')
        seen.add((key, index))
        parameters = ()
        struct_guid = boolean = guid = None
        if kind == 'StructProperty':
            parameters = (reader.name(names),)
            struct_guid = reader.take(16)
        elif kind in _ONE:
            parameters = (reader.name(names),)
        elif kind == 'MapProperty':
            parameters = (reader.name(names), reader.name(names))
        elif kind == 'BoolProperty':
            flag = reader.take(1)[0]
            if flag not in (0, 1) or size != 0:
                raise ValueError('Invalid bool property')
            boolean = bool(flag)
        elif kind not in _PLAIN:
            raise ValueError('Unsupported classic property tag type: ' + kind)
        flag = reader.take(1)[0]
        if flag not in (0, 1):
            raise ValueError('Invalid property GUID flag')
        if flag:
            guid = reader.take(16)
        entries.append(PropertyRecord(key, kind, index, parameters, bytes(reader.take(size)), boolean, guid, struct_guid))


def read_tagged_properties(reader, names):
    """Compatibility view for animation/skeleton readers: no static arrays."""
    tags, kinds = {}, {}
    for record in read_records(reader, names):
        if record.index != 0 or record.name in tags:
            raise ValueError('Unsupported indexed property in compatibility view')
        tags[record.name] = int(record.boolean) if record.kind == 'BoolProperty' else record.data
        kinds[record.name] = (record.kind, record.parameters[0] if record.parameters else None)
    return tags, kinds
