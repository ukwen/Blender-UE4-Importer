"""Read static actor placement records from validated classic editor packages.

The supported profile is derived from original Western Frontier 508 fixtures,
using the typed package and classic property interfaces. No inherited importer
modules are used. Native Blueprint execution and arbitrary component trees are
not part of this profile.
"""
from dataclasses import dataclass
import math
import struct

from package_records import read_package, ImportRecord, ExportRecord
from skeleton_native import Reader
from ue4_property_records import read_records


@dataclass(frozen=True, slots=True)
class Placement:
    actor: str
    label: str
    root_index: int
    parent_index: int
    parent_name: str
    package: str
    location: tuple
    rotation: tuple
    scale: tuple
    override_names: tuple
    override_packages: tuple


def require(condition, message):
    if not condition:
        raise ValueError(message)


def properties(raw, table, entry):
    return {p.name: p for p in read_records(Reader(raw[entry.offset:entry.offset + entry.size]), table.names)
            if p.index == 0}


def object_index(props, name, default=0):
    if name not in props:
        return default
    p = props[name]
    require(p.kind == 'ObjectProperty' and len(p.data) == 4, 'Invalid object property: ' + name)
    return struct.unpack('<i', p.data)[0]


def string_value(props, name, default):
    if name not in props:
        return default
    p = props[name]
    require(p.kind == 'StrProperty', 'Invalid string property: ' + name)
    r = Reader(p.data)
    n = r.i()
    require(abs(n) <= 65536, 'String exceeds limit')
    size = n if n >= 0 else -2*n
    data = r.take(size)
    end = bytes(1 if n >= 0 else 2)
    require(r.pos == len(p.data) and (not n or data.endswith(end)), 'Invalid string extent')
    return data[:-len(end)].decode('utf-8' if n >= 0 else 'utf-16-le') if n else ''


def triple(props, name, kind, default):
    if name not in props:
        return default
    p = props[name]
    require(p.kind == 'StructProperty' and p.parameters == (kind,) and len(p.data) == 12,
            'Unsupported transform field: ' + name)
    v = struct.unpack('<3f', p.data)
    require(all(math.isfinite(x) for x in v), 'Nonfinite transform: ' + name)
    return v


def overrides(props, table):
    p = props.get('OverrideMaterials')
    if p is None:
        return (), ()
    require(p.kind == 'ArrayProperty' and p.parameters == ('ObjectProperty',), 'Invalid material override array')
    r = Reader(p.data)
    count = r.count(4096)
    names, packages = [], []
    for _ in range(count):
        index = r.i()
        ref = table.reference(index)
        names.append(ref.name if ref else '')
        # Local exported material objects have no external package identity.
        packages.append(table.package(index) if isinstance(ref, ImportRecord) else '')
    require(r.pos == len(p.data), 'Unexpected material override trailer')
    return tuple(names), tuple(packages)


def read_placement(raw, table, index, actor):
    ap = properties(raw, table, actor)
    root_index = object_index(ap, 'RootComponent')
    component_index = object_index(ap, 'StaticMeshComponent')
    root = table.reference(root_index)
    require(root_index == component_index and isinstance(root, ExportRecord) and root.outer == index
            and root.kind == 'StaticMeshComponent', 'Unsupported root/mesh component association')
    cp = properties(raw, table, root)
    mesh_index = object_index(cp, 'StaticMesh')
    mesh = table.reference(mesh_index)
    require(isinstance(mesh, ImportRecord) and mesh.kind == 'StaticMesh', 'Missing external mesh reference')
    package = table.package(mesh_index)
    require(bool(package), 'Unresolved mesh package')
    parent_index = object_index(cp, 'AttachParent')
    parent = table.reference(parent_index)
    require(not parent_index or isinstance(parent, ExportRecord), 'Unsupported external attach parent')
    require(parent_index != root_index, 'Self-parenting component')
    names, packages = overrides(cp, table)
    return Placement(actor.name, string_value(ap, 'ActorLabel', actor.name), root_index, parent_index,
                     parent.name if parent else '', package,
                     triple(cp, 'RelativeLocation', 'Vector', (0., 0., 0.)),
                     triple(cp, 'RelativeRotation', 'Rotator', (0., 0., 0.)),
                     triple(cp, 'RelativeScale3D', 'Vector', (1., 1., 1.)), names, packages)


def inspect_layout(path):
    meta, raw, table = read_package(path)
    require(meta['ue4'] == 508 and meta['ue5'] is None and meta['licensee'] == 0,
            'Unsupported classic layout profile')
    actors, skipped = [], []
    for index, actor in enumerate(table.exports, 1):
        if actor.kind != 'StaticMeshActor':
            continue
        try:
            actors.append(read_placement(raw, table, index, actor))
        except (ValueError, UnicodeError, struct.error) as exc:
            skipped.append((actor.name, str(exc)))
    return actors, skipped


def parent_links(actors):
    """Validate ancestry before building it; retain unresolved IDs as diagnostics."""
    roots = {a.root_index: a for a in actors}
    if len(roots) != len(actors):
        raise ValueError('Duplicate root identity')
    links, unresolved = {}, set()
    for actor in actors:
        if not actor.parent_index:
            continue
        cursor, seen = actor.parent_index, {actor.root_index}
        while cursor in roots and cursor not in seen:
            seen.add(cursor)
            cursor = roots[cursor].parent_index
        if cursor in seen or actor.parent_index not in roots:
            unresolved.add(actor.root_index)
        else:
            links[actor.root_index] = actor.parent_index
    return links, unresolved
