bl_info = {
    "name" : "Unreal Engine 4",
    "author" : "Waffle1434",
    "description" : "Import UE4 meshes, materials, & maps.",
    "blender" : (4, 2, 0),
    "version" : (0, 10, 4),
    "location" : "",
    "warning" : "",
    "category" : "Import-Export",
    "doc_url": "https://github.com/ukwen/Blender-UE4-Importer"
}

import os, sys

cur_dir = os.path.dirname(__file__)
if cur_dir not in sys.path: sys.path.append(cur_dir)

import umap, umesh, umat, uproject_browser

def register():
    umat.register()
    umesh.register()
    umap.register()
    uproject_browser.register()

def unregister():
    uproject_browser.unregister()
    umat.unregister()
    umesh.unregister()
    umap.unregister()
