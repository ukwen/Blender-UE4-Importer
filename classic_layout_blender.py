"""Build editable static actor placements using typed classic source records."""
import json
import math
import bpy
from mathutils import Euler, Vector
from classic_actor_layout import inspect_layout, parent_links


def apply_transform(obj, location, rotation, scale):
    x, y, z = location
    obj.location = Vector((y, x, z)) * .01
    pitch, yaw, roll = rotation
    obj.rotation_mode = 'YXZ'
    obj.rotation_euler = Euler(tuple(math.radians(v) for v in (pitch, roll, -yaw)), 'YXZ')
    x, y, z = scale
    obj.scale = (y, x, z)


def import_classic_layout(filepath, mesh_resolver=None):
    actors, skipped = inspect_layout(filepath)
    links, unresolved = parent_links(actors)
    collection = bpy.data.collections.new('Unreal layout — ' + bpy.path.display_name_from_filepath(filepath))
    bpy.context.scene.collection.children.link(collection)
    objects = {}
    for actor in actors:
        obj = None
        try:
            geometry, status = mesh_resolver(actor.package) if mesh_resolver else (None, 'layout_only')
            obj = bpy.data.objects.new(actor.label, geometry)
            collection.objects.link(obj)
            if geometry is None:
                obj.empty_display_type = 'ARROWS'
                obj.empty_display_size = 0.35
            obj['UE_actor'] = actor.actor
            obj['UE_mesh_package'] = actor.package
            obj['UE_preview_only'] = geometry is None
            obj['UE_geometry_status'] = status
            if actor.override_names:
                obj['UE_material_overrides'] = list(actor.override_names)
                obj['UE_material_override_packages'] = json.dumps(actor.override_packages)
            apply_transform(obj, actor.location, actor.rotation, actor.scale)
            objects[actor.root_index] = obj
        except Exception as exc:
            if obj is not None:
                bpy.data.objects.remove(obj, do_unlink=True)
            skipped.append((actor.actor, str(exc)))
    missing = []
    for actor in actors:
        obj = objects.get(actor.root_index)
        if obj is None or not actor.parent_index:
            continue
        target = objects.get(links.get(actor.root_index))
        if target is not None:
            obj.parent = target
        else:
            missing.append(actor.actor)
            obj['UE_unresolved_parent'] = actor.parent_name
    return collection, dict(static_actors=len(objects), unique_mesh_packages=len({o['UE_mesh_package'] for o in objects.values()}),
                            skipped=skipped, unresolved_parents=missing)
