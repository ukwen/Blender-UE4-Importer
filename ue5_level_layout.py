"""Read saved World Partition ownership and explicitly report unhandled level composition.
No inference from generic map dependencies or runtime cell evaluation.
"""
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables, require
from ue5_editor_tags import export_tags
from ue5_editor_scene import external_packages,index_value
from ue5_scene_dependencies import external_objects


def saved_bool(tags,key):
    if key not in tags:return None
    t=tags[key]
    require(t['type']==['BoolProperty'] and not t['data'] and not t['flags']&0x28,'Unsupported '+key)
    return bool(t['flags']&16)


def inventory(content,path):
    content=Path(content).resolve();path=Path(path).resolve()
    require(path.is_relative_to(content) and path.suffix=='.umap','Expected map under Content')
    level='/Game/'+path.relative_to(content).with_suffix('').as_posix()
    m,b,_,es,ref,pkg=read_tables(path)
    require(m['ue5'] in (1016,1017),'Unsupported level layout profile')
    worlds=[(i,e) for i,e in enumerate(es,1) if e['kind']=='World' and not e['outer']]
    require(len(worlds)==1,'Expected one saved World');wi,w=worlds[0]
    levels=[(i,e) for i,e in enumerate(es,1) if e['kind']=='Level' and e['name']=='PersistentLevel' and e['outer']==wi]
    require(len(levels)==1,'Expected one owned PersistentLevel');li,l=levels[0]
    lt=export_tags(b,l,m['names']);wt=export_tags(b,w,m['names'])
    flags={k:saved_bool(lt,k) for k in ('bUseExternalActors','bIsPartitioned','bUseActorFolders')}
    partitions=[(i,e) for i,e in enumerate(es,1) if e['kind']=='WorldPartition']
    partition=None;issues=[]
    if partitions:
        require(len(partitions)==1,'Ambiguous World Partition')
        pi,p=partitions[0];ws=index_value(lt,'WorldSettings');require(ws>0 and p['outer']==ws and ref(ws)['kind']=='WorldSettings' and ref(ws)['outer']==li,'Invalid World Partition ownership')
        pt=export_tags(b,p,m['names']);hashes={}
        for k in ('EditorHash','RuntimeHash'):
            idx=index_value(pt,k);require(idx>0 and ref(idx)['outer']==pi,'Invalid partition hash ownership: '+k)
            hashes[k]=ref(idx)['kind']
        partition=dict(name=p['name'],owner=ref(ws)['name'],streaming_enabled=saved_bool(pt,'bEnableStreaming'),hashes=hashes)
        if flags['bIsPartitioned'] is not True:issues.append('Partition object and saved partition flag disagree or are incomplete')
    elif flags['bIsPartitioned'] is True:issues.append('Partition flag without saved partition object')
    links=[];owned=[];external_errors=[]
    def candidates(source,exports):
        for e in exports:
            kind=e['kind'];k=kind.lower()
            if 'levelstreaming' in k or 'levelinstance' in k or 'packedlevelactor' in k:
                links.append(dict(source=source,actor=e['name'],kind=kind,status='unresolved_native_level_composition'))
    candidates(path.relative_to(content).as_posix(),es)
    for f in external_packages(content,path):
        rel=f.relative_to(content).as_posix()
        try:
            _,_,_,xs,xref,xpkg=read_tables(f)
            actors=[e for e in xs if e['outer']<0 and xref(e['outer'])['kind']=='Level' and xref(e['outer'])['name']=='PersistentLevel' and xpkg(e['outer'])==level]
            if not actors:raise ValueError('No matching external PersistentLevel actor')
            owned.append(dict(source=rel,actors=[dict(name=e['name'],kind=e['kind']) for e in actors]));candidates(rel,actors)
        except Exception as exc:external_errors.append(dict(source=rel,detail=str(exc)))
    world_fields=sorted(k for k in wt if 'streaming' in k.lower() or 'levelinstance' in k.lower())
    if world_fields:issues.append('World streaming-related fields preserved but not decoded')
    if links:issues.append('Native level composition records are not decoded')
    if external_errors:issues.append('External actor ownership audit incomplete')
    return dict(level=level,flags=flags,partition=partition,owned_external_packages=len(owned),external_actor_classes=dict(Counter(a['kind'] for x in owned for a in x['actors'])),external_actors=owned,external_errors=external_errors,external_object_packages=[f.relative_to(content).as_posix() for f in external_objects(content,path)],composition_candidates=links,world_streaming_fields=world_fields,issues=issues,scope='Saved partition ownership only; no runtime cells, data layer visibility, level instance transforms or streaming composition evaluated.')
