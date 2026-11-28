"""Bounded UE4.27 tagged layer topology records, independent of Blender/UAsset.

Uses the MIT-reference classic property reader and typed object tables. Only
explicit detached snapshots are supported; parent reconciliation is not inferred.
"""
from dataclasses import dataclass
from uuid import UUID
from skeleton_native import Reader
from ue4_property_records import read_records
from package_records import ImportRecord, read_package


def check(ok, message):
    if not ok:
        raise ValueError(message)


@dataclass(frozen=True, slots=True)
class LayerStack:
    layers: tuple
    blends: tuple
    states: tuple

    def __post_init__(self):
        check(all(isinstance(x, tuple) for x in (self.layers, self.blends, self.states)), 'Layer arrays must be immutable')
        count = len(self.layers)
        check(1 <= count <= 32 and len(self.blends) == count-1 and len(self.states) == count, 'Invalid layer stack lengths')
        check(all(type(x) is bool for x in self.states) and self.states[0], 'Invalid layer states or disabled background')
        check(all(not enabled or ref is not None for ref, enabled in zip(self.layers, self.states)), 'Missing active layer')

    def legacy_view(self):
        return tuple(list(x) for x in (self.layers, self.blends, self.states))


@dataclass(frozen=True, slots=True)
class DetachedSnapshot:
    name: str
    stack: LayerStack
    guids: tuple
    links: tuple

    def __post_init__(self):
        check(isinstance(self.name, str) and self.name.strip() and self.name != 'None', 'Invalid layer parameter name')
        check(isinstance(self.stack, LayerStack), 'Expected immutable layer stack')
        validate_guids(self.guids, len(self.stack.layers))
        check(isinstance(self.links, tuple) and len(self.links) == len(self.guids) and all(isinstance(x, str) and x.split('::')[-1] in ('NotFromParent', 'UnlinkedFromParent') for x in self.links), 'Parent-linked layer reconciliation unsupported')


def validate_guids(guids, count):
    check(isinstance(guids, tuple) and len(guids) == count and all(isinstance(x, UUID) and x.int for x in guids) and len(set(guids)) == count, "Invalid layer GUIDs")


def fields(reader, names):
    records = read_records(reader, names)
    check(all(p.index == 0 for p in records), 'Indexed layer properties unsupported')
    return {p.name: p for p in records}


def struct_fields(record, names, subtype):
    check(record.kind == 'StructProperty' and record.parameters == (subtype,), 'Unexpected layer struct type')
    r = Reader(record.data)
    out = fields(r, names)
    check(r.pos == len(r.data), 'Unexpected layer struct tail')
    return out


def array_reader(record, kind):
    check(record.kind == 'ArrayProperty' and record.parameters == (kind,), 'Invalid layer array type: '+record.name)
    r = Reader(record.data)
    return r, r.count(32)


def struct_array_reader(record, names, subtype):
    r, count = array_reader(record, 'StructProperty')
    check(r.name(names) == record.name and r.name(names) == 'StructProperty', 'Invalid layer array inner tag')
    size = r.unpack('q')[0]
    check(r.name(names) == subtype, 'Invalid layer array element class')
    r.take(16)
    flag = r.take(1)[0]
    check(flag in (0, 1), 'Invalid layer array GUID flag')
    if flag:
        r.take(16)
    check(size == len(r.data)-r.pos, 'Invalid layer array extent')
    return r, count


def end(r):
    check(r.pos == len(r.data), 'Unexpected layer array tail')


def references(record, table, kinds):
    r, count = array_reader(record, 'ObjectProperty')
    refs = []
    for _ in range(count):
        index = r.i()
        if index == 0:
            refs.append(None)
            continue
        ref = table.reference(index)
        package = table.package(index)
        check(isinstance(ref, ImportRecord) and ref.kind in kinds and package, 'Invalid layer function reference')
        refs.append(package)
    end(r)
    return tuple(refs)


def stack_fields(p, table):
    check({'Layers', 'Blends', 'LayerStates'} <= set(p), 'Missing layer arrays')
    layers = references(p['Layers'], table, ('MaterialFunctionMaterialLayer', 'MaterialFunction'))
    blends = references(p['Blends'], table, ('MaterialFunctionMaterialLayerBlend', 'MaterialFunction'))
    r, count = array_reader(p['LayerStates'], 'BoolProperty')
    raw = r.take(count)
    end(r)
    check(all(v in (0, 1) for v in raw), 'Invalid serialized layer state')
    return LayerStack(layers, blends, tuple(map(bool, raw)))


def decode_stack(record, table):
    p = struct_fields(record, table.names, 'MaterialLayersFunctions')
    return stack_fields(p, table)


def name_value(record, names):
    check(record.kind in ('NameProperty', 'ByteProperty', 'EnumProperty') and len(record.data) == 8, 'Invalid layer name')
    return Reader(record.data).name(names)


def decode_override(p, table):
    """Return None (absent), False (disabled), or immutable detached snapshot."""
    names = table.names
    containers = [p]
    for key in ('StaticParameters', 'StaticParametersRuntime'):
        if key in p:
            containers.append(struct_fields(p[key], names, 'StaticParameterSet' if key == 'StaticParameters' else 'StaticParameterSetRuntimeData'))
    arrays = [c['MaterialLayersParameters'] for c in containers if 'MaterialLayersParameters' in c]
    if not arrays:
        return None
    check(len(arrays) == 1, 'Multiple layer override arrays unsupported')
    r, count = struct_array_reader(arrays[0], names, 'StaticMaterialLayersParameter')
    if count == 0:
        end(r)
        return None
    check(count == 1, 'Multiple layer overrides unsupported')
    rec = fields(r, names)
    end(r)
    flag = rec.get('bOverride')
    check(flag is None or flag.kind == 'BoolProperty', 'Invalid layer override flag')
    if flag is None or not flag.boolean:
        return False
    check({'ParameterInfo', 'Value'} <= set(rec), 'Missing layer override fields')
    info = struct_fields(rec['ParameterInfo'], names, 'MaterialParameterInfo')
    check('Name' in info, 'Missing layer parameter name')
    if 'Association' in info:
        a = info['Association']
        check((a.kind == 'ByteProperty' and a.data == b'\x02') or (len(a.data) == 8 and name_value(a, names) == 'GlobalParameter'), 'Invalid layer override association')
    if 'Index' in info:
        i = info['Index']
        check(i.kind == 'IntProperty' and i.data == b'\xff'*4, 'Invalid layer override index')
    value = struct_fields(rec['Value'], names, 'MaterialLayersFunctions')
    check({'LayerGuids', 'LayerLinkStates'} <= set(value), 'Missing detached layer identity')
    check(not ({'DeletedParentLayerGuids'} & set(value)), 'Parent deletion reconciliation unsupported')
    stack = stack_fields(value, table)
    r, count = struct_array_reader(value['LayerGuids'], names, 'Guid')
    guids = tuple(UUID(bytes_le=r.take(16)) for _ in range(count))
    end(r)
    r, count = array_reader(value['LayerLinkStates'], 'ByteProperty')
    links = tuple(r.name(names) for _ in range(count))
    end(r)
    return DetachedSnapshot(name_value(info['Name'], names), stack, guids, links)


def package_fields(path, kind, name):
    meta, raw, table = read_package(path)
    check(meta.get('ue4') == 522 and meta.get('ue5') is None and meta.get('licensee') == 0, 'Expected UE4.27 layer package')
    matches = [e for e in table.exports if e.kind == kind and e.name == name]
    check(len(matches) == 1, 'Ambiguous layer export identity')
    e = matches[0]
    return fields(Reader(raw[e.offset:e.offset+e.size]), table.names), table


def read_stack(path, name):
    p, table = package_fields(path, 'MaterialExpressionMaterialAttributeLayers', name)
    check('DefaultLayers' in p, 'Missing DefaultLayers')
    return decode_stack(p['DefaultLayers'], table)


def read_override(path, name):
    p, table = package_fields(path, 'MaterialInstanceConstant', name)
    return decode_override(p, table)
