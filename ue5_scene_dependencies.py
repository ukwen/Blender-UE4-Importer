"""Selected-level dependency closure and source qualification, not a render-fidelity guarantee."""
from collections import Counter, deque
from pathlib import Path


def package_file(project, package):
    """Resolve exact package mount and distinguish maps from assets, never guess a replacement."""
    asset = Path(project.resolve_package(package))
    level = asset.with_suffix('.umap')
    root = (Path(project.dir)/'Content' if package.startswith('/Game/') else Path(project.engine_dir)/'Content').resolve()
    candidates = [p.resolve() for p in (asset, level) if p.is_file()]
    if any(not p.is_relative_to(root) for p in candidates):
        raise ValueError('Package escapes content root: '+package)
    if len(candidates) > 1:
        raise ValueError('Ambiguous asset and map for '+package)
    return candidates[0] if candidates else None


def external_objects(content, level):
    root = content / '__ExternalObjects__' / level.relative_to(content).with_suffix('')
    if not root.resolve().is_relative_to(content): raise ValueError('External object folder escapes Content')
    return sorted(p for p in root.rglob('*.uasset') if p.is_file() and p.resolve().is_relative_to(root.resolve()))


def audit(project, level, limit=10000, reader=None):
    """Traverse known hard/soft package references, including map-owned actor/object packages.

    This is conservative source availability, not actual runtime use. No scene mutations.
    """
    from project_preflight import read_record
    from ue5_editor_scene import external_packages
    reader = reader or read_record
    content = (Path(project.dir)/'Content').resolve(); level = Path(level).resolve()
    if level.suffix != '.umap' or not level.is_relative_to(content) or not level.is_file():
        raise ValueError('Select an existing level inside project Content')
    if not 1 <= limit <= 10000: raise ValueError('Invalid dependency limit')
    root = '/Game/'+level.relative_to(content).with_suffix('').as_posix()
    records = {}; pending = deque([(root, level)]); queued = {root}; edges = {}; owners = {}
    def enqueue(key,path):
        if key in queued: return
        if len(queued) >= limit: raise ValueError('Scene dependency limit exceeded; audit incomplete')
        queued.add(key); pending.append((key,path))
    while pending:
        key,path = pending.popleft()
        try:
            record = reader(path,project)
        except Exception as exc:
            record = dict(coverage='unknown',soft_coverage='unknown',references=[],soft_references=[],detail=f'{type(exc).__name__}: {exc}')
        records[key] = dict(path=str(path),size_bytes=path.stat().st_size,**record)
        if path.suffix=='.umap' and path.is_relative_to(content):
            actor_root=content/'__ExternalActors__'/path.relative_to(content).with_suffix('')
            if not actor_root.resolve().is_relative_to(content): raise ValueError('External actor folder escapes Content')
            owned=external_packages(content,path)+external_objects(content,path)
            owners[key]=[]
            for p in owned:
                child='/Game/'+p.relative_to(content).with_suffix('').as_posix()
                owners[key].append(child); enqueue(child,p)
        hard=set(record.get('references',[])); soft=set(record.get('soft_references',[]))
        for target in sorted(hard|soft):
            if target==key or target.startswith('/Script/'): continue
            if target not in edges:
                if len(edges)>=limit: raise ValueError('Scene reference limit exceeded; audit incomplete')
                try:
                    p=package_file(project,target)
                    status='available' if p else 'missing_engine' if target.startswith('/Engine/') else 'missing_game'
                except FileNotFoundError: p=None;status='missing_engine' if target.startswith('/Engine/') else 'missing_game'
                except ValueError: p=None;status='unsupported_mount' if not target.startswith(('/Game/','/Engine/')) else 'invalid_or_ambiguous'
                edges[target]=dict(status=status,path=str(p) if p else None,hard=[],soft=[])
                if p: enqueue(target,p)
            if target in hard: edges[target]['hard'].append(key)
            if target in soft: edges[target]['soft'].append(key)
    unknown=sorted(k for k,v in records.items() if v.get('coverage')=='unknown' or v.get('soft_coverage')=='unknown')
    gaps={k:v for k,v in edges.items() if v['status']!='available'}
    return dict(level=root,source=str(level),engine_content=str(project.engine_dir) if project.engine_dir else None,
                scanned_packages=len(records),dependency_counts=dict(Counter(v['status'] for v in edges.values())),
                owned_packages=owners,unknown_tables=unknown,unresolved_hard=sum(bool(v['hard']) for v in gaps.values()),
                unresolved_soft_only=sum(not v['hard'] for v in gaps.values()),ready_for_strict_import=not gaps and not unknown,
                dependencies=edges,records=records,
                scope='Conservative known hard and soft package references, including map-owned external actor/object packages and available engine packages. Not runtime usage, actor or visual completeness. Unknown tables and missing mounts block strict mode.')
