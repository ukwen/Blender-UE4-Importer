"""Atomic explicit map-set import. Independent maps retain local world coordinates."""
import json
from pathlib import Path


def map_redirector(path):
    """Identify a bounded original UE5 map alias, not a World export.

    Never follow an alias automatically; unknown or malformed files remain
    discoverable for diagnosis. Avoid reading large map payloads during scans.
    """
    import struct
    from ue5_blueprint import read_tables
    try:
        if Path(path).stat().st_size>1024*1024:return None
        meta,raw,imports,exports,ref,package=read_tables(path)
        if meta['ue5'] not in (1016,1017) or len(exports)!=1:return None
        e=exports[0];cls=ref(e['class_index'])
        if e['outer'] or e['kind']!='ObjectRedirector' or e['class_index']>=0 or cls['kind']!='Class' or cls['class_package']!='/Script/CoreUObject':return None
        if ref(cls['outer'])['name']!='/Script/CoreUObject':return None
        payload=raw[e['offset']:e['offset']+e['size']]
        if e['script_start']!=0 or e['script_end']!=9 or len(payload)!=17 or payload[:13]!=bytes(13):return None
        idx=struct.unpack_from('<i',payload,13)[0]
        if idx>=0:return None
        target=ref(idx);dest=package(idx)
        if target['kind']!='World' or target['class_package']!='/Script/Engine' or not dest.startswith('/Game/') or target['name']!=dest.rsplit('/',1)[-1]:return None
        return dest
    except Exception:
        return None


def validate_selection(project, paths):
    content=(Path(project).resolve().parent/'Content').resolve()
    selected=[Path(p).resolve() for p in paths]
    if not selected or len(selected)>128 or len(set(selected))!=len(selected):raise ValueError('Select 1–128 distinct saved levels')
    if any(p.suffix!='.umap' or not p.is_file() or not p.is_relative_to(content) or any(s in ('__ExternalActors__','__ExternalObjects__') for s in p.relative_to(content).parts) for p in selected):raise ValueError('Invalid saved level selection')
    return selected


def reconstruct(project, paths, partial=False, preview_scale=1., strict=False, profile='4.27'):
    """Synchronous callers use the same cancellable transaction as the modal UI."""
    iterator=iter_reconstruct(project,paths,partial,preview_scale,strict,profile)
    try:
        while True:next(iterator)
    except StopIteration as done:return done.value
    finally:iterator.close()


def iter_reconstruct(project, paths, partial=False, preview_scale=1., strict=False, profile='4.27',cache_budget=None):
    """Yield after each completed map; closing before commit rolls back the entire set.

    Native builders remain synchronous; cancellation is between maps, not mid-map.
    Caller must prevent other edits while the generator owns the scene.
    """
    import bpy
    from package_inspector import inspect_package
    from legacy_full_scene import supported
    from project_session import new_ids,rollback_new
    from ue5_blueprint import read_tables
    from ue5_full_scene import reconstruct as modern
    from legacy_full_scene import reconstruct as legacy
    paths=validate_selection(project,paths);scene=bpy.context.scene
    # Validate before any mutation, including unsupported map profiles.
    builders=[]
    for p in paths:
        meta=inspect_package(p)
        if supported(meta):builders.append(legacy)
        else:
            m,_,_,ex,_,_=read_tables(p)
            if m['ue5'] not in (1016,1017) or not any(e['kind']=='World' and not e['outer'] for e in ex):raise ValueError('Unsupported saved map: '+str(p))
            builders.append(modern)
    keys=('UE_full_scene_source','UE_source_map_path','UE_lighting_source','UE_camera_source')
    if any(c.get(k) in {str(p) for p in paths} for c in scene.collection.children_recursive for k in keys):raise ValueError('Selected level already imported; remove prior import explicitly')
    before=set(new_ids());camera=scene.camera;world=scene.world
    try:
        group=bpy.data.collections.new('UE Project — '+Path(project).stem);scene.collection.children.link(group)
        rows=[]
        for p,builder in zip(paths,builders):
            args=(str(p),partial,preview_scale,strict)
            if builder is legacy:root,report=builder(*args,profile)
            elif cache_budget is None:root,report=builder(*args)
            else:
                from import_workflow import table_scope
                with table_scope(cache_budget):root,report=builder(*args)
            group.children.link(root);scene.collection.children.unlink(root)
            root.hide_render=bool(rows);root.hide_viewport=bool(rows)
            rows.append(dict(source=str(p),collection=root.name,counts=report['counts'],report=root['UE_report']))
            yield dict(completed=len(rows),total=len(paths),source=str(p))
        if scene.camera!=camera or scene.world!=world:raise ValueError('Unexpected camera or world change')
        report=dict(project=str(Path(project).resolve()),levels=rows,active_source=rows[0]['source'],scope='Explicit independent saved level set; only first level visible. No native streaming placement or runtime composition. Existing scene camera/world unchanged.')
        t=bpy.data.texts.new(group.name+' - project transfer.json');t.write(json.dumps(report,indent=2));group['UE_project_level_set']=str(Path(project).resolve());group['UE_report']=t.name;group['UE_active_level']=rows[0]['source']
        return group,report
    except BaseException:
        scene.camera=camera;scene.world=world;rollback_new(before);raise


def activate(scene,source):
    groups=[c for c in scene.collection.children_recursive if c.get('UE_project_level_set') and any(x.get('UE_full_scene_source')==source for x in c.children)]
    if len(groups)!=1:raise ValueError('Selected map must belong to exactly one imported project level set')
    group=groups[0];matches=[c for c in group.children if c.get('UE_full_scene_source')==source]
    if len(matches)!=1:raise ValueError('Ambiguous saved level')
    import bpy
    text=bpy.data.texts.get(group.get('UE_report',''))
    if text is None:raise ValueError('Project level-set report missing')
    report=json.loads(text.as_string());report['active_source']=source
    for c in group.children:
        if c.get('UE_full_scene_source'):
            c.hide_render=c!=matches[0];c.hide_viewport=c!=matches[0]
    group['UE_active_level']=source
    text.clear();text.write(json.dumps(report,indent=2))
    return matches[0]
