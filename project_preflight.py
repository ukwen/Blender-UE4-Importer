"""Read-only dependency inventory. Package table references are conservative, not runtime usage."""
from pathlib import Path
from collections import Counter


def content_paths(content):
    content=Path(content).resolve()
    paths=sorted(p for p in content.rglob('*') if p.is_file() and p.suffix.lower() in ('.uasset','.umap') and p.resolve().is_relative_to(content) and not {'__ExternalActors__','__ExternalObjects__'}.intersection(p.relative_to(content).parts))
    if len(paths)>10000: raise ValueError('Preflight limit: 10000 packages')
    return paths


def package_id(path,content):
    return '/Game/'+Path(path).relative_to(content).with_suffix('').as_posix()


def soft_refs_ue4(asset):
    """Bounded package-summary soft reference table, for tested object versions."""
    s=asset.summary; desc=s.soft_pkg_refs_desc; n,o=desc.count,desc.offset
    if not n: return []
    if not 0<n<=100000 or not 0<o<s.header_size: raise ValueError('Invalid soft reference table')
    if s.version_ue4 not in (508,522): raise NotImplementedError('Unverified soft reference serialization')
    asset.f.Seek(o); refs=[]
    for _ in range(n):
        if s.version_ue4==508:
            if asset.f.Position()+4>s.header_size: raise ValueError('Truncated soft reference')
            length=asset.f.ReadInt32(); size=length if length>=0 else -2*length
            if not 0<size<=65536 or asset.f.Position()+size>s.header_size: raise ValueError('Invalid soft reference string')
            raw=asset.f.ReadBytes(size); term=b'\0' if length>0 else b'\0\0'
            if not raw.endswith(term): raise ValueError('Unterminated soft reference')
            ref=raw[:-len(term)].decode('utf-8' if length>0 else 'utf-16-le')
        else:
            if asset.f.Position()+8>s.header_size: raise ValueError('Truncated soft reference name')
            idx,number=asset.f.ReadStruct('ii',8)
            if not 0<=idx<len(asset.names) or number!=0: raise ValueError('Invalid soft reference name')
            ref=asset.names[idx]
        if ref=='None': continue
        if not ref.startswith('/') or '.' in ref or '\\' in ref: raise ValueError('Unsupported soft package path: '+ref)
        refs.append(ref)
    return sorted(set(refs))


def read_record(path,project):
    from package_inspector import inspect_package
    meta=inspect_package(path)
    record={'format':meta.get('status'),'ue4':meta.get('ue4'),'ue5':meta.get('ue5'),'sidecars':meta['sidecars'],'classes':[],'references':[],'coverage':'unknown','soft_references':[],'soft_coverage':'unknown'}
    if meta.get('legacy')==-8 and meta.get('status')=='unversioned_requires_context' and '.uexp' in meta['sidecars']:
        try:
            from ue5_cooked_geometry import package
            cls,_,_,imports,_=package(path)
            refs={i[3] for i in imports if i[1]=='Package' and i[3].startswith('/') and not i[3].startswith('/Script/')}
            record.update(classes=[cls],references=sorted(refs),coverage='ue5_cooked_import_table',format='unversioned_ue5_split_profile')
        except (ValueError,OSError,NotImplementedError) as exc: record['detail']=str(exc)
        return record
    if meta.get('status')!='tables_inspected' or meta['sidecars']: return record
    try:
        if meta['ue5'] is None and meta['legacy']==-7:
            from uasset import UAsset
            with UAsset(str(path),False,project) as a:
                classes={e.export_class_type for e in a.exports if not e.outer_index}
                refs={i.object_name for i in a.imports if i.class_name=='Package' and i.object_name.startswith('/') and not i.object_name.startswith('/Script/')}
                try: record.update(soft_references=soft_refs_ue4(a),soft_coverage='summary_table')
                except Exception as exc: record['soft_detail']=str(exc)
        elif meta['ue5']==1012:
            from ue5_blueprint import read_tables
            _,_,imports,exports,_,_=read_tables(path)
            classes={e['kind'] for e in exports if not e['outer']}
            refs={i['name'] for i in imports if i['kind']=='Package' and i['name'].startswith('/') and not i['name'].startswith('/Script/')}
            refs.update(i['package_name'] for i in imports if i['package_name'].startswith('/') and not i['package_name'].startswith('/Script/'))
            try:
                from ue5_dependencies import read_dependencies
                deps=read_dependencies(path)
                record.update(soft_references=deps['soft_references'],soft_coverage='ue5_1012_summary_tables',
                              soft_object_paths=deps['soft_object_paths'],export_dependency_rows=len(deps['export_dependency_rows']),
                              export_dependency_indices=sum(map(len,deps['export_dependency_rows'])))
            except Exception as exc: record['soft_detail']=str(exc)
        else: return record
        record.update(classes=sorted(classes),references=sorted(refs),coverage='import_table')
    except Exception as exc: record['detail']=f'{type(exc).__name__}: {exc}'
    return record


def preflight(descriptor,scope='ALL_MAPS',selected=None,subfolder='',job_filter='',selected_packages=None):
    from uasset import UProject
    from uproject_browser import discover_maps
    descriptor,engine,maps=discover_maps(descriptor)
    content=(Path(descriptor).parent/'Content').resolve(); project=UProject(descriptor)
    folder=(content/subfolder).resolve()
    if not folder.is_relative_to(content) or not folder.is_dir(): raise ValueError('Select a folder inside project Content')
    paths=content_paths(content); index={}; records={}
    for p in paths:
        key=package_id(p,content)
        if key in index: raise ValueError('Duplicate package identity: '+key)
        index[key]=p
    for key,p in index.items():
        records[key]=read_record(p,project)
    if scope=='ALL_MAPS': seeds=[package_id(p,content) for _,p in maps]
    elif scope in ('SELECTED_MAP','MAP_GEOMETRY'):
        if selected not in {p for _,p in maps}: raise ValueError('Selected map is missing; scan again')
        seeds=[package_id(selected,content)]
    elif scope=='GEOMETRY':
        seeds=[k for k,p in index.items() if p.is_relative_to(folder) and p.suffix.lower()=='.uasset' and (set(records[k]['classes'])&{'StaticMesh','SkeletalMesh'} or records[k]['coverage']=='unknown')]
    else: raise ValueError('Invalid batch scope')
    root_seeds=list(seeds)
    if scope=='MAP_GEOMETRY':
        # Only geometry packages reachable through the selected level's known
        # dependency graph. Unknown classes remain reported, never imported blindly.
        reachable=set(); pending=list(seeds)
        while pending:
            key=pending.pop()
            if key in reachable: continue
            reachable.add(key)
            pending.extend(ref for ref in set(records[key]['references'])|set(records[key]['soft_references']) if ref in index and ref not in reachable)
        seeds=sorted(k for k in reachable if index[k].suffix.lower()=='.uasset' and set(records[k]['classes'])&{'StaticMesh','SkeletalMesh'})
    seeds=[k for k in seeds if job_filter.casefold() in k.casefold()]
    if selected_packages is not None:
        if not set(selected_packages)<=set(seeds): raise ValueError("Selection is stale; refresh the job list")
        seeds=[k for k in seeds if k in selected_packages]
    visited=set(); pending=list(seeds); edges={}
    while pending:
        k=pending.pop()
        if k in visited: continue
        visited.add(k)
        for ref in sorted(set(records[k]['references']) | set(records[k]['soft_references'])):
            if ref==k: continue
            if ref in index: status='available'; pending.append(ref)
            elif ref.startswith('/Game/'): status='missing_game'
            elif ref.startswith('/Engine/'):
                try: status='external_engine_present' if Path(project.resolve_package(ref)).is_file() else 'missing_engine'
                except (ValueError,OSError): status='missing_engine'
            else: status='unsupported_mount'
            edge=edges.setdefault(ref,{'status':status,'referenced_by':[],'soft_referenced_by':[],'hard_referenced_by':[]})
            edge['referenced_by'].append(k)
            if ref in records[k]['references']: edge['hard_referenced_by'].append(k)
            if ref in records[k]['soft_references']: edge['soft_referenced_by'].append(k)
    return dict(project=descriptor,engine=engine,scope=scope,folder=subfolder,job_filter=job_filter,seeds=sorted(seeds),source_map=root_seeds[0] if scope=='MAP_GEOMETRY' else None,jobs=[str(index[k]) for k in sorted(seeds)],inventory_count=len(index),closure_count=len(visited),coverage_counts=dict(Counter(records[k]['coverage'] for k in visited)),soft_coverage_counts=dict(Counter(records[k]['soft_coverage'] for k in visited)),dependency_counts=dict(Counter(x['status'] for x in edges.values())),dependencies=edges,records={k:records[k] for k in sorted(visited)},note='Conservative package import-table and supported UE4 and UE5 1012 soft-summary references; does not prove required runtime dependencies. Supported UE5.0 split import tables are inspected; other split/unsupported tables are unknown. Engine packages are not recursively inspected.')
