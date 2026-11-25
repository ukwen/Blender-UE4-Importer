"""Native editor source acceptance with public exact-blob fixtures and controlled binding."""
import hashlib, os, shutil, sys, tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset, umat, texture_blender, editor_texture
root=Path(os.environ['UE_EDITOR_TEXTURES'])
fixtures=[('T_DevPatterns.uasset','ccee499bf811bc17ddbaed52bbab9f88b575afad',64,False,True),('T_Black_32_D.uasset','e6a8080570ae07b9d572362e7df972a40cd20e46',32,True,False)]
for name,sha,dim,srgb,nearest in fixtures:
    src=root/name; data=src.read_bytes()
    assert hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()==sha
    png,meta=editor_texture.read_editor_texture(src)
    assert meta['width']==meta['height']==dim and meta['source_png'] and meta['srgb']==srgb and meta['nearest']==nearest
    # Destroy the thumbnail signature only; source decode must remain byte-identical.
    with tempfile.TemporaryDirectory() as tmp:
        variant=Path(tmp)/name; damaged=bytearray(data); damaged[data.index(editor_texture.PNG)]=0
        variant.write_bytes(damaged)
        assert editor_texture.read_editor_texture(variant)[0]==png
    image=texture_blender.load_editor_texture(src)
    assert image.packed_file.data==png and tuple(image.size)==(dim,dim)
    assert image.colorspace_settings.name==('sRGB' if srgb else 'Non-Color')
    assert texture_blender.load_editor_texture(src)==image
    image.use_fake_user=True
    print('EDITOR_TEXTURE_PASS',name,dim,len(png),image.colorspace_settings.name)
with tempfile.TemporaryDirectory() as tmp:
    project=Path(tmp); (project/'Content').mkdir(); (project/'P.uproject').write_text('{}')
    src=project/'Content/T_DevPatterns.uasset'; shutil.copy(root/fixtures[0][0],src)
    up=uasset.UProject(str(src)); ref=SimpleNamespace(import_ref=SimpleNamespace(object_name='/Game/T_DevPatterns'),asset=SimpleNamespace(ToProjectPath=up.resolve_package,uproject=up))
    # Exercise the actual existing material texture lookup path with a controlled reference.
    with patch.object(umat.subprocess,'run',side_effect=AssertionError('No UModel allowed')):
        image=umat.TryGetExtractedImport(ref,str(project/'Export'))
        assert image and image.packed_file and not (project/'Export').exists()
        assert umat.TryGetExtractedImport(ref,str(project/'Export'))==image
    mat=bpy.data.materials.new('EditorTextureBinding'); mat.use_nodes=True
    node=mat.node_tree.nodes.new('ShaderNodeTexImage'); umat.SetNodeTexture(node,image)
    mat.node_tree.links.new(node.outputs['Color'],mat.node_tree.nodes['Principled BSDF'].inputs['Base Color'])
    assert node.image==image and node.interpolation=='Closest'
    bpy.ops.mesh.primitive_plane_add(); bpy.context.object.data.materials.append(mat)
    # Same name but different package path must not share the cached image.
    other=project/'Content/Other'; other.mkdir(); duplicate=other/src.name
    shutil.copy(root/fixtures[1][0],duplicate)
    different=texture_blender.load_editor_texture(duplicate)
    assert different!=image and tuple(different.size)==(32,32)
    bpy.data.images.remove(different)
    # Corrupt genuine payload cannot be accepted even if thumbnail is intact.
    bad=project/'Content/Corrupt.uasset'; data=bytearray(src.read_bytes()); data[-8]^=0xff; bad.write_bytes(data)
    try: editor_texture.read_editor_texture(bad)
    except (ValueError, OSError, RuntimeError) as exc: print('CORRUPT_SOURCE_REJECTED',type(exc).__name__)
    else: raise AssertionError('Corrupt source accepted')
    out=os.environ['UE_EDITOR_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out)
print('MATERIAL_TEXTURE_BIND_PASS')
