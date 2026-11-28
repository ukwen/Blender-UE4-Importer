"""Registration of owned Blender classes and menus; no global driver namespace."""
import bpy


def register(classes, menu, callback):
    registered = []
    try:
        for cls in classes:
            bpy.utils.register_class(cls)
            registered.append(cls)
        menu.append(callback)
    except Exception:
        for cls in reversed(registered):
            bpy.utils.unregister_class(cls)
        raise


def unregister(classes, menu, callback):
    menu.remove(callback)
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
