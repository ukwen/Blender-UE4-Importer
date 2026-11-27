"""Preserve saved decal projector transforms and source properties, not rendered decals."""
import json
import math
import struct
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables, require
from ue5_editor_scene import external_packages, index_value
from ue5_editor_tags import export_tags
from skeleton_native import Reader


def vector(tags, key, kind, default=None):
    t=tags.get(key)
    if t is None:return default
    require(t['type']==['StructProperty',kind,'/Script/CoreUObject'] and len(t['data'])==24 and not t['flags']&0x20,'Invalid '+key)
    v=struct.unpack('<3d',t['data']);require(all(math.isfinite(x) for x in v),'Nonfinite '+key)
    return v


def fields(tags):
    require(not index_value(tags,'AttachParent') and not any(k in tags for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')),'Attached or absolute decal unsupported')
    result={k:vector(tags,k,kind,default) for k,kind,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]}
    require(all(abs(x)>1e-12 for x in result['RelativeScale3D']),'Degenerate decal scale')
    size=vector(tags,'DecalSize','Vector');require(size is None or all(0<x<=1e9 for x in size),'Invalid decal size')
    props={}
    for k,typ,fmt in [('FadeScreenSize','FloatProperty','f'),('SortOrder','IntProperty','i'),('FadeStartDelay','FloatProperty','f'),('FadeDuration','FloatProperty','f'),('FadeInStartDelay','FloatProperty','f'),('FadeInDuration','FloatProperty','f')]:
        t=tags.get(k)
        if t is None:continue
        require(t['type']==[typ] and len(t['data'])==4 and not t['flags']&0x28,'Invalid '+k)
        v=struct.unpack('<'+fmt,t['data'])[0];require(math.isfinite(v) and (typ=='IntProperty' or v>=0),'Invalid '+k);props[k]=v
    return result,size,props


def records(content,map_path):
    content=Path(content).resolve();path=Path(map_path).resolve();m,_,_,ex,_,_=read_tables(path)
    require(m['ue5'] in (1016,1017) and any(e['kind']=='World' and not e['outer'] for e in ex),'Expected UE5.6 editor World')
    level='/Game/'+path.relative_to(content).with_suffix('').as_posix();rows=[];skipped=[]
    for source in [path,*external_packages(content,path)]:
        rel=source.relative_to(content).as_posix()
        try:
            m,b,_,ex,ref,pkg=read_tables(source);names=m['names']
            for i,e in enumerate(ex,1):
                if e['kind']!='DecalActor':continue
                try:
                    outer=e['outer'];parent=ref(outer);require(parent and parent['kind']=='Level' and parent['name']=='PersistentLevel','Not a PersistentLevel actor')
                    require((source==path and outer>0) or (source!=path and outer<0 and pkg(outer)==level),'Decal level ownership mismatch')
                    at=export_tags(b,e,names);idx=index_value(at,'RootComponent');require(idx>0 and index_value(at,'Decal')==idx,'Decal root association missing')
                    co=ref(idx);require(co['outer']==i and co['kind']=='DecalComponent','Invalid decal component');ct=export_tags(b,co,names)
                    transform,size,props=fields(ct);mi=index_value(ct,'DecalMaterial');material=None;status='not_serialized'
                    if mi:
                        require(mi<0 and ref(mi)['kind'] in ('Material','MaterialInstanceConstant','MaterialInstance') and pkg(mi),'Invalid decal material reference');material=pkg(mi);status='external_or_unresolved'
                        if material.startswith('/Game/'):
                            p=(content/(material[6:]+'.uasset')).resolve();require(p.is_relative_to(content),'Invalid decal material path');status='present_not_reconstructed' if p.is_file() else 'missing'
                    label=e['name'];t=at.get('ActorLabel')
                    if t:
                        require(t['type']==['StrProperty'],'Invalid actor label');r=Reader(t['data']);label=r.string();require(r.pos==len(r.data),'Invalid actor label extent')
                    rows.append(dict(actor=e['name'],source=rel,label=label,component=co['name'],fields=transform,decal_size_cm=size,properties=props,material_package=material,material_status=status,untranslated_fields=sorted(set(ct)-set(transform)-set(props)-{'DecalSize','DecalMaterial','AttachParent'})))
                except Exception as exc:skipped.append(dict(source=rel,actor=e['name'],detail=str(exc)))
        except Exception as exc:skipped.append(dict(source=rel,detail=str(exc)))
    require(len({(r['source'],r['actor']) for r in rows})==len(rows),'Duplicate decal actor identity')
    return dict(level=level,records=rows,skipped=skipped)


def extend_decals(content,path,parent):
    import bpy
    from blueprint_placement import apply_fields
    data=records(content,path);rows=data['records'];count=0
    if rows:
        collection=bpy.data.collections.new(Path(path).stem+' — Decal projector guides');parent.children.link(collection)
        for r in rows:
            obj=bpy.data.objects.new(r['label']+' / Decal',None);collection.objects.link(obj);apply_fields(obj,r['fields']);obj.empty_display_type='ARROWS';obj.empty_display_size=.1;obj.hide_render=True
            obj['UE_actor']=r['actor'];obj['UE_source_actor_package']=r['source'];obj['UE_decal_record']=json.dumps(r);obj['UE_decal_projector']=True;obj['UE_preview_only']=True
            size=r['decal_size_cm']
            if size is not None:
                guide=bpy.data.objects.new(r['label']+' / Saved size guide',None);collection.objects.link(guide);guide.parent=obj;guide.empty_display_type='CUBE';guide.empty_display_size=1.;guide.scale=(size[1]*.01,size[0]*.01,size[2]*.01);guide.hide_render=True;guide['UE_preview_only']=True;count+=1
        collection['UE_preview_only']=True
    return dict(data,projector_anchors=len(rows),size_guides=count,material_status=dict(Counter(r['material_status'] for r in rows)),rendered_decals=0,scope='Saved decal projector anchors and explicit size guides only; omitted sizes not inferred. No receiver projection, material conversion, blending or rendering.')
