"""Saved-scene batch recovery. Never overwrite a stale or incomplete owned collection."""
import hashlib
import json
import uuid
from pathlib import Path

SCHEMA=1
TAG='UE_batch_job'
OBJECT_TAG='UE_batch_owner'

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def hash_file(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()

def source_fingerprint(plan):
    """Conservative whole-project fingerprint, including supported sidecars."""
    from project_preflight import content_paths
    project=Path(plan['project']).resolve(); content=project.parent/'Content'
    files=[project]; packages=content_paths(content)
    for folder in (content/"__ExternalActors__",content/"__ExternalObjects__"):
        packages.extend(p for p in folder.rglob("*.uasset") if p.is_file() and p.resolve().is_relative_to(content.resolve()))
    for p in packages:
        files.append(p)
        files.extend(p.with_suffix(ext) for ext in ('.uexp','.ubulk','.uptnl') if p.with_suffix(ext).is_file())
    return digest([(str(p),hash_file(p)) for p in sorted(set(files))])

def job_fingerprint(plan,path,common,engine_hashes):
    """Scope-independent fingerprint of project bytes plus reachable known engine files."""
    from project_paths import ProjectPaths
    from project_preflight import package_id
    project=Path(plan['project']).resolve(); resolver=ProjectPaths(str(project))
    seed=package_id(path,project.parent/'Content'); pending=[seed];seen=set();external=[]
    while pending:
        package=pending.pop()
        if package in seen: continue
        seen.add(package)
        record=plan['records'].get(package,{})
        for ref in set(record.get('references',[]))|set(record.get('soft_references',[])):
            if ref in plan['records']: pending.append(ref)
            elif plan['dependencies'].get(ref,{}).get('status')=='external_engine_present':
                if ref not in engine_hashes:
                    p=Path(resolver.resolve_package(ref)); files=[p]+[p.with_suffix(ext) for ext in ('.uexp','.ubulk','.uptnl') if p.with_suffix(ext).is_file()]
                    engine_hashes[ref]=digest([(str(f),hash_file(f)) for f in files])
                external.append((ref,engine_hashes[ref]))
    return digest([common,sorted(set(external))])


def identity(plan,path):
    return digest([str(Path(plan['project']).resolve()),'geometry' if plan['scope'] in ('GEOMETRY','MAP_GEOMETRY') else 'map',str(Path(path).resolve())])

def options_key(plan,profile,materials,components,partial,physics,all_lods=False):
    geometry=[SCHEMA,profile,physics]
    # Keep existing LOD0 checkpoint identities compatible; opt-in grouped imports are distinct.
    if all_lods and profile=='5.6': geometry.append('shared_native_lods')
    is_editor=any(r.get('ue5') in (1016,1017) for r in plan.get('records',{}).values())
    if is_editor and materials:
        from ue5_editor_material import EDITOR_MATERIAL_REVISION
        geometry.extend([EDITOR_MATERIAL_REVISION,partial])
    mapping=[SCHEMA,profile,materials,components,partial]
    if is_editor and materials:mapping.append(EDITOR_MATERIAL_REVISION)
    if is_editor and components:mapping.append('editor_components_073')
    return digest(geometry if plan['scope'] in ('GEOMETRY','MAP_GEOMETRY') else mapping)

def collection_objects(collection):
    return list(collection.all_objects)

def find_existing(scene,key):
    return [c for c in scene.collection.children_recursive if c.get(TAG)==key]

def validate_collection(collection,source,options):
    if collection.get('UE_batch_source')!=source or collection.get('UE_batch_options')!=options: return 'source or settings changed'
    try:
        expected=json.loads(collection['UE_batch_members'])
        actual=sorted(o.get('UE_batch_member','') for o in collection_objects(collection))
        if expected!=actual or not actual or len(set(actual))!=len(actual): return 'collection membership changed'
        # Group ownership includes the shared rig bindings, not just object UUIDs.
        from skeletal_lod_group import members
        for obj in collection_objects(collection):
            if obj.type=='ARMATURE' and obj.get('UE_lod_group_count'): members(obj)
        result=json.loads(collection['UE_batch_result'])
        if not isinstance(result,dict) or result.get('status') not in ('completed','reconstructed'): return 'invalid saved result'
    except (ValueError,KeyError,TypeError): return 'missing or invalid recovery metadata'
    return ''

def mark_collection(collection,key,source,options,result):
    members=[]
    for obj in collection_objects(collection):
        token=uuid.uuid4().hex; obj['UE_batch_member']=token;obj[OBJECT_TAG]=key; members.append(token)
    if not members: raise ValueError('Cannot checkpoint an empty import collection')
    collection[TAG]=key; collection['UE_batch_source']=source; collection['UE_batch_options']=options
    collection['UE_batch_members']=json.dumps(sorted(members)); collection['UE_batch_result']=json.dumps(result)

def gallery_offset(scene,collection,result):
    import bpy
    end=0.
    for c in scene.collection.children_recursive:
        if c!=collection and c.get(TAG) and 'UE_batch_gallery_end' in c:
            end=max(end,float(c['UE_batch_gallery_end']))
    obj=bpy.data.objects.get(result['result']['object'])
    if obj is None or obj not in collection_objects(collection): raise ValueError('Missing imported gallery mesh')
    root=obj
    while root.parent is not None and root.parent in collection_objects(collection): root=root.parent
    root.location.x+=end; root['UE_gallery_offset_x']=root.location.x
    collection['UE_batch_gallery_end']=end+max(v.co.x for v in obj.data.vertices)-min(v.co.x for v in obj.data.vertices)+.5

def new_ids():
    import bpy
    # All Main ID collections, including lights, cameras, curves and constraints' object IDs.
    return {item.as_pointer():item for p in bpy.data.bl_rna.properties if p.type=='COLLECTION' for item in getattr(bpy.data,p.identifier) if isinstance(item,bpy.types.ID)}

def rollback_new(before):
    import bpy
    ids=[v for k,v in new_ids().items() if k not in before and not v.is_embedded_data]
    if ids: bpy.data.batch_remove(ids=ids)

def run_session(plan,profile='4.27',materials=True,components=True,partial=False,physics=False,all_lods=False):
    import bpy
    from project_batch import run_jobs
    scene=bpy.context.scene; common=source_fingerprint(plan); engine_hashes={}; options=options_key(plan,profile,materials,components,partial,physics,all_lods)
    for path in plan['jobs']:
        key=identity(plan,path); existing=find_existing(scene,key); source=job_fingerprint(plan,path,common,engine_hashes)
        owners=[o for o in scene.objects if o.get(OBJECT_TAG)==key]
        if owners and (len(existing)!=1 or any(o not in collection_objects(existing[0]) for o in owners)):
            yield dict(job=path,status='blocked_stale',detail='Owned objects exist outside the import collection; review before retrying');continue
        if existing:
            reason='multiple owned collections' if len(existing)!=1 else validate_collection(existing[0],source,options)
            if reason:
                yield dict(job=path,status='blocked_stale',detail=reason+'; review/remove the prior imported collection before retrying'); continue
            result=json.loads(existing[0]['UE_batch_result']); result['collection']=existing[0].name
            result['reused']=True; yield result; continue
        before=set(new_ids()); iterator=run_jobs(dict(plan,jobs=[path]),profile,materials,components,partial,physics,all_lods)
        try:
            try: result=next(iterator)
            finally: iterator.close()
            if result['status'] not in ('completed','reconstructed'):
                rollback_new(before); yield result; continue
            collection=bpy.data.collections.get(result['collection'])
            if collection is None or collection.as_pointer() in before: raise ValueError('Import did not create an owned collection')
            if plan['scope'] in ('GEOMETRY','MAP_GEOMETRY'): gallery_offset(scene,collection,result)
            mark_collection(collection,key,source,options,result)
        except Exception as exc:
            rollback_new(before); result=dict(job=path,status='failed',detail=f'{type(exc).__name__}: {exc}')
        yield result


def save_recovery_copy():
    """Opt-in full scene recovery copy. Never overwrite an existing file or change the active path."""
    import bpy
    if not bpy.data.filepath: raise ValueError('Save the current Blender file before enabling a recovery copy')
    source=Path(bpy.data.filepath).resolve()
    dest=source.with_name(source.stem+'.ue-recovery-'+uuid.uuid4().hex[:12]+'.blend')
    if dest.exists(): raise FileExistsError(str(dest))
    result=bpy.ops.wm.save_as_mainfile(filepath=str(dest),copy=True,check_existing=False)
    if result!={'FINISHED'} or not dest.is_file() or Path(bpy.data.filepath).resolve()!=source: raise RuntimeError('Unable to create independent recovery copy')
    return str(dest)
