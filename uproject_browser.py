"""Native project map selection; delegates reconstruction to the existing reader."""
from pathlib import Path
import json
import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, CollectionProperty, PointerProperty


def discover_maps(descriptor):
    path = Path(descriptor).expanduser().resolve()
    if path.suffix.lower() != '.uproject' or not path.is_file():
        raise ValueError('Select an existing .uproject file')
    with path.open(encoding='utf-8-sig') as stream:
        metadata = json.load(stream)
    if not isinstance(metadata, dict):
        raise ValueError('Invalid project descriptor')
    root = (path.parent / 'Content').resolve()
    if not root.is_dir():
        raise ValueError('Project Content directory is missing')
    maps = []
    for entry in root.rglob('*'):
        if entry.suffix.lower() != '.umap' or not entry.is_file():
            continue
        if not entry.resolve().is_relative_to(root):
            continue
        relative = entry.relative_to(root)
        if any(part in ('__ExternalActors__', '__ExternalObjects__') for part in relative.parts):
            continue
        maps.append((relative.as_posix(), str(entry.resolve())))
    return str(path), str(metadata.get('EngineAssociation') or 'Unknown'), sorted(maps)


class UEIMPORT_Map(bpy.types.PropertyGroup):
    name: StringProperty()
    filepath: StringProperty()


class UEIMPORT_Settings(bpy.types.PropertyGroup):
    project_path: StringProperty(name='Project', subtype='FILE_PATH')
    scanned_project: StringProperty(options={'HIDDEN'})
    engine: StringProperty(options={'HIDDEN'})
    maps: CollectionProperty(type=UEIMPORT_Map)
    active: IntProperty(default=0, min=0)
    materials: BoolProperty(name='Materials', default=True)


class UEIMPORT_OT_scan(bpy.types.Operator):
    bl_idname = 'ueimport.scan_project'
    bl_label = 'Scan Unreal Project'

    def execute(self, context):
        state = context.scene.ueimport_project
        state.maps.clear()
        state.scanned_project = ''
        state.engine = ''
        state.active = 0
        try:
            project, engine, maps = discover_maps(bpy.path.abspath(state.project_path))
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        state.scanned_project, state.engine = project, engine
        for name, filepath in maps:
            item = state.maps.add()
            item.name, item.filepath = name, filepath
        self.report({'INFO'}, f'Found {len(maps)} maps')
        return {'FINISHED'}


class UEIMPORT_OT_import_map(bpy.types.Operator):
    bl_idname = 'ueimport.import_selected_map'
    bl_label = 'Import Selected Map'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        state = context.scene.ueimport_project
        return 0 <= state.active < len(state.maps)

    def execute(self, context):
        state = context.scene.ueimport_project
        try:
            project, engine, maps = discover_maps(bpy.path.abspath(state.project_path))
            if project != state.scanned_project:
                raise ValueError('Project changed; scan again')
            selected = state.maps[state.active].filepath
            if selected not in {filepath for _, filepath in maps}:
                raise ValueError('Map changed or is missing; scan again')
            import umap
            umap.LoadUMap(selected, umap.UMapImportSettings(materials=state.materials))
        except Exception as exc:
            self.report({'ERROR'}, f'Import failed: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, 'Map import completed; inspect console for asset warnings')
        return {'FINISHED'}


class UEIMPORT_OT_reconstruct_static(bpy.types.Operator):
    bl_idname = 'ueimport.reconstruct_static'
    bl_label = 'Reconstruct Static Geometry'
    bl_description = 'Decode native static meshes, keep unresolved actors as empties, and write an import report; no materials'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        state = context.scene.ueimport_project
        try:
            project, _, maps = discover_maps(bpy.path.abspath(state.project_path))
            if project != state.scanned_project:
                raise ValueError('Project changed; scan again')
            selected = state.maps[state.active].filepath
            if selected not in {path for _, path in maps}:
                raise ValueError('Map changed or is missing; scan again')
            from static_scene import reconstruct_static_map
            collection, report = reconstruct_static_map(selected)
        except Exception as exc:
            self.report({'ERROR'}, f'Reconstruction failed: {exc}')
            return {'CANCELLED'}
        count = report['actor_status'].get('reconstructed', 0)
        self.report({'INFO'}, f'{count}/{report["static_actors"]} static actors reconstructed; report: {collection["UE_report"]}')
        return {'FINISHED'}


class UEIMPORT_PT_project(bpy.types.Panel):
    bl_label = 'Unreal Project Importer'
    bl_idname = 'UEIMPORT_PT_project'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Unreal'

    def draw(self, context):
        state = context.scene.ueimport_project
        layout = self.layout
        layout.prop(state, 'project_path')
        layout.operator('ueimport.scan_project', icon='FILE_REFRESH')
        if state.scanned_project:
            layout.label(text=f'Engine: {state.engine}')
            layout.label(text=f'Maps: {len(state.maps)}')
            layout.template_list('UI_UL_list', 'unreal_maps', state, 'maps', state, 'active', rows=5)
            layout.prop(state, 'materials')
            layout.operator('ueimport.import_selected_map', icon='IMPORT')
            layout.separator()
            layout.operator('ueimport.reconstruct_static', icon='MESH_DATA')
            layout.label(text='Geometry only; missing assets remain empties.')
            layout.label(text='Legacy UE4 reader; UE5 not yet supported.')


CLASSES = (UEIMPORT_Map, UEIMPORT_Settings, UEIMPORT_OT_scan, UEIMPORT_OT_import_map, UEIMPORT_OT_reconstruct_static, UEIMPORT_PT_project)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ueimport_project = PointerProperty(type=UEIMPORT_Settings)


def unregister():
    del bpy.types.Scene.ueimport_project
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
