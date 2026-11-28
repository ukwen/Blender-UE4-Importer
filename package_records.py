"""Immutable, bounded object-table reader for versioned monolithic editor packages.

Format reference: MIT-licensed UAssetAPI Import.cs, ExportTypes/Export.cs,
UnrealTypes/ObjectVersion.cs; see third_party/UAssetAPI-LICENSE.txt.
This module does not import uasset, Blender, or an Unreal runtime. Package
summary/name metadata is supplied by the existing MIT-reference inspector.
"""
from dataclasses import dataclass, replace
from pathlib import Path
import struct
from package_inspector import inspect_package

MAX_PACKAGE = 128 * 1024 * 1024
MAX_RECORDS = 100_000


def check(condition, reason):
    if not condition:
        raise ValueError(reason)


@dataclass(frozen=True, slots=True)
class ImportRecord:
    class_package: str
    kind: str
    outer: int
    name: str
    package_name: str
    optional: bool


@dataclass(frozen=True, slots=True)
class ExportRecord:
    name: str
    class_index: int
    super_index: int
    template: int
    outer: int
    offset: int
    size: int
    script_start: int | None
    script_end: int | None
    inherited: bool
    kind: str = ''


@dataclass(frozen=True, slots=True)
class PackageRecords:
    names: tuple[str, ...]
    imports: tuple[ImportRecord, ...]
    exports: tuple[ExportRecord, ...]

    def reference(self, index):
        check(type(index) is int and -len(self.imports) <= index <= len(self.exports), 'Invalid package index')
        if index < 0:
            return self.imports[~index]
        if index > 0:
            return self.exports[index - 1]
        return None

    def package(self, index, mounts=('/Game/', '/Engine/')):
        visited = set()
        while index:
            check(index not in visited, 'Package index cycle')
            visited.add(index)
            entry = self.reference(index)
            if isinstance(entry, ImportRecord) and entry.kind == 'Package' and entry.name.startswith(mounts):
                return entry.name
            index = entry.outer
        return ''


def decode_records(meta, raw):
    """Decode exact supported fixed-stride maps; never infer layout by engine label."""
    version = meta.get('ue5')
    classic = version is None and meta.get('ue4') == 508
    check(meta.get('status') == 'tables_inspected' and (classic or meta['ue4'] == 522) and
          (version is None or version == 1004 or 1012 <= version <= 1018) and
          not meta['sidecars'] and not meta['flags'] & 0x80002000 and
          len(raw) == meta['size'] <= MAX_PACKAGE, 'Unsupported monolithic editor table profile')
    check(not meta.get('cell_export_count', 0) and not meta.get('cell_import_count', 0), 'Verse cell tables unsupported')
    names = tuple(meta['names']); ni, ne = meta['import_count'], meta['export_count']
    io, eo, header = meta['import_offset'], meta['export_offset'], meta['header_end']
    modern = version is not None and version >= 1012
    import_stride = 28 if classic else 36 if version is None else 40
    export_stride = 96 if classic else 104 if version is None else 112 if modern else 108
    check(0 < ni <= MAX_RECORDS and 0 < ne <= MAX_RECORDS and
          0 < io < eo < header <= len(raw) and io + ni * import_stride == eo and
          eo + ne * export_stride <= header, 'Invalid object table extents')
    # Known following table, where present, must not be consumed as object data.
    following = [meta[k] for k in ('depends_offset','soft_package_offset','searchable_offset','thumbnail_offset','metadata_offset','import_hierarchy_offset') if meta.get(k, 0) > eo]
    check(not following or eo + ne * export_stride <= min(following), 'Object table overlaps following table')

    def fname(at):
        index, number = struct.unpack_from('<ii', raw, at)
        check(0 <= index < len(names) and number >= 0, 'Invalid FName')
        return names[index] if number == 0 else f'{names[index]}_{number - 1}'

    def index_ok(value):
        return -ni <= value <= ne

    imports = []
    for at in range(io, eo, import_stride):
        outer = struct.unpack_from('<i', raw, at + 16)[0]
        optional = struct.unpack_from('<i', raw, at + 36)[0] if version is not None else 0
        check(index_ok(outer) and optional in (0, 1), 'Invalid import record')
        imports.append(ImportRecord(fname(at), fname(at+8), outer, fname(at+20), '' if classic else fname(at+28), bool(optional)))
    exports = []
    for at in range(eo, eo + ne * export_stride, export_stride):
        cls, base, template, outer = struct.unpack_from('<4i', raw, at)
        size, offset = struct.unpack_from('<ii' if classic else '<qq', raw, at+28)
        check(all(map(index_ok, (cls, base, template, outer))), 'Invalid export index')
        switches = struct.unpack_from('<3i', raw, at+(36 if classic else 44))
        inherited = struct.unpack_from('<i', raw, at+56)[0] if modern else 0
        more = struct.unpack_from('<3i' if version is not None else '<2i', raw, at+(68 if classic else 64 if modern else 76))
        check(all(x in (0, 1) for x in (*switches, inherited, *more)), 'Invalid export flags')
        check(header <= offset <= len(raw) and 0 <= size <= len(raw)-offset, 'Invalid export extent')
        start, end = struct.unpack_from('<qq', raw, at+96) if modern else (None, None)
        check(not modern or 0 <= start <= end <= size, 'Invalid script extent')
        exports.append(ExportRecord(fname(at+16), cls, base, template, outer, offset, size, start, end, bool(inherited)))
    spans = sorted((x.offset, x.offset+x.size) for x in exports if x.size)
    check(all(a[1] <= b[0] for a,b in zip(spans, spans[1:])), 'Overlapping export extents')
    records = PackageRecords(names, tuple(imports), tuple(exports))
    return replace(records, exports=tuple(replace(e, kind=records.reference(e.class_index).name if e.class_index else '') for e in exports))


def read_package(path):
    path = Path(path)
    check(path.stat().st_size <= MAX_PACKAGE, 'Package size limit')
    meta = inspect_package(path)
    with path.open('rb') as stream:
        raw = stream.read(MAX_PACKAGE + 1)
    return meta, raw, decode_records(meta, raw)


def compatibility_tables(path):
    """Temporary dictionary adapter for already validated reconstruction consumers."""
    meta, raw, records = read_package(path)
    imports = [{key:getattr(i,key) for key in ImportRecord.__slots__} for i in records.imports]
    exports = [{key:getattr(e,key) for key in ExportRecord.__slots__} for e in records.exports]
    def ref(index):
        records.reference(index)  # check without relying on Python negative indexing
        return imports[~index] if index < 0 else exports[index-1] if index else None
    return meta, raw, imports, exports, ref, records.package


def soft_references_522(meta, raw, records):
    """UE4 522 summary soft package names; strict unnumbered identities only."""
    check(meta['ue4'] == 522 and meta['ue5'] is None, 'Unsupported soft reference profile')
    count, offset = meta['soft_package_count'], meta['soft_package_offset']
    if not count:
        return []
    check(0 < count <= MAX_RECORDS and 0 < offset < meta['header_end'] and count*8 <= meta['header_end']-offset, 'Invalid soft table extent')
    refs = set()
    for at in range(offset, offset + count*8, 8):
        index, number = struct.unpack_from('<ii', raw, at)
        check(0 <= index < len(records.names) and number == 0, 'Invalid soft package name')
        name = records.names[index]
        if name == 'None':
            continue
        check(name.startswith('/') and all(p and p not in ('.','..') and not any(c in p for c in '.\\:\0') for p in name[1:].split('/')), 'Invalid soft package path')
        refs.add(name)
    return sorted(refs)


def read_editor522(path, limit=MAX_PACKAGE):
    """Read only the classic monolithic UE4.27 editor profile."""
    check(Path(path).stat().st_size <= limit, 'Editor package size limit')
    meta, raw, table = read_package(path)
    check(meta['legacy'] == -7 and meta['ue4'] == 522 and meta['ue5'] is None,
          'Expected UE4.27 editor package')
    return meta, raw, table


def root_export(table, kind):
    matches = [e for e in table.exports if not e.outer and e.kind == kind]
    check(len(matches) == 1, 'Expected one root ' + kind)
    return matches[0]


def classic_custom_versions(raw):
    """Versioned UE4 -7 optimized GUID table (GUID bytes remain in file order)."""
    check(len(raw) >= 24 and struct.unpack_from('<i', raw, 4)[0] == -7,
          'Unsupported classic custom version layout')
    count = struct.unpack_from('<i', raw, 20)[0]
    check(0 <= count <= 10000 and 24 + 20 * count <= len(raw), 'Invalid custom version extent')
    result = {}
    for pos in range(24, 24 + 20 * count, 20):
        guid = bytes(raw[pos:pos+16])
        check(guid not in result, 'Duplicate custom version GUID')
        result[guid] = struct.unpack_from('<i', raw, pos+16)[0]
    return result


def soft_references_508(meta, raw, records):
    """Classic FString soft-package table, separate from UE4.27 FName layout."""
    check(meta['ue4'] == 508 and meta['ue5'] is None, 'Expected classic profile')
    count, offset = meta['soft_package_count'], meta['soft_package_offset']
    if not count: return []
    check(0 < count <= MAX_RECORDS and 0 < offset < meta['header_end'], 'Invalid soft table')
    refs = set()
    for _ in range(count):
        check(offset + 4 <= meta['header_end'], 'Truncated soft name')
        n = struct.unpack_from('<i', raw, offset)[0]; offset += 4
        size = n if n > 0 else -2*n
        check(0 < size <= 65536 and offset+size <= meta['header_end'], 'Invalid soft name extent')
        data = raw[offset:offset+size]; offset += size
        term = bytes(1 if n > 0 else 2)
        check(data.endswith(term), 'Unterminated soft name')
        name = data[:-len(term)].decode('utf8' if n > 0 else 'utf-16-le')
        if name == 'None': continue
        check(name.startswith('/') and all(p and p not in ('.','..') and not any(ord(c)<32 or c in '.\\:' for c in p) for p in name[1:].split('/')), 'Invalid soft package path')
        refs.add(name)
    return sorted(refs)
