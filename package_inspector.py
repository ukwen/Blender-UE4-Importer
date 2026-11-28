"""Read-only package inspection, independent of Blender or Unreal Engine.
Header layout reference: UAssetAPI, UAsset.cs ReadHeader (MIT, atenfyr).
Only versioned optimized legacy -7/-8/-9 package tables are decoded.
"""
import argparse
import json
import struct
from pathlib import Path

MAGIC = 0x9E2A83C1


def inspect_package(path, *, include_bulk_522=False):
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
            custom_versions = read(count*20)
            # FFortniteMainBranchObjectVersion controls FSoftObjectPath subpath encoding.
            fortnite_guid=struct.pack("<4I",0x601D1886,0xAC644F84,0xAA16D3DE,0x0DEAC7D6)
            fortnite_versions=[struct.unpack_from("<i",custom_versions,i+16)[0] for i in range(0,len(custom_versions),20) if custom_versions[i:i+16]==fortnite_guid]
            if len(fortnite_versions)>1: raise ValueError("duplicate Fortnite custom version")
            result["fortnite_main_version"]=fortnite_versions[0] if fortnite_versions else None
            if ue5 is None or ue5 < 1016: header_end = i32()
            if not f.tell() <= header_end <= size: raise ValueError('invalid header end')
            package_name=string(); flags = u32()
            if ue5 is not None and ue5>=1016:result["package_name"]=package_name
            names_count, names_offset = i32(), i32()
            soft_object_count, soft_object_offset = (i32(), i32()) if ue5 is not None and ue5 >= 1008 else (0, 0)
            if ue4 >= 516 and not flags & 0x80000000: string()
            read(8) # gatherable text count and offset
            export_count, export_offset = i32(), i32()
            import_count, import_offset = i32(), i32()
            # Explicit tested summary layouts: 1012 and 1018 (UE5.7).
            extra = {}
            if ue5 is not None and 1012 <= ue5 <= 1018:
                if ue5>=1015:
                    cell_export_count,cell_export_offset,cell_import_count,cell_import_offset=(i32() for _ in range(4))
                    extra.update(cell_export_count=cell_export_count,cell_export_offset=cell_export_offset,cell_import_count=cell_import_count,cell_import_offset=cell_import_offset)
                if ue5>=1014: extra["metadata_offset"]=i32()
                depends_offset, soft_package_count, soft_package_offset, searchable_offset, thumbnail_offset = (i32() for _ in range(5))
                extra.update(soft_object_count=soft_object_count, soft_object_offset=soft_object_offset,
                             depends_offset=depends_offset, soft_package_count=soft_package_count,
                             soft_package_offset=soft_package_offset, searchable_offset=searchable_offset,
                             thumbnail_offset=thumbnail_offset)
                if ue5==1018:
                    hierarchy_count,hierarchy_offset=i32(),i32()
                    extra.update(import_hierarchy_count=hierarchy_count,import_hierarchy_offset=hierarchy_offset)
            if ue5 is None and ue4 in (508, 518, 522):
                extra.update(depends_offset=i32(), soft_package_count=i32(), soft_package_offset=i32())
                if ue4 >= 518: extra['searchable_offset'] = i32()
                extra['thumbnail_offset'] = i32()
                if ue4 == 508 or (ue4 == 522 and include_bulk_522 and not flags & 0x80000000):
                    read(16)  # package GUID
                    if ue4 == 522: read(16)  # persistent editor package GUID
                    generations = i32()
                    if not 0 <= generations <= 10000: raise ValueError('invalid generation count')
                    read(generations * 8)
                    for _ in range(2):  # saved and compatible engine versions
                        read(10); string()
                    compression, chunks = u32(), i32()
                    if compression or chunks: raise ValueError('compressed classic package unsupported')
                    read(4)  # package source
                    additional = i32()
                    if not 0 <= additional <= 10000: raise ValueError('invalid additional package count')
                    for _ in range(additional): string()
                    extra['asset_registry_offset'] = i32()
                    extra['bulk_data_offset'] = struct.unpack('<q', read(8))[0]
                    if not 0 <= extra['bulk_data_offset'] <= size: raise ValueError('invalid bulk data offset')
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
                          names=names, **extra)
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
