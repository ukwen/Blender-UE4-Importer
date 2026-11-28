"""Native project map selection; delegates reconstruction to the existing reader."""
from pathlib import Path
import json
import time
import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, CollectionProperty, PointerProperty, EnumProperty


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
    enabled: BoolProperty(default=False)
    name: StringProperty()
    filepath: StringProperty()


class UEIMPORT_Job(bpy.types.PropertyGroup):
    package: StringProperty()
    kind: StringProperty()
    enabled: BoolProperty(default=True)
    missing: IntProperty(default=0)


class UEIMPORT_UL_jobs(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True);row.prop(item,'enabled',text='')
        row.label(text=item.package.rsplit('/',1)[-1],icon='FILE_3D')
        row.label(text=item.kind)
        if item.missing: row.label(text=str(item.missing),icon='ERROR')


class UEIMPORT_Settings(bpy.types.PropertyGroup):
    project_path: StringProperty(name='Project', subtype='FILE_PATH')
    scanned_project: StringProperty(options={'HIDDEN'})
    engine: StringProperty(options={'HIDDEN'})
    maps: CollectionProperty(type=UEIMPORT_Map)
    active: IntProperty(default=0, min=0)
    cooked_profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Legacy buffers'),('4.27','UE4.27','Separate buffers'),('5.0','UE5.0','Bounded unversioned split profile'),('5.4','UE5.4','Bounded cooked static only'),('5.5','UE5.5','Bounded cooked static only'),('5.6','UE5.6','Bounded cooked static and skeletal LOD0')],default='4.27')
    strict_scene_dependencies: BoolProperty(name='Require resolved source dependencies',default=False,description='Refuse scene import if known hard/soft package references are missing or dependency tables are unknown; not a visual completeness guarantee')
    light_preview_scale: FloatProperty(name="Light preview multiplier",default=1.,min=.001,max=1000.,description="Approximate Blender preview brightness, not Unreal photometric equivalence")
    geometry_all_lods: BoolProperty(name='All skeletal LODs on one rig',default=False,description='UE5.6: import all supported native render LODs with shared materials')
    geometry_physics: BoolProperty(name='Attach native physics previews',default=False,description='Resolve exact source PhysicsAsset references; missing or unsupported assets are reported without dropping geometry')
    batch_scope: EnumProperty(name='Batch scope',items=[('ALL_MAPS','All maps','Reconstruct all project maps'),('SELECTED_MAP','Selected map','Reconstruct selected map'),('GEOMETRY','Geometry folder','Native geometry inspection gallery'),('MAP_GEOMETRY','Selected map geometry','Import only known geometry dependencies of selected map into a gallery')],default='ALL_MAPS')
    job_items: CollectionProperty(type=UEIMPORT_Job)
    job_active: IntProperty(default=0,min=0)
    catalog_key: StringProperty(options={'HIDDEN'})
    recovery_copy: BoolProperty(name='Save recovery copy before batch',description='Optional full Blender scene backup beside the saved file; does not overwrite the active file',default=False)
    use_job_selection: BoolProperty(name='Use checked jobs only',default=False)
    job_filter: StringProperty(name='Asset name filter', description='Case-insensitive package path substring; blank selects all jobs')
    batch_status: StringProperty(options={'HIDDEN'})
    batch_report: StringProperty(options={'HIDDEN'})
    scene_summary: StringProperty(options={'HIDDEN'})
    scene_summary_source: StringProperty(options={'HIDDEN'})
    scene_action_report: StringProperty(options={'HIDDEN'})
    geometry_folder: StringProperty(name='Content subfolder',description='Relative to Content; empty imports all supported geometry assets')
    materials: BoolProperty(name='Materials', default=True)
    components: BoolProperty(name='Include Blueprint and skeletal components', default=False, description='Reconstruct map-owned component hierarchies; unresolved defaults and sockets stay diagnostic')
    static_materials: BoolProperty(name='Bind materials (experimental)', default=False)
    partial_materials: BoolProperty(name='Keep incomplete surface previews', default=False, description='Keep connected material graphs with resolved surface images; missing functions and unsupported effects remain marked')


class UEIMPORT_OT_scan(bpy.types.Operator):
    bl_idname = 'ueimport.scan_project'
    bl_label = 'Scan Unreal Project'

    def execute(self, context):
        state = context.scene.ueimport_project
        state.maps.clear()
        state.scanned_project = ''
        state.engine = ''
        state.active = 0
        state.scene_summary = state.scene_summary_source = state.scene_action_report = ''
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
            if any(c.get('UE_full_scene_source')==selected for c in context.scene.collection.children_recursive):
                raise ValueError('Level already imported as a full scene')
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
    bl_description = 'Decode native static meshes, keep unresolved actors as empties, and write an import report; optional material binding'
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
            collection, report = reconstruct_static_map(selected, materials=state.static_materials, allow_partial_materials=state.partial_materials, cooked_profile=state.cooked_profile, components=state.components)
        except Exception as exc:
            self.report({'ERROR'}, f'Reconstruction failed: {exc}')
            return {'CANCELLED'}
        count = report['actor_status'].get('reconstructed', 0)
        foliage = report.get('foliage_report', {}).get('instances', 0)
        components = report.get('component_report', {}).get('status', {}).get('reconstructed', 0)
        characters=report.get('character_report',{}).get('status',{}); bodies=characters.get('reconstructed',0)+characters.get('geometry_only_unresolved_slots',0)
        self.report({'INFO'}, f'{count}/{report["static_actors"]} static actors; {foliage} foliage instances; {components} mesh components; {bodies} skeletal bodies; report: {collection["UE_report"]}')
        return {'FINISHED'}


def publish_scene_actions(state, selected, dependencies, performance=None):
    from import_workflow import dependency_actions
    actions=dependencies.get('actions') or dependency_actions(dependencies)
    lines=[str(selected), 'Source availability (not visual completeness)',
           f"{actions['unresolved_packages']} unresolved packages; {len(actions['unknown_tables'])} unknown tables"]
    for r in actions['packages']:
        lines.append(f"{r['package']} | {r['status']} | hard: {r['hard_references']}, soft: {r['soft_references']} | {r['action']}")
    if actions['unknown_tables']:
        lines.append('Unknown package tables:');lines.extend(actions['unknown_tables'])
    if performance:
        lines.append(f"Import: {performance['elapsed_seconds']:.2f}s; {performance['table_reads']} table reads; {performance['table_hits']} cache hits")
        lines.extend(f"{name}: {seconds:.3f}s" for name,seconds in performance['stage_seconds'].items())
    text=bpy.data.texts.new(Path(selected).stem+' — source actions.txt');text.write('\n'.join(lines)+'\n')
    state.scene_summary_source=str(selected);state.scene_action_report=text.name
    state.scene_summary=f"{actions['unresolved_packages']} missing/invalid packages; {len(actions['unknown_tables'])} unknown tables"
    if performance:state.scene_summary+=f" | {performance['elapsed_seconds']:.1f}s"


class UEIMPORT_OT_copy_scene_actions(bpy.types.Operator):
    bl_idname='ueimport.copy_scene_actions'
    bl_label='Copy Source Action Report'
    @classmethod
    def poll(cls,context):
        s=context.scene.ueimport_project
        return UEIMPORT_OT_import_map.poll(context) and s.scene_summary_source==s.maps[s.active].filepath and bpy.data.texts.get(s.scene_action_report) is not None
    def execute(self,context):
        s=context.scene.ueimport_project
        context.window_manager.clipboard=bpy.data.texts[s.scene_action_report].as_string()
        self.report({'INFO'},'Source action report copied');return {'FINISHED'}


class UEIMPORT_OT_scene_dependencies(bpy.types.Operator):
    bl_idname = 'ueimport.scene_dependencies'
    bl_label = 'Analyze Level Dependencies'
    bl_description = 'Read the selected level dependency closure without importing geometry; list missing files and unknown tables'

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        state=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            from uasset import UProject
            from ue5_scene_dependencies import audit
            report=audit(UProject(project),selected)
            text=bpy.data.texts.new(Path(selected).stem+' — source dependencies.json');text.write(json.dumps(report,indent=2));state.batch_report=text.name
            publish_scene_actions(state,selected,report)
            self.report({'INFO'},f"{report['scanned_packages']} inspected; {report['unresolved_hard']} hard and {report['unresolved_soft_only']} soft-only unresolved; {len(report['unknown_tables'])} unknown tables. See report.")
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class UEIMPORT_OT_full_scene(bpy.types.Operator):
    bl_idname = 'ueimport.full_scene'
    bl_label = 'Import Complete Saved Level (Preview)'
    bl_description = 'One operation for supported geometry, materials, characters, light and camera previews; unresolved source data is reported'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        state=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            from package_inspector import inspect_package
            from legacy_full_scene import supported
            if supported(inspect_package(selected)):
                from legacy_full_scene import reconstruct
                collection,report=reconstruct(selected,state.partial_materials,state.light_preview_scale,state.strict_scene_dependencies,state.cooked_profile)
            else:
                from ue5_full_scene import reconstruct
                wm=context.window_manager;step=0
                def progress(name):
                    nonlocal step
                    step+=1;wm.progress_update(min(step,13))
                wm.progress_begin(0,14)
                try:
                    collection,report=reconstruct(selected,state.partial_materials,state.light_preview_scale,state.strict_scene_dependencies,progress=progress)
                    wm.progress_update(14)
                finally:wm.progress_end()
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        state.batch_report=collection['UE_report'];counts=report['counts']
        if 'source_dependencies' in report:
            try:publish_scene_actions(state,selected,report['source_dependencies'],report.get('performance'))
            except Exception as exc:self.report({'WARNING'},f'Level imported; source action summary unavailable: {exc}')
        self.report({'INFO'},f"Saved level preview: {counts['meshes']} meshes, {counts['armatures']} rigs, {counts['lights']} lights, {counts['cameras']} cameras. Inspect scene transfer report for gaps.")
        return {'FINISHED'}


class UEIMPORT_UL_maps(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True);row.prop(item,'enabled',text='');row.label(text=item.name)


class UEIMPORT_OT_level_set(bpy.types.Operator):
    bl_idname='ueimport.level_set'
    bl_label='Import Checked Levels (Separate)'
    bl_description='Atomic transfer of checked independent maps; no inferred streaming placement'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return UEIMPORT_OT_import_map.poll(context)
    def execute(self,context):
        s=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(s.project_path));paths=[m.filepath for m in s.maps if m.enabled]
            if project!=s.scanned_project or not set(paths)<={p for _,p in maps}:raise ValueError('Project or maps changed; scan again')
            from saved_project_levels import reconstruct
            c,r=reconstruct(project,paths,s.partial_materials,s.light_preview_scale,s.strict_scene_dependencies,s.cooked_profile);s.batch_report=c['UE_report']
            self.report({'INFO'},f"Imported {len(r['levels'])} independent saved levels")
            return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class UEIMPORT_OT_activate_level(bpy.types.Operator):
    bl_idname='ueimport.activate_level'
    bl_label='Show Selected Imported Level'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):return UEIMPORT_OT_import_map.poll(context)
    def execute(self,context):
        try:
            from saved_project_levels import activate
            s=context.scene.ueimport_project;activate(context.scene,s.maps[s.active].filepath);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class UEIMPORT_OT_apply_sky_preview(bpy.types.Operator):
    bl_idname = 'ueimport.apply_sky_preview'
    bl_label = 'Apply Selected Level Sky Preview'
    bl_description = 'Explicitly replace the scene world with the imported analytical sky preview; Undo or choose another world to restore it'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        try:
            from ue5_environment_preview import activate
            state=context.scene.ueimport_project
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            world=activate(context.scene,selected)
            self.report({'INFO'},'Applied '+world.name+' (approximate sky, not Unreal lighting)')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class UEIMPORT_OT_toggle_fog_preview(bpy.types.Operator):
    bl_idname = 'ueimport.toggle_fog_preview'
    bl_label = 'Toggle Selected Level Fog Preview'
    bl_description = 'Opt-in finite Blender volume from supported saved fog density; not calibrated Unreal fog'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        try:
            from ue5_fog_preview import toggle
            state=context.scene.ueimport_project
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            obj,enabled=toggle(context.scene,selected)
            self.report({'INFO'},('Enabled' if enabled else 'Disabled')+' finite fog approximation')
            return {'FINISHED'}
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class UEIMPORT_OT_repair_missing(bpy.types.Operator):
    bl_idname = 'ueimport.repair_missing_meshes'
    bl_label = 'Repair Selected Missing Meshes'
    bl_description = 'Restore original UE5.6 mesh packages as children of selected missing anchors; does not replace the original import'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context) and bool(context.selected_objects)

    def execute(self, context):
        state=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            from ue5_editor_repair import restore
            collection,report=restore(selected,context.selected_objects,state.static_materials,state.partial_materials)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f"Repair: {report['counts']}; report: {report['report_text']}")
        return {'FINISHED'}


class UEIMPORT_OT_lighting_preview(bpy.types.Operator):
    bl_idname = 'ueimport.lighting_preview'
    bl_label = 'Import UE5 Lighting & Markers'
    bl_description = 'Import saved UE5.6 root lights and environment/spawn markers as a separate approximate preview'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        state=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path))
            selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            from ue5_editor_lighting import reconstruct
            collection,report=reconstruct(selected,state.light_preview_scale)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f"Imported {sum(report['counts'].values())} lights/markers; {len(report['skipped'])} skipped. Approximate preview.")
        return {'FINISHED'}


class UEIMPORT_OT_camera_preview(bpy.types.Operator):
    bl_idname = 'ueimport.camera_preview'
    bl_label = 'Import UE5 Camera Rig Previews'
    bl_description = 'Reconstruct unoccluded saved spring-arm camera rigs; not runtime viewpoints'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def execute(self, context):
        state=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            from ue5_editor_camera import reconstruct
            collection,report=reconstruct(selected)
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f"Imported {len(report['records'])} camera rig previews; {len(report['skipped'])} skipped.")
        return {'FINISHED'}


class UEIMPORT_OT_geometry_gallery(bpy.types.Operator):
    bl_idname = 'ueimport.geometry_gallery'
    bl_label = 'Import Native Geometry Folder'
    bl_description = 'Import supported static and skinned meshes as an inspection gallery, not a map'
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        state=context.scene.ueimport_project
        try:
            from project_geometry import import_geometry_folder
            collection,report=import_geometry_folder(bpy.path.abspath(state.project_path),state.geometry_folder,state.cooked_profile,state.geometry_physics,state.geometry_all_lods,state.static_materials,state.partial_materials)
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        count=report['counts'].get('reconstructed',0)
        self.report({'INFO'},f"Imported {count} geometry assets; report: {collection['UE_report']}")
        return {'FINISHED'}


def catalog_key(state):
    from project_session import digest
    selected=state.maps[state.active].filepath if 0<=state.active<len(state.maps) else None
    return digest([str(Path(bpy.path.abspath(state.project_path)).resolve()),state.batch_scope,selected if state.batch_scope in ('SELECTED_MAP','MAP_GEOMETRY') else None,state.geometry_folder if state.batch_scope=='GEOMETRY' else '',state.job_filter])


def make_plan(state,ignore_selection=False):
    from project_preflight import preflight
    selected=state.maps[state.active].filepath if 0<=state.active<len(state.maps) else None
    packages=None
    if state.use_job_selection and not ignore_selection:
        if state.catalog_key!=catalog_key(state): raise ValueError('Job list is stale; refresh it before importing')
        packages={item.package for item in state.job_items if item.enabled}
        if not packages: raise ValueError('Check at least one job')
    return preflight(bpy.path.abspath(state.project_path),state.batch_scope,selected,state.geometry_folder if state.batch_scope=='GEOMETRY' else '',job_filter=state.job_filter,selected_packages=packages)


def refresh_catalog(state):
    plan=make_plan(state,ignore_selection=True)
    old={item.package:item.enabled for item in state.job_items} if state.catalog_key==catalog_key(state) else {}
    state.job_items.clear();state.job_active=0
    for package in plan['seeds']:
        item=state.job_items.add();item.package=package;item.enabled=old.get(package,True)
        record=plan['records'][package];item.kind=', '.join(record['classes']) or 'Unknown'
        item.missing=sum(plan['dependencies'].get(r,{}).get('status') in ('missing_game','missing_engine','unsupported_mount') for r in set(record['references'])|set(record['soft_references']))
    state.catalog_key=catalog_key(state)
    return plan


class UEIMPORT_OT_refresh_jobs(bpy.types.Operator):
    bl_idname='ueimport.refresh_jobs';bl_label='Refresh asset job list'
    def execute(self,context):
        state=context.scene.ueimport_project
        try: plan=refresh_catalog(state)
        except Exception as exc: self.report({'ERROR'},str(exc));return {'CANCELLED'}
        self.report({'INFO'},f"{len(plan['jobs'])} available jobs");return {'FINISHED'}


class UEIMPORT_OT_check_jobs(bpy.types.Operator):
    bl_idname='ueimport.check_jobs';bl_label='Check or uncheck jobs'
    enabled: BoolProperty(default=True)
    def execute(self,context):
        for item in context.scene.ueimport_project.job_items: item.enabled=self.enabled
        return {'FINISHED'}


class UEIMPORT_OT_preflight(bpy.types.Operator):
    bl_idname='ueimport.preflight'
    bl_label='Dependency Preflight'
    def execute(self,context):
        state=context.scene.ueimport_project
        try:
            from project_batch import publish_report
            plan=make_plan(state)
            state.batch_report=publish_report('UE dependency preflight.json',plan)
            state.batch_status=f"{len(plan['jobs'])} jobs, {plan['closure_count']} packages, {plan['dependency_counts'].get('missing_game',0)} missing Game refs"
        except Exception as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}
        self.report({'INFO'},state.batch_status);return {'FINISHED'}


class UEIMPORT_OT_batch(bpy.types.Operator):
    bl_idname='ueimport.batch_import'
    bl_label='Run / Resume Batch Import'
    bl_description='Import one job at a time; Esc stops after the current job, keeping completed results'
    bl_options={'REGISTER','UNDO'}
    _active=False

    @classmethod
    def poll(cls,context): return not cls._active

    def start(self,context):
        from project_session import run_session
        self.state=context.scene.ueimport_project
        self.plan=make_plan(self.state)
        if not self.plan['jobs']: raise ValueError('No import jobs found')
        self.results=[];self.recovery_path=''
        if self.state.recovery_copy:
            from project_session import save_recovery_copy
            self.recovery_path=save_recovery_copy()
        self.iterator=run_session(self.plan,self.state.cooked_profile,self.state.static_materials,self.state.components,self.state.partial_materials,self.state.geometry_physics,self.state.geometry_all_lods)
        self.timer=None;self.wm=context.window_manager;self.next_tick=0.;self.finished=False
        self.wm.progress_begin(0,len(self.plan['jobs']))
        type(self)._active=True
        self.state.batch_status=f"0/{len(self.plan['jobs'])} jobs"

    def step(self):
        try: result=next(self.iterator)
        except StopIteration: return False
        self.results.append(result)
        self.wm.progress_update(len(self.results))
        self.state.batch_status=f"{len(self.results)}/{len(self.plan['jobs'])} jobs"
        return True

    def finish(self,status,error=''):
        from project_batch import publish_report
        if self.finished: return {'FINISHED'}
        self.finished=True
        try:
            self.iterator.close()
            self.state.batch_report=publish_report('UE batch report.json',dict(status=status,error=error,plan=self.plan,results=self.results,recovery_copy=self.recovery_path,unprocessed=len(self.plan['jobs'])-len(self.results)))
            reused=sum(bool(r.get('reused')) for r in self.results)
            blocked=sum(r['status']=='blocked_stale' for r in self.results)
            failed=sum(r['status'] in ('failed','unsupported') for r in self.results)
            self.state.batch_status=f"{status}: {len(self.results)}/{len(self.plan['jobs'])}; {reused} reused, {blocked} blocked, {failed} failed"
            self.report({'WARNING'} if status!='completed' or any(r['status'] in ('failed','unsupported','blocked_stale') or r.get('has_unresolved_static') or r.get('has_unresolved_characters') or r.get('result',{}).get('physics',{}).get('status') in ('missing','unavailable') for r in self.results) else {'INFO'},self.state.batch_status)
        finally:
            if self.timer: self.wm.event_timer_remove(self.timer)
            self.wm.progress_end();type(self)._active=False
        # FINISHED retains completed jobs and enables Undo, even for user stop.
        return {'FINISHED'}

    def execute(self,context):
        try: self.start(context)
        except Exception as exc: self.report({'ERROR'},str(exc));return {'CANCELLED'}
        try:
            while self.step(): pass
        except Exception as exc: return self.finish('failed',str(exc))
        return self.finish('completed')

    def invoke(self,context,event):
        try: self.start(context)
        except Exception as exc: self.report({'ERROR'},str(exc));return {'CANCELLED'}
        try:
            self.timer=self.wm.event_timer_add(.05,window=context.window)
            self.wm.modal_handler_add(self)
        except Exception as exc: return self.finish('failed',str(exc))
        return {'RUNNING_MODAL'}

    def modal(self,context,event):
        if event.type=='ESC' and event.value=='PRESS': return self.finish('stopped')
        # Blender 4.2 Event does not expose the originating Timer. Throttle generic TIMER events.
        if event.type=='TIMER' and time.monotonic()>=self.next_tick:
            self.next_tick=time.monotonic()+.05
            try:
                if not self.step(): return self.finish('completed')
                if context.area: context.area.tag_redraw()
            except Exception as exc: return self.finish('failed',str(exc))
        # Avoid editing the scene while a batch owns its data.
        return {'RUNNING_MODAL'}

    def cancel(self,context):
        if hasattr(self,'finished'): self.finish('stopped')


class UEIMPORT_PT_project(bpy.types.Panel):
    bl_label = 'Unreal Project Importer'
    bl_idname = 'UEIMPORT_PT_project'
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Unreal'

    def draw(self, context):
        state = context.scene.ueimport_project
        layout = self.layout
        layout.operator('ueimport.native_texture', icon='IMAGE_DATA')
        layout.operator('ueimport.wind_preview', icon='MOD_NODES')
        layout.prop(state, 'project_path')
        layout.operator('ueimport.scan_project', icon='FILE_REFRESH')
        box=layout.box();box.label(text='Project batch workflow')
        box.prop(state,'batch_scope');box.prop(state,'job_filter')
        if state.batch_scope in ('GEOMETRY','MAP_GEOMETRY'):
            if state.batch_scope=='GEOMETRY': box.prop(state,'geometry_folder')
            else: box.label(text='Gallery of selected map dependencies')
            box.prop(state,'geometry_physics')
            box.prop(state,'static_materials',text='UE5 editor materials')
            if state.static_materials: box.prop(state,'partial_materials')
            if state.cooked_profile=='5.6': box.prop(state,'geometry_all_lods')
        else:
            box.prop(state,'components');box.prop(state,'static_materials')
            if state.static_materials: box.prop(state,'partial_materials')
        box.prop(state,'cooked_profile')
        box.operator('ueimport.refresh_jobs',icon='FILE_REFRESH')
        box.prop(state,'use_job_selection')
        if state.use_job_selection:
            if state.catalog_key!=catalog_key(state): box.label(text='Refresh the job list',icon='ERROR')
            else:
                row=box.row(align=True);row.operator('ueimport.check_jobs',text='All').enabled=True;row.operator('ueimport.check_jobs',text='None').enabled=False
                box.template_list('UEIMPORT_UL_jobs','asset_jobs',state,'job_items',state,'job_active',rows=5)
                box.label(text=f'{sum(item.enabled for item in state.job_items)} of {len(state.job_items)} jobs checked')
        box.operator('ueimport.preflight',icon='VIEWZOOM')
        box.prop(state,'recovery_copy')
        box.operator('ueimport.batch_import',icon='PLAY')
        if state.batch_status: box.label(text=state.batch_status)
        if state.batch_report: box.label(text=state.batch_report,icon='TEXT')
        box.label(text='Esc stops between jobs; save to resume')
        box.label(text='Existing verified jobs are reused')
        if state.scanned_project:
            layout.label(text=f'Engine: {state.engine}')
            layout.label(text=f'Maps: {len(state.maps)}')
            layout.template_list('UEIMPORT_UL_maps', 'unreal_maps', state, 'maps', state, 'active', rows=5)
            layout.prop(state,'partial_materials',text='Allow partial material previews')
            layout.operator('ueimport.scene_dependencies',icon='VIEWZOOM')
            if 0<=state.active<len(state.maps) and state.scene_summary_source==state.maps[state.active].filepath:
                actions=layout.box();actions.label(text=state.scene_summary);actions.operator('ueimport.copy_scene_actions',icon='COPYDOWN')
            layout.prop(state,'strict_scene_dependencies')
            layout.operator('ueimport.full_scene',icon='SCENE_DATA')
            layout.operator('ueimport.level_set',icon='SCENE_DATA')
            layout.operator('ueimport.activate_level')
            layout.operator('ueimport.apply_sky_preview',icon='WORLD')
            layout.operator('ueimport.toggle_fog_preview')
            layout.prop(state, 'materials')
            layout.operator('ueimport.import_selected_map', icon='IMPORT')
            layout.separator()
            layout.prop(state, 'cooked_profile')
            layout.prop(state, 'geometry_folder')
            layout.prop(state, 'geometry_physics')
            if state.cooked_profile=='5.6': layout.prop(state,'geometry_all_lods')
            layout.prop(state,'static_materials',text='UE5 editor materials')
            if state.static_materials: layout.prop(state,'partial_materials')
            layout.operator('ueimport.geometry_gallery', icon='OUTLINER_OB_ARMATURE')
            layout.separator()
            layout.prop(state, 'components')
            layout.prop(state, 'static_materials')
            if state.static_materials:
                layout.prop(state, 'partial_materials')
            layout.operator('ueimport.reconstruct_static', icon='MESH_DATA')
            layout.prop(state,'light_preview_scale')
            layout.operator('ueimport.lighting_preview', icon='LIGHT')
            layout.operator('ueimport.camera_preview', icon='CAMERA_DATA')
            layout.operator('ueimport.repair_missing_meshes', icon='FILE_REFRESH')
            layout.label(text='Lighting is a preview, not Unreal rendering.')
            layout.label(text='Missing meshes remain empties; unresolved materials marked.')
            layout.label(text='Bounded native formats; unsupported assets reported.')


CLASSES = (UEIMPORT_Map, UEIMPORT_UL_maps, UEIMPORT_OT_level_set, UEIMPORT_OT_activate_level, UEIMPORT_Job, UEIMPORT_UL_jobs, UEIMPORT_Settings, UEIMPORT_OT_scan, UEIMPORT_OT_import_map, UEIMPORT_OT_reconstruct_static, UEIMPORT_OT_scene_dependencies, UEIMPORT_OT_copy_scene_actions, UEIMPORT_OT_full_scene, UEIMPORT_OT_apply_sky_preview, UEIMPORT_OT_toggle_fog_preview, UEIMPORT_OT_repair_missing, UEIMPORT_OT_lighting_preview, UEIMPORT_OT_camera_preview, UEIMPORT_OT_geometry_gallery, UEIMPORT_OT_refresh_jobs, UEIMPORT_OT_check_jobs, UEIMPORT_OT_preflight, UEIMPORT_OT_batch, UEIMPORT_PT_project)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ueimport_project = PointerProperty(type=UEIMPORT_Settings)


def unregister():
    del bpy.types.Scene.ueimport_project
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
