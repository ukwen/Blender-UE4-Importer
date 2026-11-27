"""Saved UE5.6 root light layout and environment markers; not Unreal renderer evaluation."""
import json
import math
import struct
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables, require
from ue5_editor_scene import external_packages, index_value
from ue5_editor_tags import export_tags
from skeleton_native import Reader

LIGHTS={'DirectionalLight':('DirectionalLightComponent','SUN'),
        'PointLight':('PointLightComponent','POINT'), 'SpotLight':('SpotLightComponent','SPOT')}
MARKERS={'PlayerStart':'CapsuleComponent','SkyLight':'SkyLightComponent',
         'ExponentialHeightFog':'ExponentialHeightFogComponent','SkyAtmosphere':'SkyAtmosphereComponent',
         'AtmosphericFog':'AtmosphericFogComponent','PostProcessVolume':'BrushComponent'}
FLOATS=('Intensity','AttenuationRadius','SourceRadius','SoftSourceRadius','SourceLength','LightSourceAngle',
        'InnerConeAngle','OuterConeAngle','Temperature','FogDensity','StartDistance')
BOOLS=('CastShadows','bUseTemperature','bVisible','bAffectsWorld','bRealTimeCapture','bLowerHemisphereIsBlack')
TRANSFORMS=(('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.)))


def properties(tags,names):
    result={}
    for name in FLOATS:
        if name in tags:
            t=tags[name];require(t['type']==['FloatProperty'] and len(t['data'])==4 and not t['flags']&0x28,'Unsupported '+name)
            value=struct.unpack('<f',t['data'])[0];require(math.isfinite(value) and value>=0,'Invalid '+name);result[name]=value
    for name in BOOLS:
        if name in tags:
            t=tags[name];require(t['type']==['BoolProperty'] and not t['data'] and not t['flags']&0x28,'Unsupported '+name);result[name]=bool(t['flags']&16)
    if 'LightColor' in tags:
        t=tags['LightColor'];require(t['type']==['StructProperty','Color','/Script/CoreUObject'] and len(t['data'])==4 and not t['flags']&0x20,'Unsupported LightColor')
        b,g,r,a=t['data'];result['LightColor']=[r,g,b,a]
    if 'IntensityUnits' in tags:
        t=tags['IntensityUnits'];require(t['type'][0] in ('EnumProperty','ByteProperty') and len(t['data'])==8 and not t['flags']&0x28,'Unsupported IntensityUnits')
        result['IntensityUnits']=Reader(t['data']).name(names)
    return result


def records(content,map_path):
    content=Path(content).resolve();map_path=Path(map_path).resolve();meta,_,_,exports,_,_=read_tables(map_path)
    require(meta['ue5'] in (1016,1017) and any(e['kind']=='World' and not e['outer'] for e in exports),'Expected UE5.6 editor World')
    level='/Game/'+map_path.relative_to(content).with_suffix('').as_posix();result=[];skipped=[]
    for source in [map_path,*external_packages(content,map_path)]:
        rel=source.relative_to(content).as_posix()
        try:
            m,raw,_,exports,ref,pkg=read_tables(source);names=m['names']
            for i,e in enumerate(exports,1):
                kind=e['kind']
                if kind not in LIGHTS and kind not in MARKERS:continue
                try:
                    outer=e['outer'];parent=ref(outer)
                    require(parent and parent['kind']=='Level' and parent['name']=='PersistentLevel','Not a PersistentLevel actor')
                    require((source==map_path and outer>0) or (source!=map_path and outer<0 and pkg(outer)==level),'Level ownership mismatch')
                    at=export_tags(raw,e,names);idx=index_value(at,'RootComponent');component=ref(idx)
                    expected=LIGHTS[kind][0] if kind in LIGHTS else MARKERS[kind]
                    require(idx>0 and component['outer']==i and component['kind']==expected,'Invalid root component')
                    if kind in LIGHTS:require(index_value(at,'LightComponent')==idx,'Light component association missing')
                    ct=export_tags(raw,component,names)
                    require(not index_value(ct,'AttachParent') and not any(k in ct for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')),'Attached or absolute root unsupported')
                    fields={}
                    for k,typ,default in TRANSFORMS:
                        t=ct.get(k)
                        if t is None:fields[k]=default;continue
                        require(t['type']==['StructProperty',typ,'/Script/CoreUObject'] and len(t['data'])==24 and not t['flags']&0x20,'Unsupported transform '+k)
                        fields[k]=struct.unpack('<3d',t['data'])
                    require(all(math.isfinite(v) for f in fields.values() for v in f) and all(abs(v)>1e-12 for v in fields['RelativeScale3D']),'Invalid transform')
                    label=e['name'];t=at.get('ActorLabel')
                    if t:
                        require(t['type']==['StrProperty'],'Invalid actor label');r=Reader(t['data']);label=r.string();require(r.pos==len(r.data),'Invalid actor label')
                    props=properties(ct,names)
                    for k in ('InnerConeAngle','OuterConeAngle'):
                        if k in props:require(0<=props[k]<90,'Unsupported cone angle')
                    if 'InnerConeAngle' in props and 'OuterConeAngle' in props:require(props['InnerConeAngle']<=props['OuterConeAngle'],'Invalid cone angles')
                    result.append(dict(actor=e['name'],label=label,source=rel,kind=kind,component=component['name'],fields=fields,properties=props,untranslated_component_fields=sorted(set(ct)-set(props)-set(fields)),untranslated_actor_fields=sorted(set(at)-{'ActorLabel','RootComponent','LightComponent'})))
                except Exception as exc:skipped.append(dict(source=rel,actor=e['name'],kind=kind,detail=str(exc)))
        except Exception as exc:skipped.append(dict(source=rel,detail=str(exc)))
    return dict(level=level,records=result,skipped=skipped)


def srgb_linear(value):
    v=value/255.;return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4


def reconstruct(filepath,preview_scale=1.):
    import bpy
    from mathutils import Matrix
    from blueprint_placement import apply_fields
    from uasset import UProject
    from project_session import new_ids,rollback_new
    require(math.isfinite(preview_scale) and 0<preview_scale<=1000,'Invalid preview intensity multiplier')
    path=Path(filepath).resolve();project=UProject(str(path));content=Path(project.dir)/'Content';data=records(content,path)
    require(data['records'],'No supported light or marker records')
    require(not any(c.get('UE_lighting_source')==str(path) for c in bpy.context.scene.collection.children_recursive),'Lighting already imported; remove the prior lighting collection before reimporting')
    before=set(new_ids());counts=Counter()
    try:
        collection=bpy.data.collections.new('UE5 lighting preview — '+path.stem);bpy.context.scene.collection.children.link(collection)
        for r in data['records']:
            kind=r['kind'];p=r['properties'];light=None
            if kind in LIGHTS:
                light=bpy.data.lights.new(r['label'],LIGHTS[kind][1]);light['UE_preview_only']=True
                # Deliberate preview scaling, not a photometric conversion. Units omitted by source
                # are not inferred. Preserve exact source values in the object metadata.
                if 'Intensity' in p:light.energy=p['Intensity']*(1. if kind=='DirectionalLight' else .01)*preview_scale
                else:light.energy*=preview_scale
                if 'LightColor' in p:light.color=tuple(srgb_linear(v) for v in p['LightColor'][:3])
                if 'CastShadows' in p:light.use_shadow=p['CastShadows']
                if 'AttenuationRadius' in p and kind!='DirectionalLight':light.use_custom_distance=True;light.cutoff_distance=p['AttenuationRadius']*.01
                if 'SourceRadius' in p and kind!='DirectionalLight':light.shadow_soft_size=p['SourceRadius']*.01
                if 'LightSourceAngle' in p and kind=='DirectionalLight':light.angle=math.radians(p['LightSourceAngle'])
                if kind=='SpotLight' and 'OuterConeAngle' in p:
                    light.spot_size=math.radians(2*p['OuterConeAngle'])
                    if 'InnerConeAngle' in p and p['OuterConeAngle']>0:light.spot_blend=1-p['InnerConeAngle']/p['OuterConeAngle']
            obj=bpy.data.objects.new(r['label'],light);collection.objects.link(obj);apply_fields(obj,r['fields'])
            if light:
                # UE light forward +X maps to Blender +Y; Blender emits along local -Z.
                rotation=obj.rotation_euler.to_matrix()@Matrix.Rotation(math.pi/2,3,'X');obj.rotation_mode='QUATERNION';obj.rotation_quaternion=rotation.to_quaternion()
                if p.get('bVisible') is False or p.get('bAffectsWorld') is False:obj.hide_render=True;obj.hide_viewport=True
            else:obj.empty_display_type='ARROWS' if kind=='PlayerStart' else 'PLAIN_AXES';obj.empty_display_size=.5
            obj['UE_actor']=r['actor'];obj['UE_source_actor_package']=r['source'];obj['UE_actor_kind']=kind;obj['UE_preview_only']=True;obj['UE_light_source_properties']=json.dumps(p,sort_keys=True);obj['UE_source_transform']=json.dumps(r['fields']);counts[kind]+=1
        collection['UE_lighting_source']=str(path);collection['UE_preview_only']=True
        report=dict(level=data['level'],counts=dict(counts),skipped=data['skipped'],records=data['records'],preview_scale=preview_scale,scope='Saved root light transforms and explicit source fields. Approximate intensity (sun x1, local x0.01); unset values use Blender defaults. Temperature, source length, IES, shadow/runtime settings, sky/fog/post-process effects not evaluated; environmental actors are markers only.')
        text=bpy.data.texts.new(collection.name+' - import report.json');text.write(json.dumps(report,indent=2));collection['UE_report']=text.name
        return collection,report
    except Exception:
        rollback_new(before);raise
