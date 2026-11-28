bl_info = {
    "name" : "Unreal Project Importer (UE4/UE5)",
    "author" : "Waffle1434",
    "description" : "Reconstruct supported saved Unreal levels, geometry and materials in Blender.",
    "blender" : (4, 2, 0),
    "version" : (0, 10, 95),
    "location" : "",
    "warning" : "",
    "category" : "Import-Export",
    "doc_url": "https://github.com/ukwen/Blender-UE4-Importer"
}

import os, sys

cur_dir = os.path.dirname(__file__)
if cur_dir not in sys.path: sys.path.append(cur_dir)

import umap, umesh, umat, uproject_browser, texture_blender, wind_preview, skeleton_blender

def register():
    umat.register()
    umesh.register()
    umap.register()
    uproject_browser.register()
    texture_blender.register()
    wind_preview.register()
    skeleton_blender.register()

def unregister():
    skeleton_blender.unregister()
    wind_preview.unregister()
    texture_blender.unregister()
    uproject_browser.unregister()
    umat.unregister()
    umesh.unregister()
    umap.unregister()
