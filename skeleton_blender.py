"""Import verified cooked reference-skeleton profiles without Unreal Engine."""
import bpy
from bpy.props import EnumProperty, StringProperty, FloatProperty
from bpy_extras.io_utils import ImportHelper
from skeleton_native import read_cooked_skeleton, build_armature

class ImportUESkeleton(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_reference_skeleton'
    bl_label='Import UE reference skeleton'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked UE4 profile',items=[('4.18','UE4.18','Tagged split package'),('4.27','UE4.27','Tagged split package')],default='4.27')
    def execute(self,context):
        try:
            name,bones=read_cooked_skeleton(self.filepath,self.profile)
            obj=build_armature(name,bones)
            obj['UE_skeleton_source']=self.filepath; obj['UE_skeleton_profile']=self.profile
            self.report({'INFO'},f'Imported {len(bones)} reference bones (no mesh or skin weights)')
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

class ImportUESkeletalMesh(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_native_skeletal_mesh'
    bl_label='Import native UE4 skeletal mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked UE4 profile',items=[('4.18','UE4.18','Legacy interleaved buffers'),('4.27','UE4.27','Inline separate render buffers')],default='4.18')
    def execute(self,context):
        from skeletal_mesh_native import read_mesh, build_mesh
        try:
            data=read_mesh(self.filepath,self.profile); obj,arm=build_mesh(data)
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
    start_frame: FloatProperty(name='Start frame',default=1.,min=0.,max=100000.)
    @classmethod
    def poll(cls,context):
        return context.object is not None and context.object.type=='ARMATURE' and context.object.mode=='OBJECT'
    def execute(self,context):
        from animation_native import read_animation, make_action
        try:
            data=read_animation(self.filepath)
            action=make_action(context.object,data,context.scene,self.start_frame)
            self.report({'INFO'},f"Imported {data['frames']} raw samples, {len(data['tracks'])} tracks; curves/notifies and compressed data not imported")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError,KeyError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class ImportUECookedStatic(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_cooked_static'
    bl_label='Import native cooked UE4 static mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked UE4 profile',items=[('4.18','UE4.18','Interleaved buffers'),('4.27','UE4.27','Separate inline buffers')],default='4.27')
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


def menu(self,context):
    self.layout.operator(ImportUECookedStatic.bl_idname,text='UE4 Native Cooked Static Mesh (.uasset)')
    self.layout.operator(ImportUESkeleton.bl_idname,text='UE Reference Skeleton (.uasset)')
    self.layout.operator(ImportUESkeletalMesh.bl_idname,text='UE4 Native Skeletal Mesh (.uasset)')
    self.layout.operator(ImportUEAnimation.bl_idname,text='UE4.27 Editor Raw Animation (.uasset)')
def register():
    bpy.utils.register_class(ImportUECookedStatic); bpy.utils.register_class(ImportUESkeleton); bpy.utils.register_class(ImportUESkeletalMesh); bpy.utils.register_class(ImportUEAnimation); bpy.types.TOPBAR_MT_file_import.append(menu)
def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu); bpy.utils.unregister_class(ImportUEAnimation); bpy.utils.unregister_class(ImportUESkeletalMesh); bpy.utils.unregister_class(ImportUESkeleton); bpy.utils.unregister_class(ImportUECookedStatic)
