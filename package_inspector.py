"""Read-only package inspection, independent of Blender or Unreal Engine.
Header layout reference: UAssetAPI, UAsset.cs ReadHeader (MIT, atenfyr).
Only versioned optimized legacy -7/-8/-9 package tables are decoded.
"""
import argparse
import json
import struct
from pathlib import Path

MAGIC = 0x9E2A83C1


def inspect_package(path):
    path = Path(path)
    result = {'file': path.name, 'size': path.stat().st_size,
              'sidecars': [ext for ext in ('.uexp', '.ubulk', '.uptnl') if path.with_suffix(ext).is_file()]}
    try:
        with path.open('rb') as f:
            size = result['size']
            def read(n):
                if n < 0 or n > size - f.tell():
                    raise ValueError('truncated package')
                return f.read(n)
            def i32(): return struct.unpack('<i', read(4))[0]
            def u32(): return struct.unpack('<I', read(4))[0]
            def string():
                n = i32()
                if abs(n) > 1048576:
                    raise ValueError('oversized FString')
                raw = read(-2*n if n < 0 else n)
                if not n: return ''
                terminator = b'\0\0' if n < 0 else b'\0'
                if not raw.endswith(terminator): raise ValueError('unterminated FString')
                return raw[:-len(terminator)].decode('utf-16-le' if n < 0 else 'utf-8', errors='replace')
            magic = u32()
            if magic != MAGIC:
                result['status'] = 'unknown_signature'
                return result
            legacy = i32(); result['legacy'] = legacy
            if legacy not in (-7, -8, -9):
                result['status'] = 'unsupported_legacy'; return result
            i32()
            ue4 = i32(); ue5 = i32() if legacy <= -8 else None
            result.update(ue4=ue4, ue5=ue5, licensee=i32())
            if ue4 == 0 or (ue5 is not None and ue5 == 0):
                result['status'] = 'unversioned_requires_context'; return result
            if not (ue4 == 508 and ue5 is None or 516 <= ue4 <= 522) or (ue5 is not None and not 1000 <= ue5 <= 1018):
                result['status'] = 'unsupported_version'; return result
            if ue5 is not None and ue5 >= 1016:
                read(20); header_end = i32()
            count = i32()
            if not 0 <= count <= 10000: raise ValueError('invalid custom version count')
            read(count*20)
            if ue5 is None or ue5 < 1016: header_end = i32()
            if not f.tell() <= header_end <= size: raise ValueError('invalid header end')
            string(); flags = u32()
            names_count, names_offset = i32(), i32()
            if ue5 is not None and ue5 >= 1008: read(8)
            if ue4 >= 516 and not flags & 0x80000000: string()
            read(8) # gatherable text count and offset
            export_count, export_offset = i32(), i32()
            import_count, import_offset = i32(), i32()
            for n, o in ((names_count,names_offset),(export_count,export_offset),(import_count,import_offset)):
                if not 0 <= n <= 2000000 or (n and not f.tell() <= o < header_end):
                    raise ValueError('invalid package table')
            names = []
            if names_count:
                f.seek(names_offset)
                for _ in range(names_count):
                    name = string()
                    if name: read(4)
                    if f.tell() > header_end: raise ValueError('name table outside header')
                    names.append(name)
            result.update(status='tables_inspected', header_end=header_end, flags=flags,
                          name_count=names_count, import_count=import_count, export_count=export_count,
                          name_offset=names_offset, import_offset=import_offset, export_offset=export_offset,
                          names=names)
    except (ValueError, struct.error, OSError) as exc:
        result.update(status='invalid_or_truncated', error=str(exc))
    return result


def inspect_tree(root):
    root = Path(root).resolve()
    records = []
    for path in sorted(root.rglob('*')):
        if path.suffix.lower() in ('.uasset', '.umap') and path.is_file() and path.resolve().is_relative_to(root):
            item = inspect_package(path)
            item['file'] = path.relative_to(root).as_posix()
            item.pop('names', None) # keep project reports small; no asset name-table dump
            records.append(item)
    return records


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('root', type=Path)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.root.is_dir(): parser.error('root must be a directory')
    args.output.write_text(json.dumps(inspect_tree(args.root), indent=2), encoding='utf-8')
