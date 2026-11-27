"""Map-owned saved capsule/body pairs. No spawning or construction-script execution."""
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_editor_scene import external_packages,index_value
from ue5_editor_components import character_defaults,character_fields,array,build_character_data
from skeleton_native import Reader


def placements(content,map_path):
    content=Path(content).resolve();path=Path(map_path).resolve();level='/Game/'+path.relative_to(content).with_suffix('').as_posix()
    meta,_,_,exports,_,_=read_tables(path);require(meta['ue5'] in (1016,1017) and any(e['kind']=='World' and not e['outer'] for e in exports),'Expected editor World')
    result=[];skipped=[];cache={}
    for source in [path,*external_packages(content,path)]:
        rel=source.relative_to(content).as_posix()
        try:m,b,im,ex,ref,pkg=read_tables(source)
        except Exception as exc:skipped.append(dict(source=rel,detail=str(exc)));continue
        owners={}
        for j,e in enumerate(ex,1):
            if e['kind']=='SkeletalMeshComponent' and e['outer']>0:owners.setdefault(e['outer'],{})[j]=e
        for i,owned in owners.items():
            a=ref(i)
            try:
                require(a['kind'].endswith('_C') and a['class_index']<0,'Unsupported skeletal actor class')
                outer=a['outer'];parent=ref(outer);require(parent and parent['kind']=='Level' and parent['name']=='PersistentLevel','Not a PersistentLevel actor')
                require((source==path and outer>0) or (source!=path and outer<0 and pkg(outer)==level),'Saved character level mismatch')
                cp=pkg(a['class_index']);require(cp.startswith('/Game/'),'External character class unsupported');p=(content/(cp[6:]+'.uasset')).resolve();require(p.is_relative_to(content) and p.is_file(),'Missing original Blueprint '+cp)
                at=export_tags(b,a,m['names']);ri=index_value(at,'RootComponent');mi=index_value(at,'Mesh');require(ri>0 and ri==index_value(at,'CapsuleComponent') and mi in owned and len(owned)==1,'Expected unique saved root/body association')
                root,mesh=ref(ri),ref(mi);require(root['outer']==i and root['kind']=='CapsuleComponent','Invalid saved capsule owner')
                rt,mt=export_tags(b,root,m['names']),export_tags(b,mesh,m['names']);require(not index_value(rt,'AttachParent') and index_value(mt,'AttachParent')==ri,'Invalid saved body attachment')
                if p not in cache:cache[p]=character_defaults(p)
                d=cache[p];require(d['name']==a['kind'] and d['source']==cp and root['name']==d['root_name'] and mesh['name']==d['mesh_name'],'Character template identity mismatch')
                require(not any(k in mt for k in ('SkeletalMesh','SkinnedAsset')),'Instance skeletal asset override not yet supported')
                overrides=list(d['overrides']) if 'OverrideMaterials' not in mt else []
                for j in array(mt,'OverrideMaterials'):
                    require(j==0 or j<0 and ref(j)['kind'] in ('Material','MaterialInstanceConstant') and pkg(j),'Invalid saved body material override');overrides.append(pkg(j) if j else '')
                label=a['name']
                if 'ActorLabel' in at:
                    t=at['ActorLabel'];require(t['type']==['StrProperty'],'Invalid actor label');r=Reader(t['data']);label=r.string();require(r.pos==len(r.data),'Invalid actor label extent')
                root_fields=character_fields(dict(d['root_tags'],**rt));mesh_fields=character_fields(dict(d['mesh_tags'],**mt))
                scale=root_fields['RelativeScale3D'];require(max(scale)-min(scale)<1e-9,'Nonuniform capsule scale unsupported for saved body hierarchy')
                result.append(dict(source=rel,actor=a['name'],label=label,blueprint=cp,name=a['kind'],mesh_package=d['mesh_package'],root_name=root['name'],mesh_name=mesh['name'],root_fields=root_fields,mesh_fields=mesh_fields,overrides=overrides))
            except Exception as exc:skipped.append(dict(source=rel,actor=a['name'],detail=str(exc)))
    require(len({(r['source'],r['actor']) for r in result})==len(result),'Duplicate saved character actor identity')
    return dict(level=level,records=result,skipped=skipped)


def extend_characters(content,path,collection):
    """Add only resolved bodies, keep a per-actor failure report and never substitute assets."""
    import json
    from project_session import new_ids,rollback_new
    data=placements(content,path);counts=Counter();details=[];cache={}
    for r in data['records']:
        before=set(new_ids())
        try:
            # A separate static-component root must not silently duplicate the actor hierarchy.
            require(not any(o.get('UE_actor')==r['actor'] and o.get('UE_source_actor_package')==r['source'] for o in collection.objects),'Shared static/skeletal actor hierarchy not yet supported')
            d=dict(r,source=r['blueprint'],content=Path(content).resolve());a,obj,arm=build_character_data(d,collection,sockets=True,allow_unresolved_slots=True,decoded_cache=cache,allow_missing_sockets=True)
            a.name=r['label'];arm.name=r['label']+' / '+r['mesh_name'];obj.name=r['label']+' / body';a['UE_character_record']=json.dumps(r,sort_keys=True)
            for o in (a,arm,obj):o['UE_actor']=r['actor'];o['UE_source_actor_package']=r['source'];o['UE_blueprint_package']=r['blueprint']
            a['UE_component_name']=r['root_name'];arm['UE_component_name']=r['mesh_name'];a['UE_geometry_status']='reconstructed_reference_pose'
            unresolved=json.loads(obj.data.get('UE_unresolved_material_groups','[]'));status='geometry_only_unresolved_slots' if unresolved else 'reconstructed';counts[status]+=1
            details.append(dict(**r,status=status,vertices=len(obj.data.vertices),bones=len(arm.data.bones),unresolved_material_groups=unresolved,socket_status=arm.get('UE_socket_status','source sockets checked')))
        except Exception as exc:
            rollback_new(before);counts['unresolved']+=1;details.append(dict(**r,status='unresolved',detail=str(exc)))
    return dict(level=data['level'],records=details,skipped=data['skipped'],status=dict(counts),decoded_meshes=len(cache),scope='Saved capsule/body reference pose only; no runtime animation, spawning, construction scripts or material-slot inference')
