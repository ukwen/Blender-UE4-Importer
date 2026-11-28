bl_info = {
    "name" : "Unreal Project Importer (UE4/UE5)",
    "author" : "Waffle1434",
    "description" : "Reconstruct supported saved Unreal levels, geometry and materials in Blender.",
    "blender" : (4, 2, 0),
    "version" : (0, 10, 111),
    "location" : "",
    "warning" : "",
    "category" : "Import-Export",
    "doc_url": "https://github.com/ukwen/Blender-UE4-Importer"
}

import os, sys

cur_dir = os.path.dirname(__file__)
if cur_dir not in sys.path: sys.path.append(cur_dir)

import asset_entrypoints, uproject_browser, texture_blender, wind_preview, skeleton_blender

_COMPONENTS = (asset_entrypoints, uproject_browser, texture_blender, wind_preview, skeleton_blender)

def register():
    completed = []
    try:
        for component in _COMPONENTS:
            component.register()
            completed.append(component)
    except Exception:
        for component in reversed(completed):
            component.unregister()
        raise

def unregister():
    for component in reversed(_COMPONENTS):
        component.unregister()
