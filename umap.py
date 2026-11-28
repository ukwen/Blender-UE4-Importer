import bpy, os, sys, math, time, zlib
from dataclasses import dataclass
from mathutils import *

cur_dir = os.path.dirname(__file__)
if cur_dir not in sys.path: sys.path.append(cur_dir)

import uasset, umat, umesh
from uasset import UAsset, Import, Export, FVector, FColor
from umat import TryGetUMaterialImport
from umesh import ImportMeshUAsset

hide_noncasting = False
deg2rad = math.radians(1)

@dataclass
class UMapImportSettings():
    folders:          bool  = True
    meshes:           bool  = True
    materials:        bool  = True
    cameras:          bool  = True
    lights_point:     bool  = False
    lights_spot:      bool  = True
    lights_dir:       bool  = True
    cubemaps:         bool  = True
    lightprobes:      bool  = True
    force_shadows:    bool  = False
    light_intensity:  float = 1
    light_angle_coef: float = 1

def SetupObjectFull(cfg:UMapImportSettings, export:Export, data=None, name=None):
    parent_coll = bpy.context.collection
    if cfg.folders and (folder_path := export.properties.TryGetValue('FolderPath')):
        for folder in folder_path.split('/'):
            if (coll := bpy.data.collections.get(folder)) == None:
                coll = bpy.data.collections.new(folder)
                parent_coll.children.link(coll)
            parent_coll = coll

    return SetupObject(name if name else export.properties.TryGetValue('ActorLabel', export.object_name), data, parent_coll)
def SetupObject(name, data, collection):
    obj = bpy.data.objects.new(name, data)
    obj.rotation_mode = 'YXZ'
    obj.empty_display_type = 'ARROWS'
    collection.objects.link(obj)
    return obj
def Transform(export:Export, obj, pitch_offset=0, def_scale=FVector(1,1,1), scale=1):
    props = export.properties

    # Unreal: X+ Forward, Y+ Right, Z+ Up     Blender: X+ Right, Y+ Forward, Z+ Up
    if rel_loc := props.TryGetValue('RelativeLocation'): obj.location = Vector((rel_loc.y,rel_loc.x,rel_loc.z)) * 0.01
    
    # Unreal: Roll, Pitch, Yaw     File: Pitch, Yaw, Roll     Blender: Pitch, Roll, -Yaw     0,0,0 = fwd, down for lights
    if rel_rot := props.TryGetValue('RelativeRotation'):
        eu1 = Euler((pitch_offset*deg2rad, 0, 0), 'YXZ')
        eu1.rotate(Euler((rel_rot.x*deg2rad, rel_rot.z*deg2rad, -rel_rot.y*deg2rad), 'YXZ'))
        obj.rotation_euler = eu1

    rel_scale = props.TryGetValue('RelativeScale3D', def_scale)
    obj.scale = Vector((rel_scale.y,rel_scale.x,rel_scale.z)) * scale
def Parent(export:Export, obj):
    if attach := export.properties.TryGetValue('AttachParent'): # TODO: unify?
        assert hasattr(attach, 'bl_obj')
        obj.parent = attach.bl_obj
        parent_coll = obj.parent.users_collection[0]
        if parent_coll != obj.users_collection[0]: parent_coll.objects.link(obj)
def TryApplyRootComponent(export:Export, obj, pitch_offset=0, def_scale=FVector(1,1,1), scale=1):
    if root_export := export.properties.TryGetValue('RootComponent'):
        root_export.ReadProperties(False)
        Parent(root_export, obj)
        Transform(root_export, obj, pitch_offset, def_scale, scale)
        root_export.bl_obj = obj
        return True
    return False
def TryGetMesh(static_mesh_comp:Export, m_type, import_materials=True):
    mesh = None
    if mesh_prop := static_mesh_comp.properties.TryGetValue(m_type):
        mesh_name = mesh_prop.object_name
        mesh = bpy.data.meshes.get(mesh_name)
        if not mesh or not mesh.get('UAsset'):
            if mesh_import := mesh_prop.import_ref:
                mesh_path = static_mesh_comp.asset.ToProjectPath(mesh_import.object_name)
                mesh = ImportMeshUAsset(mesh_path, static_mesh_comp.asset.uproject, import_materials)
                if not mesh: print(f"Failed to get Mesh \"{mesh_path}\"")
        if import_materials:
            mat_overrides:list[Import] = static_mesh_comp.properties.TryGetValue('OverrideMaterials')
            if mat_overrides and mesh is not None:
                hash = 1
                for mat_override in mat_overrides: hash = zlib.adler32(str.encode(mat_override.value.object_name if mat_override.value else "None"), hash)
                override_mesh_name = f"{mesh_name}_{hash:X}"
                if override_mesh := bpy.data.meshes.get(override_mesh_name): mesh = override_mesh
                else:
                    mesh = mesh.copy()
                    mesh.name = override_mesh_name
                    c_override = len(mat_overrides)
                    if c_override > len(mesh.materials): print(f"Error: More overrides ({c_override}) than materials ({len(mesh.materials)})")
                    else:
                        for i in range(c_override):
                            if mat_override := mat_overrides[i].value: mesh.materials[i] = TryGetUMaterialImport(mat_override, mesh)
    return mesh
def ProcessUMapExport(export:Export, cfg:UMapImportSettings):
    if type(export.export_class) is not uasset.Import: return
    match export.export_class.class_name:
        case 'Class':
            match export.export_class_type:
                case 'StaticMeshActor':
                    export.ReadProperties(True)
                    mesh_comp = export.properties.TryGetValue('StaticMeshComponent') if cfg.meshes else None
                    mesh = TryGetMesh(mesh_comp, 'StaticMesh', cfg.materials) if mesh_comp else None
                    obj = SetupObjectFull(cfg, export, mesh)
                    TryApplyRootComponent(export, obj)
                case 'SkeletalMeshActor':
                    export.ReadProperties(True)
                    mesh_comp = export.properties.TryGetValue('SkeletalMeshComponent') if cfg.meshes else None
                    mesh = TryGetMesh(mesh_comp, 'SkeletalMesh', cfg.materials) if mesh_comp else None
                    obj = bpy.data.objects.get(mesh.name) if mesh else None
                    if obj is None:
                        obj = SetupObjectFull(cfg, export, mesh)
                    #obj = SetupObject(export.object_name, mesh) # TODO
                    TryApplyRootComponent(export, obj)
                case 'PointLight' | 'SpotLight' | 'DirectionalLight':
                    rot_off = 90
                    light_intensity = cfg.light_intensity
                    match export.export_class_type:
                        case 'PointLight':
                            if not cfg.lights_point: return
                            light_type = 'POINT'
                        case 'SpotLight':
                            if not cfg.lights_spot: return
                            light_type = 'SPOT'
                        case 'DirectionalLight':
                            if not cfg.lights_dir: return
                            light_type = 'SUN'
                            light_intensity *= 100
                            rot_off = 0

                    export.ReadProperties(True)

                    light = bpy.data.lights.new(export.object_name, light_type)
                    obj = SetupObjectFull(cfg, export, light)
                    TryApplyRootComponent(export, obj, rot_off) # Blender lights are cursed, local Z- Forward, Y+ Up, X+ Right
                    
                    if export.export_class_type == 'DirectionalLight': obj.rotation_euler.rotate_axis('X', math.radians(90))
                    
                    if light_comp := export.properties.TryGetValue('LightComponent'): # Export
                        light_props = light_comp.properties
                        light.energy = 0.01 * light_intensity * light_props.TryGetValue('Intensity', 5000) # pre 4.19 is unitless
                        color:FColor = light_props.TryGetValue('LightColor', FColor(255,255,255,255))
                        light.color = Color((color.r,color.g,color.b)) / 255.0
                        cast = light_props.TryGetValue('CastShadows', True)
                        light.use_shadow = cast or cfg.force_shadows
                        if not cast and hide_noncasting: obj.hide_viewport = obj.hide_render = True
                        light.shadow_soft_size = light_props.TryGetValue('SourceRadius', 0.05)

                        if light_type == 'SPOT':
                            outer_angle = light_props.TryGetValue('OuterConeAngle', 44)
                            inner_angle = light_props.TryGetValue('InnerConeAngle', 0)
                            light.spot_size = 2 * cfg.light_angle_coef * outer_angle * deg2rad
                            light.spot_blend = 1 - (inner_angle / outer_angle)
                case 'BoxReflectionCapture':
                    if not cfg.cubemaps: return
                    export.ReadProperties(False)

                    probe = bpy.data.lightprobes.new(export.object_name, 'SPHERE')
                    probe.influence_type = 'BOX'
                    probe.influence_distance = 1

                    if (cap_props := export.properties.TryGetProperties('CaptureComponent')) and (box_props := cap_props.TryGetProperties('PreviewCaptureBox')):
                        if box_ext := box_props.TryGetValue('BoxExtent'): probe.falloff = 1 - max(box_ext.x, max(box_ext.y, box_ext.z))

                    obj = SetupObjectFull(cfg, export, probe)
                    TryApplyRootComponent(export, obj, def_scale=FVector(1000,1000,400), scale=0.01)

                    if cfg.lightprobes:
                        irr = bpy.data.lightprobes.new(export.object_name, 'VOLUME')
                        if hasattr(irr, 'influence_distance') and probe.falloff < 1:
                            irr.influence_distance = 1 / (1 - probe.falloff) - 1
                        obj2 = SetupObjectFull(cfg, export, irr, f"{export.object_name}_irridance")
                        TryApplyRootComponent(export, obj2, def_scale=FVector(1000,1000,400), scale=0.01*(1 - probe.falloff))
                case 'SphereReflectionCapture':
                    if not cfg.cubemaps: return
                    export.ReadProperties(False)

                    probe = bpy.data.lightprobes.new(export.object_name, 'SPHERE')
                    probe.influence_type = 'ELIPSOID'
                    if cap_comp := export.properties.TryGetProperties('CaptureComponent'): probe.influence_distance = cap_comp.TryGetValue('InfluenceRadius', 3000) * 0.01
                    
                    obj = SetupObjectFull(cfg, export, probe)
                    TryApplyRootComponent(export, obj)
                case 'CameraActor':
                    if cfg.cameras:
                        export.ReadProperties(True)
                        if cam_props := export.properties.TryGetProperties('CameraComponent'): h_fov = cam_props.TryGetValue('FieldOfView', 90)
                        else: h_fov = 90

                        cam = bpy.data.cameras.new(name=export.object_name)
                        cam.display_size, cam.sensor_fit, cam.lens_unit = (0.5, 'HORIZONTAL', 'FOV')
                        cam.angle = math.radians(h_fov)

                        obj = SetupObjectFull(cfg, export, cam)
                        TryApplyRootComponent(export, obj, 90)
                case 'Actor':
                    export.ReadProperties(False)
                    obj = SetupObjectFull(cfg, export)
                    TryApplyRootComponent(export, obj)
                #case _: print(f"Skipping \"{export.export_class_type}\"")
        case 'BlueprintGeneratedClass':
            export.ReadProperties(True)

            bp_obj = SetupObjectFull(cfg, export)
            TryApplyRootComponent(export, bp_obj)

            if bp_comps := export.properties.TryGetValue('BlueprintCreatedComponents'):
                if not hasattr(export.asset, 'import_cache'): export.asset.import_cache = {}

                bp_path = export.export_class.import_ref.object_name
                if bp_path.startswith("/Engine/"): return
                if not (bp_asset := export.asset.import_cache.get(bp_path)):
                    bp_asset = UAsset(export.asset.ToProjectPath(bp_path), False, export.asset.uproject)
                    bp_asset = bp_asset.__enter__()
                    bp_asset.EnsureIndexExports()
                    export.asset.import_cache[bp_path] = bp_asset
                
                for comp in bp_comps:
                    child_export = comp.value
                    #ProcessUMapExport(child_export) # TODO? Can't, need to partly process gend_exp & child_export
                    if child_export.export_class_type == 'StaticMeshComponent': # TODO: other components
                        gend_exp = bp_asset.name2exp.get(f"{child_export.object_name}_GEN_VARIABLE")
                        if gend_exp:
                            gend_exp.ReadProperties()

                            mesh = TryGetMesh(gend_exp, 'StaticMesh', cfg.materials) if cfg.meshes else None
                            child_export.bl_obj = obj = SetupObjectFull(cfg, child_export, mesh)

                            Parent(child_export, obj)
                            Transform(gend_exp, obj)
def LoadUMap(filepath, cfg=UMapImportSettings()):
    t0 = time.time()

    obj_count   = len(bpy.data.objects)
    mesh_count  = len(bpy.data.meshes)
    mat_count   = len(bpy.data.materials)
    light_count = len(bpy.data.lights)

    with UAsset(filepath) as asset:
        bpy.context.window_manager.progress_begin(0, len(asset.exports))

        if cfg.folders:
            map_coll = bpy.data.collections.new(os.path.splitext(os.path.basename(filepath))[0])
            bpy.context.scene.collection.children.link(map_coll)
            bpy.context.view_layer.active_layer_collection = bpy.context.view_layer.layer_collection.children[map_coll.name]

        try:
            for i, export in enumerate(asset.exports):
                ProcessUMapExport(export, cfg)
                bpy.context.window_manager.progress_update(i)
        finally:
            bpy.context.window_manager.progress_end()
    if hasattr(asset, 'import_cache'):
        for imp_asset in asset.import_cache.values(): imp_asset.Close()
    print(f"Imported {asset}: {(time.time() - t0) * 1000:.2f}ms")
    print(f"{len(bpy.data.objects) - obj_count} Objects, {len(bpy.data.meshes) - mesh_count} Meshes, {len(bpy.data.materials) - mat_count} Materials, {len(bpy.data.lights) - light_count} Lights")
    if len(bpy.data.lights) > 128: print(f"Warning, Exceeded Eevee's 128 Light Limit! ({len(bpy.data.lights)})")
