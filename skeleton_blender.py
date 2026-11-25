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

def menu(self,context): self.layout.operator(ImportUESkeleton.bl_idname,text='UE Reference Skeleton (.uasset)')
def register():
    bpy.utils.register_class(ImportUESkeleton); bpy.types.TOPBAR_MT_file_import.append(menu)
def unregister():
    bpy.types.TOPBAR_MT_file_import.remove(menu); bpy.utils.unregister_class(ImportUESkeleton)
