"""Use genuine Matya UAsset Samples, no Unreal or UModel."""
import os, sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from texture_blender import load_native_texture
root=Path(os.environ['MATYA_ASSETS'])
for version in ('4.18','4.27','5.0'):
    for path in sorted((root/version).glob('T_Worm_*.uasset')):
        image=load_native_texture(path,version,srgb=path.stem.endswith('_D'))
        assert tuple(image.size)==(256,256) and image.packed_file
        assert image['UE_mips_validated']==(1 if path.stem.endswith('_N') else 9)
        print('TEXTURE_PASS',version,path.name,image['UE_texture_format'])
image=load_native_texture(root/'4.27/T_Worm_N.uasset','4.27',normal=True)
assert image['UE_normal_z_reconstructed'] and image.colorspace_settings.name=='Non-Color'
# A packed texture attached to a shader survives save/reopen without the sidecar files.
mat=bpy.data.materials.new('NativeTexture'); mat.use_fake_user=True; mat.use_nodes=True
n=mat.node_tree.nodes.new('ShaderNodeTexImage'); n.image=bpy.data.images['T_Worm_D']
mat.node_tree.links.new(n.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
bpy.ops.wm.save_as_mainfile(filepath=os.environ['UE_TEXTURE_OUTPUT'])
bpy.ops.wm.open_mainfile(filepath=os.environ['UE_TEXTURE_OUTPUT'])
assert len([im for im in bpy.data.images if im.get('UE_texture_format') and im.packed_file])==10
assert bpy.data.materials['NativeTexture'].node_tree.nodes.get('Image Texture').image.packed_file
print('NATIVE_TEXTURE_REOPEN_PASS')
