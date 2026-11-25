"""Native UE4 static actor layout preview, not geometry import."""
import bpy
import uasset
import umap
from collections import Counter


def import_layout(filepath):
    """Read actual static actor root transforms; do not load missing dependencies."""
    collection = bpy.data.collections.new('Unreal layout — ' + bpy.path.display_name_from_filepath(filepath))
    bpy.context.scene.collection.children.link(collection)
    actors = []
    roots = {}
    skipped = []
    with uasset.UAsset(filepath) as asset:
        for export in asset.exports:
            if export.export_class_type != 'StaticMeshActor':
                continue
            try:
                export.ReadProperties(True)
                root = export.properties.TryGetValue('RootComponent')
                component = export.properties.TryGetValue('StaticMeshComponent')
                if root is None or component is None:
                    raise ValueError('missing root or mesh component')
                root.ReadProperties(False)
                component.ReadProperties(False)
                mesh = component.properties.TryGetValue('StaticMesh')
                if mesh is None or mesh.import_ref is None:
                    raise ValueError('missing external mesh reference')
                path = mesh.import_ref.object_name
                obj = bpy.data.objects.new(export.properties.TryGetValue('ActorLabel', export.object_name), None)
                collection.objects.link(obj)
                obj.empty_display_type = 'ARROWS'
                obj.empty_display_size = 0.35
                obj.rotation_mode = 'YXZ'
                obj['UE_actor'] = export.object_name
                obj['UE_mesh_package'] = path
                obj['UE_preview_only'] = True
                umap.Transform(root, obj)
                actors.append((root, obj))
                roots[id(root)] = obj
            except Exception as exc:
                skipped.append((export.object_name, str(exc)))
        # Assign parent links in a separate pass: serialized order is not hierarchy order.
        unresolved = []
        for root, obj in actors:
            parent = root.properties.TryGetValue('AttachParent')
            if parent is not None:
                target = roots.get(id(parent))
                if target is not None and target != obj:
                    obj.parent = target
                else:
                    unresolved.append(obj['UE_actor'])
                    obj['UE_unresolved_parent'] = parent.object_name
    report = {'static_actors': len(actors), 'unique_mesh_packages': len({o['UE_mesh_package'] for _, o in actors}),
              'skipped': skipped, 'unresolved_parents': unresolved}
    return collection, report
