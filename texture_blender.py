"""Blender entry point for explicitly versioned cooked textures; packs image bytes."""
import tempfile
from pathlib import Path
import bpy
from bpy.props import EnumProperty, StringProperty, BoolProperty
from bpy_extras.io_utils import ImportHelper
from native_texture import read_texture, decode_rgba, png_bytes


def load_native_texture(filepath, version, srgb=False, normal=False):
    w,h,fmt,raw,count = read_texture(filepath, version)
    pixels = decode_rgba(w,h,fmt,raw)
    if normal:
        if fmt != 'PF_BC5': raise ValueError('Normal Z reconstruction requires BC5')
        rgba = bytearray(pixels)
        for i in range(0,len(rgba),4):
            x,y = rgba[i]/127.5-1, rgba[i+1]/127.5-1
            rgba[i+2] = round((max(0,1-x*x-y*y)**0.5+1)*127.5)
        pixels = bytes(rgba)
        srgb = False
    with tempfile.TemporaryDirectory() as temp:
        p = Path(temp)/'texture.png'
        p.write_bytes(png_bytes(w,h,pixels))
        image = bpy.data.images.load(str(p), check_existing=False)
        try:
            image.colorspace_settings.name = 'sRGB' if srgb else 'Non-Color'
            image.pack()
            image.filepath = '//'+Path(filepath).stem+'.png'
            image.name = Path(filepath).stem
            image.use_fake_user = True
            image['UE_texture_format'] = fmt
            image['UE_texture_profile'] = version
            image['UE_mips_validated'] = count
            image['UE_normal_z_reconstructed'] = normal
        except Exception:
            bpy.data.images.remove(image)
            raise
    return image


class UEIMPORT_OT_native_texture(bpy.types.Operator, ImportHelper):
    bl_idname = 'ueimport.native_texture'
    bl_label = 'Import Native Cooked Texture'
    bl_description = 'Import and pack a cooked BC1/BC4/BC5 texture with matching sidecars; choose the known asset version'
    filename_ext = '.uasset'
    filter_glob: StringProperty(default='*.uasset', options={'HIDDEN'})
    version: EnumProperty(name='Known asset version', items=[(v,v,'') for v in ('4.18','4.27','5.0')])
    srgb: BoolProperty(name='sRGB color', default=False)
    normal: BoolProperty(name='Reconstruct BC5 normal Z', default=False)

    def execute(self, context):
        try:
            image = load_native_texture(self.filepath, self.version, self.srgb, self.normal)
        except Exception as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        self.report({'INFO'}, f'Packed {image.name}: {image.size[0]} x {image.size[1]}')
        return {'FINISHED'}


def register():
    bpy.utils.register_class(UEIMPORT_OT_native_texture)


def unregister():
    bpy.utils.unregister_class(UEIMPORT_OT_native_texture)
