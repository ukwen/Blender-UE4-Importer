"""One native UE5.6 skeletal rig, shared materials and explicit LOD switching.
No decimation, inferred distances, or changes to previously imported rigs.
"""
from pathlib import Path
from skeletal_mesh_native import require, build_mesh
from ue5_modern_skeletal import read_skeletal56_all


def build_lod_group(path, collection=None):
    import bpy
    data=read_skeletal56_all(path)
    require(len(data)==3 and all(d['lod_index']==i for i,d in enumerate(data)), 'Invalid native LOD group')
    base=data[0]
    require(all(d['bones']==base['bones'] and d['materials']==base['materials'] and d['source_package']==base['source_package'] for d in data),'Incompatible native LOD definitions')
    for d in data: d['source_path']=str(Path(path).resolve())
    collection=collection or bpy.context.collection
    arm=None; objects=[]; materials=[]
    try:
        for i,d in enumerate(data):
            obj,rig=build_mesh(d,collection,_shared_arm=arm,_shared_materials=materials if arm is not None else None)
            if arm is None:
                arm=rig; materials=list(obj.data.materials)
            objects.append(obj); obj.name=f'{base["name"]}_LOD{i}';obj.data.name=obj.name
            obj['UE_lod_group_member']=True
        arm['UE_lod_group_count']=len(objects)
        arm['UE_lod_group_source']=base['source_package']
        set_active_lod(arm,0)
        return arm,objects
    except Exception:
        for obj in reversed(objects):
            mesh=obj.data; bpy.data.objects.remove(obj,do_unlink=True)
            if mesh.users==0: bpy.data.meshes.remove(mesh)
        if arm is not None:
            ar=arm.data; bpy.data.objects.remove(arm,do_unlink=True)
            if ar.users==0: bpy.data.armatures.remove(ar)
        for mat in materials:
            if mat.users==0: bpy.data.materials.remove(mat)
        raise


def members(arm):
    require(arm is not None and arm.type=='ARMATURE' and arm.get('UE_lod_group_count')==3,'Select a native UE LOD group armature')
    rows={}
    for obj in arm.children:
        if not obj.get('UE_lod_group_member'): continue
        require(obj.type=='MESH','Invalid native LOD member')
        idx=obj.data.get('UE_source_lod_index')
        require(idx in (0,1,2) and idx not in rows,'Duplicate or invalid native LOD index')
        require(obj.get('UE_source_mesh_path')==arm.get('UE_source_mesh_path'),'LOD source mismatch')
        mods=[m for m in obj.modifiers if m.type=='ARMATURE']
        require(len(mods)==1 and mods[0].object==arm,'Damaged native LOD skin binding')
        rows[idx]=obj
    require(set(rows)=={0,1,2},'Missing native LOD group member')
    return rows


def set_active_lod(arm,lod):
    """Switch both viewport and render visibility, without modifying pose/action."""
    rows=members(arm)
    require(isinstance(lod,int) and lod in rows,'Invalid native LOD selection')
    require(not any(_visibility_drivers(o) for o in rows.values()),'Disable distance switching before manual LOD selection')
    for i,obj in rows.items():
        obj.hide_viewport=i!=lod;obj.hide_render=i!=lod
    arm['UE_active_lod']=lod


def _visibility_drivers(obj):
    return [f for f in (obj.animation_data.drivers if obj.animation_data else []) if f.data_path in ('hide_viewport','hide_render')]


def _owned_driver(f,arm):
    d=f.driver
    return (d.type=='SCRIPTED' and len(d.variables)==1 and d.variables[0].name=='ue_distance' and d.variables[0].type=='LOC_DIFF' and d.variables[0].targets[0].id==arm)


def enable_distance_lod(arm,camera,near,far):
    """Explicit user-defined world distances in metres; not Unreal screen-size LODs."""
    import math
    rows=members(arm)
    require(camera is not None and camera.type=='CAMERA','Select a scene camera')
    require(math.isfinite(near) and math.isfinite(far) and 0<near<far,'LOD distances must be finite, positive and increasing')
    require(not any(_visibility_drivers(o) for o in rows.values()),'Disable existing LOD visibility drivers before enabling distance switching')
    expressions=[f'ue_distance >= {near!r}',f'ue_distance < {near!r} or ue_distance >= {far!r}',f'ue_distance < {far!r}']
    created=[]; old=[(o,o.hide_viewport,o.hide_render) for o in rows.values()]
    try:
        for i,o in rows.items():
            for path in ('hide_viewport','hide_render'):
                setattr(o,path,False)
                f=o.driver_add(path);created.append((o,path));d=f.driver;d.type='SCRIPTED';v=d.variables.new();v.name='ue_distance';v.type='LOC_DIFF'
                for target,obj in zip(v.targets,(arm,camera)):
                    target.id=obj;target.transform_space='WORLD_SPACE'
                d.expression=expressions[i]
        arm['UE_lod_mode']='CAMERA_DISTANCE';arm['UE_lod_distance_near']=near;arm['UE_lod_distance_far']=far
        if 'UE_active_lod' in arm: del arm['UE_active_lod']
    except Exception:
        for o,path in created: o.driver_remove(path)
        for o,v,r in old: o.hide_viewport=v;o.hide_render=r
        raise


def disable_distance_lod(arm,lod):
    rows=members(arm)
    require(lod in rows,'Invalid native LOD selection')
    drivers=[(o,f) for o in rows.values() for f in _visibility_drivers(o)]
    if drivers:
        require(arm.get('UE_lod_mode')=='CAMERA_DISTANCE' and len(drivers)==6 and all(_owned_driver(f,arm) for o,f in drivers),'Unexpected visibility drivers; refusing to remove user animation')
        for o,f in drivers: o.driver_remove(f.data_path)
    arm['UE_lod_mode']='MANUAL'
    set_active_lod(arm,lod)
