"""Import verified cooked reference-skeleton profiles without Unreal Engine."""
import bpy
from bpy.props import EnumProperty, StringProperty
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
    bl_label='Import UE4.18 native skeletal mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    def execute(self,context):
        from skeletal_mesh_native import read_mesh, build_mesh
        try:
            data=read_mesh(self.filepath); obj,arm=build_mesh(data)
            obj['UE_source_package']=self.filepath
            self.report({'INFO'},f"Imported {len(data['positions'])} skinned vertices, {len(data['bones'])} bones (material placeholders)")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


def menu(self,context):
    self.layout.operator(ImportUESkeleton.bl_idname,text='UE Reference Skeleton (.uasset)')
    self.layout.operator(ImportUESkeletalMesh.bl_idname,text='UE4.18 Native Skeletal Mesh (.uasset)')
def register():
    bpy.utils.register_class(ImportUESkeleton); bpy.utils.register_class(ImportUESkeletalMesh); bpy.types.TOPBAR_MT_file_import.append(menu)
def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu); bpy.utils.unregister_class(ImportUESkeletalMesh); bpy.utils.unregister_class(ImportUESkeleton)
