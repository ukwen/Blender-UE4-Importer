"""Import verified cooked reference-skeleton profiles without Unreal Engine."""
import bpy
from bpy.props import EnumProperty, StringProperty, FloatProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
from skeleton_native import read_cooked_skeleton, build_armature

class ImportUESkeleton(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_reference_skeleton'
    bl_label='Import UE reference skeleton'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Tagged split package'),('4.27','UE4.27','Tagged split package'),('5.0','UE5.0','Bounded unversioned split profile')],default='4.27')
    def execute(self,context):
        try:
            from pathlib import Path
            if Path(self.filepath).with_suffix(".uexp").is_file():
                name,bones=read_cooked_skeleton(self.filepath,self.profile); sockets=[]
            else:
                from editor_skeleton import read_editor_skeleton
                data=read_editor_skeleton(self.filepath); name,bones,sockets=data["name"],data["bones"],data["sockets"]
            obj=build_armature(name,bones)
            if sockets:
                import json
                obj["UE_socket_definitions"]=json.dumps(sockets)
            obj['UE_skeleton_source']=self.filepath; obj['UE_skeleton_profile']=self.profile
            self.report({'INFO'},f'Imported {len(bones)} reference bones (no mesh or skin weights)')
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

class ImportUESkeletalMesh(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_native_skeletal_mesh'
    bl_label='Import native UE skeletal mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Legacy interleaved buffers'),('4.27','UE4.27','Inline separate render buffers'),('5.0','UE5.0','Bounded unversioned split profile')],default='4.18')
    def execute(self,context):
        from skeletal_mesh_native import read_native_mesh, build_mesh
        try:
            data=read_native_mesh(self.filepath,self.profile); obj,arm=build_mesh(data)
            obj['UE_source_package']=self.filepath
            self.report({'INFO'},f"Imported {len(data['positions'])} skinned vertices, {len(data['bones'])} bones (material placeholders)")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class ImportUEAnimation(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_raw_animation'
    bl_label='Import UE4.27 editor raw animation'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    allow_subset: BoolProperty(name='Allow same-skeleton track subset',description='Omit absent tracks only when original skeleton package identity matches; no engine retargeting',default=False)
    start_frame: FloatProperty(name='Start frame',default=1.,min=0.,max=100000.)
    @classmethod
    def poll(cls,context):
        return context.object is not None and context.object.type=='ARMATURE' and context.object.mode=='OBJECT'
    def execute(self,context):
        from animation_native import read_animation, make_action
        try:
            data=read_animation(self.filepath)
            action=make_action(context.object,data,context.scene,self.start_frame,self.allow_subset)
            self.report({'INFO'},f"Imported {data['frames']} raw samples, {len(data['tracks'])} tracks; curves/notifies and compressed data not imported")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError,KeyError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class ImportUECookedStatic(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_cooked_static'
    bl_label='Import native cooked UE static mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Interleaved buffers'),('4.27','UE4.27','Separate inline buffers'),('5.0','UE5.0','Bounded unversioned split profile'),('5.4','UE5.4','Bounded cooked static only'),('5.5','UE5.5','Bounded cooked static only'),('5.6','UE5.6','Bounded cooked static only')],default='4.27')
    def execute(self,context):
        from cooked_static import read_static,build_static
        try:
            data=read_static(self.filepath,self.profile); mesh=build_static(data)
            obj=bpy.data.objects.new(mesh.name,mesh); context.collection.objects.link(obj)
            obj['UE_source_package']=self.filepath
            self.report({'INFO'},f"Imported {len(mesh.vertices)} vertices, {len(mesh.polygons)} triangles (material placeholders)")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class ImportUECookedMaterialInstance(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_cooked_material_instance'
    bl_label='Inspect cooked UE material instance'
    bl_description='Recover native source parameters and package identities; parent shader remains unresolved'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked material profile',items=[('5.4','UE5.4','Bounded instance parameter schema'),('5.6','UE5.6','Bounded instance parameter schema')],default='5.4')
    def execute(self,context):
        from ue5_cooked_material import read_instance,attach_instance_metadata
        mat=None
        try:
            data=read_instance(self.filepath,self.profile)
            mat=bpy.data.materials.new(data['name']);mat['UE_material_package']=data['source_package'];mat.use_fake_user=True
            attach_instance_metadata(mat,data)
            self.report({'INFO'},f"Recovered {len(data['parameters'])} native material parameters; parent shader unresolved")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            if mat is not None: bpy.data.materials.remove(mat)
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class BindUEAccessory(bpy.types.Operator):
    bl_idname='object.ue_bind_accessory'
    bl_label='UE Bind Compatible Skeletal Accessory'
    bl_description='Select one native accessory mesh and its target armature (active). Align in verified reference space; keep original rig'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and context.object is not None and context.object.type=='ARMATURE' and len(context.selected_objects)==2 and any(o.type=='MESH' for o in context.selected_objects)
    def execute(self,context):
        from native_attachments import bind_compatible_accessory
        try:
            mesh=next(o for o in context.selected_objects if o.type=='MESH')
            bind_compatible_accessory(mesh,context.object)
            self.report({'INFO'},'Accessory bound; original armature retained')
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}



class ImportUEPhysics(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_physics_asset'
    bl_label='Import UE Physics Asset (collision preview)'
    bl_description='Attach source collision capsules and joint frames to the selected native rig; does not enable simulation'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and context.object is not None and context.object.type=='ARMATURE' and bool(context.object.get('UE_source_mesh_path'))
    def execute(self,context):
        from physics_native import read_physics,build_physics
        try:
            arm=context.object;data=read_physics(self.filepath);objects=build_physics(arm,data,arm['UE_source_mesh_path'])
            self.report({'INFO'},f"Created {len(objects)} collision/joint preview objects; no simulation enabled")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}

def menu(self,context):
    self.layout.operator(ImportUECookedMaterialInstance.bl_idname,text='UE Cooked Material Instance Parameters (.uasset)')
    self.layout.operator(ImportUEPhysics.bl_idname,text='UE Physics Asset — Collision Preview (.uasset)')
    self.layout.operator(ImportUECookedStatic.bl_idname,text='UE Native Cooked Static Mesh (.uasset)')
    self.layout.operator(ImportUESkeleton.bl_idname,text='UE Reference Skeleton (.uasset)')
    self.layout.operator(ImportUESkeletalMesh.bl_idname,text='UE4 Native Skeletal Mesh (.uasset)')
    self.layout.operator(ImportUEAnimation.bl_idname,text='UE4.27 Editor Raw Animation (.uasset)')
def register():
    import native_sockets
    native_sockets.register()
    bpy.utils.register_class(ImportUECookedMaterialInstance); bpy.utils.register_class(ImportUEPhysics); bpy.utils.register_class(BindUEAccessory); bpy.utils.register_class(ImportUECookedStatic); bpy.utils.register_class(ImportUESkeleton); bpy.utils.register_class(ImportUESkeletalMesh); bpy.utils.register_class(ImportUEAnimation); bpy.types.TOPBAR_MT_file_import.append(menu)
def unregister():
    import native_sockets
    native_sockets.unregister()
    bpy.types.TOPBAR_MT_file_import.remove(menu); bpy.utils.unregister_class(ImportUEAnimation); bpy.utils.unregister_class(ImportUESkeletalMesh); bpy.utils.unregister_class(ImportUESkeleton); bpy.utils.unregister_class(ImportUECookedStatic); bpy.utils.unregister_class(BindUEAccessory); bpy.utils.unregister_class(ImportUEPhysics); bpy.utils.unregister_class(ImportUECookedMaterialInstance)
