"""Bounded UE4.27 parameter records for the layer replay boundary.

Uses typed package tables and the classic tagged struct reader (MIT format
reference in third_party/UAssetAPI-LICENSE.txt). No inherited property objects.
Only explicit scalar, linear color, texture and static switch values are read.
"""
from dataclasses import dataclass
from uuid import UUID
from classic_material_graph import array, nested
from classic_material import scalar, linear_color, integer, boolean, object_index
from layer_records import check, name_value, package_fields
from package_records import ImportRecord

ARRAYS = {'ScalarParameterValues': ('scalar', 'ScalarParameterValue'),
          'VectorParameterValues': ('vector', 'VectorParameterValue'),
          'TextureParameterValues': ('texture', 'TextureParameterValue'),
          'StaticSwitchParameters': ('switch', 'StaticSwitchParameter'),
          'StaticSwitchParameterValues': ('switch', 'StaticSwitchParameter')}
SCOPES = ('LayerParameter', 'BlendParameter', 'GlobalParameter')
OTHER = {'StaticComponentMaskParameters', 'StaticComponentMaskParameterValues',
         'MaterialLayersParameters', 'TerrainLayerWeightParameters'}


@dataclass(frozen=True, slots=True)
class ParameterValue:
    kind: str
    name: str
    value: float | tuple | str | bool
    scope: str
    index: int
    guid: UUID | None

    def replay_record(self):
        return self.kind, self.name, self.value, self.scope, self.index


def identity(item, names):
    info = nested(item['ParameterInfo'], names, 'MaterialParameterInfo')
    check(set(info) == {'Name', 'Association', 'Index'}, 'Invalid parameter identity fields')
    check(info['Name'].kind == 'NameProperty', 'Invalid parameter name type')
    name = name_value(info['Name'], names)
    a = info['Association']
    if a.kind == 'ByteProperty' and len(a.data) == 1:
        check(a.data[0] < len(SCOPES), 'Invalid parameter association')
        scope = SCOPES[a.data[0]]
    else:
        scope = name_value(a, names).split('::')[-1]
    index = integer(info, 'Index')
    check(bool(name.strip()) and name != 'None' and scope in SCOPES and
          (index == -1 if scope == 'GlobalParameter' else 0 <= index < 32), 'Invalid parameter scope/index')
    return name, scope, index


def decode_parameters(p, table, layers_handled=False):
    """Return immutable records; malformed/unsupported values never become defaults."""
    names = table.names
    containers = [p]
    for key, subtype in (('StaticParameters', 'StaticParameterSet'),
                         ('StaticParametersRuntime', 'StaticParameterSetRuntimeData')):
        if key in p:
            inner = nested(p[key], names, subtype)
            check(set(inner) <= OTHER | {'StaticSwitchParameters', 'StaticSwitchParameterValues'}, 'Unsupported static parameter fields')
            containers.append(inner)
    seen, records = set(), []
    for container in containers:
        for field in OTHER & container.keys():
            if field == 'MaterialLayersParameters' and layers_handled:
                continue
            rec = container[field]
            check(rec.kind == 'ArrayProperty' and rec.data[:4] == bytes(4), 'Unsupported static/layer data: '+field)
        for field, (kind, subtype) in ARRAYS.items():
            if field not in container:
                continue
            for item in array(container[field], names, subtype):
                required = {'ParameterInfo'}
                allowed = required | {'ExpressionGUID'} | ({'bOverride', 'Value', 'ParameterValue'} if kind == 'switch' else {'ParameterValue'})
                if kind == 'scalar': allowed.add('AtlasData')
                check(required <= set(item) <= allowed, 'Unsupported parameter fields: '+field)
                name, scope, index = identity(item, names)
                key = kind, scope, index, name.casefold()
                check(key not in seen, 'Duplicate parameter identity: '+name)
                seen.add(key)
                g = item.get('ExpressionGUID')
                if g is not None:
                    check(g.kind == 'StructProperty' and g.parameters == ('Guid',) and len(g.data) == 16, 'Invalid expression GUID')
                guid = UUID(bytes_le=g.data) if g else None
                if kind == 'switch':
                    check('bOverride' in item, 'Missing static switch override flag')
                    flag = boolean(item, 'bOverride')
                    values = {'Value', 'ParameterValue'} & item.keys()
                    check(len(values) == 1, 'Missing or ambiguous switch value')
                    value = boolean(item, next(iter(values)))
                    if not flag: continue
                else:
                    check('ParameterValue' in item, 'Missing parameter value')
                    if kind == 'scalar':
                        if 'AtlasData' in item:
                            atlas = nested(item['AtlasData'], names, 'ScalarParameterAtlasInstanceData')
                            none = names.index('None').to_bytes(4, 'little') + bytes(8)
                            check(set(atlas) == {'bIsUsedAsAtlasPosition', 'Curve', 'Atlas'} and not boolean(atlas, 'bIsUsedAsAtlasPosition') and all(atlas[k].kind == 'SoftObjectProperty' and atlas[k].data == none for k in ('Curve', 'Atlas')), 'Active scalar atlas unsupported')
                        value = scalar(item, 'ParameterValue')
                    elif kind == 'vector': value = linear_color(item, 'ParameterValue')
                    else:
                        ref = object_index(item, 'ParameterValue')
                        entry = table.reference(ref)
                        value = table.package(ref)
                        check(isinstance(entry, ImportRecord) and entry.kind == 'Texture2D' and bool(value), 'Invalid texture parameter reference')
                records.append(ParameterValue(kind, name, value, scope, index, guid))
    return tuple(records)


def read_parameters(path, name, layers_handled=False):
    p, table = package_fields(path, 'MaterialInstanceConstant', name)
    return decode_parameters(p, table, layers_handled)
