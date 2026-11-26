"""Bounded UE5 1012 dependency tables, not runtime Blueprint analysis.

Layout verified against the supplied UAssetAPI ReadHeader/FSoftObjectPath
reference and original tagged Goblin editor packages. Other versions refuse.
"""
from skeleton_native import Reader
from ue5_blueprint import read_tables, require


def package_path(name):
    if name == 'None': return ''
    require(name.startswith('/') and len(name) <= 4096 and
            all(p and p not in ('.', '..') and not any(c in p for c in '.\\:\0') for p in name[1:].split('/')),
            'Invalid package path')
    return name


def read_dependencies(path):
    meta, raw, imports, exports, ref, package = read_tables(path)
    names = meta['names']; header = meta['header_end']
    offsets = {header, *(meta[k] for k in ('name_offset','import_offset','export_offset','soft_object_offset',
              'soft_package_offset','depends_offset','searchable_offset','thumbnail_offset') if meta[k] > 0)}
    require(all(0 < o <= header for o in offsets), 'Dependency table offset outside header')

    def table(offset, count, minimum):
        require(0 <= count <= 100000, 'Dependency table count limit')
        if not count: return Reader(b'')
        require(0 < offset < header, 'Missing dependency table offset')
        end = min(o for o in offsets if o > offset)
        require(count * minimum <= end - offset, 'Dependency table extent exceeded')
        return Reader(raw[offset:end])

    def fstring(r):
        n = r.i()
        require(abs(n) <= 65536, 'Soft subpath string limit')
        if not n: return ''
        term = b'\0' if n > 0 else b'\0\0'
        data = r.take(n if n > 0 else -2*n)
        require(data.endswith(term), 'Unterminated soft subpath')
        return data[:-len(term)].decode('utf-8' if n > 0 else 'utf-16-le')

    n = meta['soft_package_count']; r = table(meta['soft_package_offset'],n,8)
    soft_packages = sorted({p for _ in range(n) if (p := package_path(r.name(names)))})
    n = meta['soft_object_count']; r = table(meta['soft_object_offset'],n,20)
    objects = []
    for _ in range(n):
        pkg, obj, sub = package_path(r.name(names)), r.name(names), fstring(r)
        require(len(obj)<=4096 and '\0' not in obj and '\0' not in sub, 'Invalid soft object identity')
        objects.append({'package':pkg,'object':obj,'subpath':sub})
    # Export DependsMap rows are arrays of signed FPackageIndex values.
    rows = []
    if meta['depends_offset']:
        r = table(meta['depends_offset'],len(exports),4)
        total = 0
        for _ in exports:
            count = r.count(100000); total += count
            require(total<=1000000, 'Dependency index limit')
            row = list(r.unpack(f'{count}i'))
            require(all(-len(imports)<=i<=len(exports) for i in row), 'Invalid dependency package index')
            rows.append(row)
    # Package import records may use an explicit package name or a plugin mount.
    hard = set()
    for i in imports:
        if i['kind']=='Package' and i['name'].startswith('/'):
            hard.add(package_path(i['name']))
        if i['package_name'].startswith('/'):
            hard.add(package_path(i['package_name']))
    return dict(hard_references=sorted(p for p in hard if not p.startswith('/Script/')),
                soft_references=sorted({p for p in soft_packages+ [x['package'] for x in objects] if p and not p.startswith('/Script/')}),
                soft_package_references=soft_packages, soft_object_paths=objects,
                export_dependency_rows=rows)
