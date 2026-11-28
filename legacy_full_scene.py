"""Atomic unified level transfer for the original UE4 editor 508/522 map profiles.
The native foliage decoder is reused, not generalized to UE5.
"""
import json
import math
from pathlib import Path
from collections import Counter


def supported(meta):
    return (meta.get('status') == 'tables_inspected' and meta.get('legacy') == -7
            and meta.get('ue4') in (508, 522) and meta.get('ue5') is None
            and meta.get('licensee') == 0 and not meta.get('sidecars')
            and not meta.get('flags',0) & 0x80002000)


def validate_tables(meta):
    if not supported(meta): raise ValueError('Unsupported legacy full scene profile')
    ic,ec,io,eo,end=(meta[k] for k in ('import_count','export_count','import_offset','export_offset','header_end'))
    import_stride,export_stride=(28,96) if meta['ue4']==508 else (36,104)
    if not (0<ic<=100000 and 0<ec<=100000 and 0<io<eo<end<=meta['size']
            and io+import_stride*ic==eo and eo+export_stride*ec<=end):
        raise ValueError('Unsupported legacy map table extents')


def inventory(path, content):
    from uasset import UAsset
    rows=[]; lights=[]; skipped=[]
    source=path.relative_to(content).as_posix()
    with UAsset(str(path)) as asset:
        if asset.summary.compression_flags: raise ValueError('Compressed legacy map unsupported')
        if not any(e.export_class_type=='World' and not e.outer_index for e in asset.exports): raise ValueError('Expected legacy editor World')
        for i,e in enumerate(asset.exports,1):
            if not 0<e.outer_index<=len(asset.exports): continue
            parent=asset.GetExport(e.outer_index)
            if parent.export_class_type!='Level' or parent.object_name!='PersistentLevel': continue
            kind=e.export_class_type
            rows.append(dict(source=source,actor=e.object_name,kind=kind))
            if kind not in ('DirectionalLight','SkyLight'): continue
            try:
                e.ReadProperties(False); root=e.properties.TryGetValue('RootComponent')
                expected={'DirectionalLight':'DirectionalLightComponent','SkyLight':'SkyLightComponent'}[kind]
                if root is None or root is not e.properties.TryGetValue('LightComponent') or root.outer_index!=i or root.export_class_type!=expected: raise ValueError('Invalid saved light component association')
                root.ReadProperties(False); p=root.properties
                if p.TryGetValue('AttachParent') is not None or any(p.TryGetValue(k,False) for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')): raise ValueError('Attached or absolute light unsupported')
                fields={}
                for k,default in [('RelativeLocation',(0.,0.,0.)),('RelativeRotation',(0.,0.,0.)),('RelativeScale3D',(1.,1.,1.))]:
                    v=p.TryGetValue(k); fields[k]=(v.x,v.y,v.z) if v is not None else default
                if not all(math.isfinite(v) for f in fields.values() for v in f) or any(v==0 for v in fields['RelativeScale3D']): raise ValueError('Invalid light transform')
                props={}
                for k in ('Intensity','CastShadows','bVisible','bAffectsWorld'):
                    if k in p: props[k]=p.TryGetValue(k)
                if 'Intensity' in props and (not math.isfinite(props['Intensity']) or props['Intensity']<0): raise ValueError('Invalid intensity')
                color=p.TryGetValue('LightColor')
                if color is not None: props['LightColor']=(color.r,color.g,color.b,color.a)
                lights.append(dict(source=source,actor=e.object_name,kind=kind,label=e.properties.TryGetValue('ActorLabel',e.object_name),fields=fields,properties=props))
            except Exception as exc: skipped.append(dict(actor=e.object_name,kind=kind,detail=str(exc)))
    if len({r['actor'] for r in rows})!=len(rows): raise ValueError('Ambiguous legacy level actor identity')
    return rows,lights,skipped


def add_lights(collection, records, preview_scale):
    import bpy
    from mathutils import Matrix
    from blueprint_placement import apply_fields
    from ue5_editor_lighting import srgb_linear
    for r in records:
        p=r['properties']; light=None
        if r['kind']=='DirectionalLight':
            light=bpy.data.lights.new(r['label'],'SUN')
            light.energy=p.get('Intensity',light.energy)*preview_scale
            if 'LightColor' in p: light.color=tuple(srgb_linear(v) for v in p['LightColor'][:3])
            if 'CastShadows' in p: light.use_shadow=p['CastShadows']
        obj=bpy.data.objects.new(r['label'],light); collection.objects.link(obj); apply_fields(obj,r['fields'])
        if light:
            rotation=obj.rotation_euler.to_matrix()@Matrix.Rotation(math.pi/2,3,'X'); obj.rotation_mode='QUATERNION';obj.rotation_quaternion=rotation.to_quaternion()
            if p.get('bVisible') is False or p.get('bAffectsWorld') is False: obj.hide_render=True;obj.hide_viewport=True
        else: obj.empty_display_type='PLAIN_AXES';obj.empty_display_size=.5
        obj['UE_actor']=r['actor'];obj['UE_source_actor_package']=r['source'];obj['UE_preview_only']=True;obj['UE_light_source_properties']=json.dumps(p);obj['UE_source_transform']=json.dumps(r['fields'])


def reconstruct(filepath,partial=False,preview_scale=1.,strict_dependencies=False,cooked_profile='4.27'):
    import bpy
    from package_inspector import inspect_package
    from project_session import new_ids,rollback_new
    from project_paths import ProjectPaths
    from ue5_scene_dependencies import audit
    from ue5_full_scene import coverage
    from static_scene import reconstruct_static_map
    path=Path(filepath).resolve(); project=ProjectPaths(str(path));content=Path(project.dir)/'Content';scene=bpy.context.scene
    meta=inspect_package(path);validate_tables(meta)
    if not math.isfinite(preview_scale) or not 0<preview_scale<=1000: raise ValueError('Invalid preview intensity multiplier')
    if any(str(path)==c.get(k) for c in scene.collection.children_recursive for k in ('UE_full_scene_source','UE_source_map_path')): raise ValueError('Level already imported (full or separate stages)')
    dependencies=audit(project,path)
    if strict_dependencies and not dependencies['ready_for_strict_import']: raise ValueError('Source dependency check failed; run Analyze Level Dependencies or disable strict mode')
    rows,lights,skipped=inventory(path,content)
    before=set(new_ids());old_camera=scene.camera
    try:
        coll,geo=reconstruct_static_map(str(path),materials=True,allow_partial_materials=partial,cooked_profile=cooked_profile,components=True)
        source=path.relative_to(content).as_posix()
        # Attach saved actor identity only when it is explicitly present on legacy outputs.
        for obj in coll.all_objects:
            actor=obj.get('UE_actor') or obj.get('UE_component_actor') or obj.get('UE_foliage_root')
            if not actor and obj.get('UE_foliage_component') and obj.parent and obj.parent.parent: actor=obj.parent.parent.get('UE_foliage_root')
            if actor: obj['UE_actor']=actor;obj['UE_source_actor_package']=source
        geometry_objects=len(coll.all_objects)
        add_lights(coll,lights,preview_scale)
        if scene.camera!=old_camera: raise ValueError('Unexpected active camera change')
        objects=list(coll.all_objects)
        if not objects: raise ValueError('No supported legacy scene objects')
        report=dict(source=str(path),package_profile=meta['ue4'],status='bounded_legacy_scene_preview',source_dependencies=dependencies,strict_dependencies=strict_dependencies,
            stages={'geometry':geo,'lighting':dict(records=lights,skipped=skipped,scope='Directional light preview and sky marker; no sky environment evaluation')},
            counts=dict(geometry_objects=geometry_objects,lighting_objects=len(lights),objects=len(objects),meshes=sum(o.type=='MESH' for o in objects),armatures=sum(o.type=='ARMATURE' for o in objects),lights=sum(o.type=='LIGHT' for o in objects),cameras=sum(o.type=='CAMERA' for o in objects)),
            coverage=coverage(rows,objects),foliage_instances=geo['foliage_report']['instances'],material_status=dict(Counter(v['status'] for v in geo.get('material_report',{}).get('packages',{}).values())),
            scope='Legacy saved geometry, decoded foliage profile, components and material graphs; directional light preview only. No sky, fog, postprocessing, runtime or UE5 instance parity.')
        coll.name='UE Scene — '+path.stem; text=bpy.data.texts.new(coll.name+' - scene transfer.json');text.write(json.dumps(report,indent=2));coll['UE_report']=text.name;coll['UE_full_scene_source']=str(path);coll['UE_preview_only']=True
        return coll,report
    except Exception:
        scene.camera=old_camera;rollback_new(before);raise
