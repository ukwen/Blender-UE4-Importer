"""Strict UE5.6 editor level and World Partition root StaticMeshActor reconstruction.
External actors are discovered through the level-relative folder and checked against
serialized PersistentLevel imports. Attached/Blueprint/runtime actors are not guessed.
"""
import json
import math
import struct
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from skeleton_native import Reader


def external_packages(content,map_path):
    content=Path(content).resolve();map_path=Path(map_path).resolve()
    require(map_path.is_relative_to(content),'Map is outside Content')
    relative=map_path.relative_to(content).with_suffix('')
    root=content/'__ExternalActors__'/relative
    paths=sorted(p for p in root.rglob('*.uasset') if p.is_file() and p.resolve().is_relative_to(root.resolve()))
    require(len(paths)<=10000,'External actor count limit');return paths


def index_value(tags,key,default=0):
    if key not in tags:return default
    t=tags[key];require(t['type']==['ObjectProperty'] and len(t['data'])==4 and not t['flags']&0x28,'Unsupported object field '+key)
    return struct.unpack('<i',t['data'])[0]


def placement_records(content,map_path):
    content=Path(content).resolve();map_path=Path(map_path).resolve();meta,raw,im,ex,ref,pkg=read_tables(map_path)
    require(meta['ue5'] in (1016,1017) and any(e['kind']=='World' and not e['outer'] for e in ex),'Expected UE5.6 editor World')
    level='/Game/'+map_path.relative_to(content).with_suffix('').as_posix()
    paths=external_packages(content,map_path); records=[]; skipped=[]; unsupported=Counter()
    for source in [map_path,*paths]:
        try:
            m,b,im,ex,ref,pkg=read_tables(source); names=m['names']
            for i,e in enumerate(ex,1):
                if e['kind']!='StaticMeshActor':
                    if e['kind']=='StaticMeshComponent' and e['outer']>0 and ref(e['outer'])['kind']!='StaticMeshActor':unsupported[ref(e['outer'])['kind']]+=1
                    continue
                try:
                    outer=e['outer'];parent=ref(outer)
                    require(parent and (parent.get('kind')=='Level') and parent['name']=='PersistentLevel','Not a PersistentLevel actor')
                    if source!=map_path:require(outer<0 and pkg(outer)==level,'External actor belongs to a different level')
                    else:require(outer>0,'Unexpected inline level ownership')
                    at=export_tags(b,e,names); cidx=index_value(at,'StaticMeshComponent');require(cidx>0 and index_value(at,'RootComponent')==cidx,'Root mesh association missing')
                    component=ref(cidx);require(component['outer']==i and component['kind']=='StaticMeshComponent','Invalid root mesh component')
                    ct=export_tags(b,component,names);require(not index_value(ct,'AttachParent') and not any(k in ct for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')),'Attached or absolute transform unsupported')
                    mi=index_value(ct,'StaticMesh'); require(mi<0 and ref(mi)['kind']=='StaticMesh' and pkg(mi),'Explicit StaticMesh reference missing')
                    fields={}
                    for k,kind,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]:
                        t=ct.get(k)
                        if not t:fields[k]=default;continue
                        require(t['type']==['StructProperty',kind,'/Script/CoreUObject'] and len(t['data'])==24 and not t['flags']&0x20,'Unsupported transform '+k)
                        fields[k]=struct.unpack('<3d',t['data'])
                    require(all(math.isfinite(x) for v in fields.values() for x in v) and all(abs(v)>1e-12 for v in fields['RelativeScale3D']),'Invalid transform')
                    label=e['name']; v=at.get('ActorLabel')
                    if v and v['type']==['StrProperty']:
                        r=Reader(v['data']);label=r.string();require(r.pos==len(r.data),'Invalid actor label')
                    overrides=[];v=ct.get('OverrideMaterials')
                    if v:
                        require(v['type']==['ArrayProperty','ObjectProperty'],'Unsupported override materials')
                        r=Reader(v['data']);n=r.count(4096)
                        for _ in range(n):
                            j=r.i();require(j==0 or j<0 and ref(j)['kind'] in ('Material','MaterialInstanceConstant') and pkg(j),'Invalid override material')
                            overrides.append(pkg(j) if j else '')
                        require(r.pos==len(r.data),'Unexpected material override bytes')
                    records.append(dict(actor=e['name'],label=label,source=source.relative_to(content).as_posix(),package=pkg(mi),fields=fields,overrides=overrides))
                except Exception as exc: skipped.append(dict(source=source.relative_to(content).as_posix(),actor=e['name'],detail=str(exc)))
        except Exception as exc: skipped.append(dict(source=source.relative_to(content).as_posix(),detail=str(exc)))
    return dict(level=level,external_count=len(paths),records=records,skipped=skipped,nonroot_component_classes=dict(unsupported))


def reconstruct(filepath,materials=False,components=False,partial=False):
    import bpy,uasset
    from static_scene import MeshResolver
    from blueprint_placement import apply_fields
    project=uasset.UProject(filepath);content=Path(project.dir)/'Content';data=placement_records(content,filepath)
    resolver=MeshResolver(project,'5.6');collection=bpy.data.collections.new('UE5 editor — '+Path(filepath).stem);bpy.context.scene.collection.children.link(collection)
    override_cache={};counts=Counter();
    for record in data['records']:
        mesh,status=resolver(record['package']);obj=bpy.data.objects.new(record['label'],mesh);collection.objects.link(obj)
        if mesh is None:obj.empty_display_type='ARROWS';obj.empty_display_size=.35
        obj['UE_actor']=record['actor'];obj['UE_source_actor_package']=record['source'];obj['UE_mesh_package']=record['package'];obj['UE_geometry_status']=status;obj['UE_preview_only']=mesh is None
        apply_fields(obj,record['fields']);counts[status]+=1
        obj['UE_material_override_packages']=json.dumps(record['overrides'])
        if mesh:
            for i,pkg in enumerate(record['overrides']):
                if i>=len(obj.material_slots):obj['UE_unresolved_override_slots']=True;break
                if not pkg:continue
                if pkg not in override_cache:
                    mat=bpy.data.materials.new(pkg.rsplit('/',1)[-1]);mat['UE_material_package']=pkg;mat['UE_unresolved_material']=True;override_cache[pkg]=mat
                obj.material_slots[i].link='OBJECT';obj.material_slots[i].material=override_cache[pkg]
    report=dict(level=data['level'],external_actor_packages=data['external_count'],static_actors=len(data['records']),actor_status=dict(counts),skipped=data['skipped'],nonroot_component_classes=data['nonroot_component_classes'],unique_reconstructed_meshes=len({o.data.as_pointer() for o in collection.objects if o.type=='MESH'}),decode_attempts=resolver.decode_attempts,dependencies={p:{'status':r['status'],'detail':r['detail']} for p,r in resolver.records.items()},materials_imported=False,material_graph_status='unresolved editor materials',components_status='root StaticMeshActor only; other components not reconstructed')
    if components:
        from ue5_editor_components import placements
        actors,skips=placements(content,filepath); component_counts=Counter(); component_objects=0
        for actor in actors:
            nodes={}
            for c in actor['components']:
                mesh,status=resolver(c['package']) if c['package'] else (None,'anchor')
                obj=bpy.data.objects.new(actor['label']+' / '+c['name'],mesh);collection.objects.link(obj);nodes[c['index']]=obj
                if c['parent']:obj.parent=nodes[c['parent']]
                apply_fields(obj,c['fields']);obj['UE_blueprint_package']=actor['blueprint'];obj['UE_actor']=actor['actor'];obj['UE_source_actor_package']=actor['source'];obj['UE_component_name']=c['name'];obj['UE_component_default_origin']=c['default_origin'];obj['UE_component_template']=c['template_name'];obj['UE_geometry_status']=status;obj['UE_preview_only']=mesh is None
                obj['UE_native_defaults_unverified']=True
                if not mesh:obj.empty_display_type='PLAIN_AXES';obj.empty_display_size=.15
                if c['package']:
                    obj['UE_mesh_package']=c['package'];obj['UE_material_override_packages']=json.dumps(c['overrides']);component_counts[status]+=1
                    if mesh:
                        for i,pkg in enumerate(c['overrides']):
                            if i>=len(obj.material_slots):obj['UE_unresolved_override_slots']=True;break
                            if not pkg:continue
                            if pkg not in override_cache:
                                mat=bpy.data.materials.new(pkg.rsplit('/',1)[-1]);mat['UE_material_package']=pkg;mat['UE_unresolved_material']=True;override_cache[pkg]=mat
                            obj.material_slots[i].link='OBJECT';obj.material_slots[i].material=override_cache[pkg]
                component_objects+=1
        report['component_report']=dict(actors=len(actors),objects=component_objects,status=dict(component_counts),skipped=skips,scope='saved static components with exact CDO/SCS defaults; native C++ defaults not independently verified')
        report['components_status']='bounded saved Blueprint static components; no runtime execution'
        report['decode_attempts']=resolver.decode_attempts;report['dependencies']={p:{'status':r['status'],'detail':r['detail']} for p,r in resolver.records.items()}
        from ue5_editor_characters import extend_characters
        report['character_report']=extend_characters(content,filepath,collection)
        report['components_status']='bounded saved Blueprint static and skeletal components; no runtime execution'
    if materials:
        from ue5_editor_material import bind_slots
        report['material_report']=bind_slots(collection.objects,content,partial)
        report['materials_imported']=any(x['status'] in ('partial','supported_pbr_subset') for x in report['material_report'].values())
        report['material_graph_status']='explicit supported PBR subset; partial graphs opt-in'
    collection['UE_source_map_path']=str(Path(filepath).resolve());collection['UE_geometry_only']=not report['materials_imported'];collection['UE_reconstructed_actors']=counts['reconstructed'];collection['UE_unresolved_actors']=sum(counts.values())-counts['reconstructed']+len(data['skipped'])
    text=bpy.data.texts.new(collection.name+' - import report.json');text.write(json.dumps(report,indent=2));collection['UE_report']=text.name
    return collection,report
