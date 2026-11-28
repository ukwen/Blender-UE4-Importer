"""Native project map selection; delegates reconstruction to the existing reader."""
from pathlib import Path
import json
import hashlib
import time
import bpy
from bpy.props import StringProperty, BoolProperty, IntProperty, FloatProperty, CollectionProperty, PointerProperty, EnumProperty


from project_paths import discover_maps


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
    show_recovery: BoolProperty(name='Recover missing assets',default=False)
    show_environment: BoolProperty(name='Environment previews',default=False)
    show_options: BoolProperty(name='Import options',default=False)
    show_batch: BoolProperty(name='Advanced asset batch',default=False)
    show_tools: BoolProperty(name='Advanced individual tools',default=False)
    project_path: StringProperty(name='Project', subtype='FILE_PATH')
    scanned_project: StringProperty(options={'HIDDEN'})
    engine: StringProperty(options={'HIDDEN'})
    map_redirectors: StringProperty(options={'HIDDEN'})
    maps: CollectionProperty(type=UEIMPORT_Map)
    active: IntProperty(default=0, min=0)
    cooked_profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Legacy buffers'),('4.27','UE4.27','Separate buffers'),('5.0','UE5.0','Bounded unversioned split profile'),('5.4','UE5.4','Bounded cooked static only'),('5.5','UE5.5','Bounded cooked static only'),('5.6','UE5.6','Bounded cooked static and skeletal LOD0')],default='4.27')
    scene_cache_mib: IntProperty(name='Package cache (MiB)',default=64,min=0,max=256,description='Modern saved-level package table cache; 0 disables caching for lower peak memory. Not a total memory limit.')
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
    recovery_folder: StringProperty(name='Original asset recovery folder', subtype='DIR_PATH')
    source_recovery_plan: StringProperty(options={'HIDDEN'})
    source_recovery_status: StringProperty(options={'HIDDEN'})
    source_recovery_scope: StringProperty(options={'HIDDEN'})
    geometry_folder: StringProperty(name='Content subfolder',description='Relative to Content; empty imports all supported geometry assets')
    materials: BoolProperty(name='Materials (required for saved level)', default=True, description='Use Reconstruct Static Geometry for a geometry-only preview')
    components: BoolProperty(name='Include Blueprint and skeletal components', default=False, description='Reconstruct map-owned component hierarchies; unresolved defaults and sockets stay diagnostic')
    static_materials: BoolProperty(name='Bind materials (experimental)', default=False)
    partial_materials: BoolProperty(name='Keep incomplete surface previews', default=False, description='Keep connected material graphs with resolved surface images; missing functions and unsupported effects remain marked')


class UEIMPORT_OT_scan(bpy.types.Operator):
    bl_idname = 'ueimport.scan_project'
    bl_label = 'Scan Unreal Project'

    @classmethod
    def poll(cls,context):return not UEIMPORT_OT_level_set._active and not UEIMPORT_OT_batch._active

    def execute(self, context):
        state = context.scene.ueimport_project
        state.maps.clear()
        state.job_items.clear();state.job_active=0;state.catalog_key=''
        state.batch_status=state.batch_report=''
        state.scanned_project = ''
        state.engine = ''
        state.map_redirectors = ''
        state.active = 0
        state.scene_summary = state.scene_summary_source = state.scene_action_report = ''
        state.source_recovery_plan = state.source_recovery_status = state.source_recovery_scope = ''
        try:
            redirectors=[]
            project, engine, maps = discover_maps(bpy.path.abspath(state.project_path),redirectors)
        except (OSError, ValueError) as exc:
            self.report({'ERROR'}, str(exc))
            return {'CANCELLED'}
        state.scanned_project, state.engine = project, engine
        for name, filepath in maps:
            item = state.maps.add()
            item.name, item.filepath = name, filepath
        state.map_redirectors=json.dumps(redirectors) if redirectors else ''
        self.report({'INFO'}, f'Found {len(maps)} maps; {len(redirectors)} redirectors excluded')
        return {'FINISHED'}


class UEIMPORT_OT_import_map(bpy.types.Operator):
    bl_idname = 'ueimport.import_selected_map'
    bl_label = 'Import Selected Saved Level'
    bl_description = 'Native saved-level reconstruction; use individual geometry tools for selective previews'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        state = context.scene.ueimport_project
        if UEIMPORT_OT_level_set._active or UEIMPORT_OT_batch._active or not state.scanned_project or not 0<=state.active<len(state.maps):return False
        try:return str(Path(bpy.path.abspath(state.project_path)).resolve())==state.scanned_project
        except (OSError,ValueError,RuntimeError):return False

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
            if not state.materials:
                raise ValueError('Historical materials-off map import is no longer supported; enable Materials for saved-level import or use Reconstruct Static Geometry without Bind materials')
            from asset_entrypoints import import_saved_levels
            group,report=import_saved_levels([selected],state.partial_materials,state.strict_scene_dependencies,state.light_preview_scale,state.cooked_profile)
        except Exception as exc:
            self.report({'ERROR'}, f'Import failed: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'}, f"Native saved-level import complete; report: {group['UE_report']}")
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


def publish_scene_actions(state, selected, dependencies, performance=None, material_diagnostics=None):
    from import_workflow import dependency_actions
    actions=dependencies.get('actions') or dependency_actions(dependencies)
    lines=[str(selected), 'Source availability (not visual completeness)',
           f"{actions['unresolved_packages']} unresolved packages; {len(actions['unknown_tables'])} unknown tables"]
    for r in actions['packages']:
        lines.append(f"{r['package']} | {r['status']} | hard: {r['hard_references']}, soft: {r['soft_references']} | {r['action']}")
    if actions['unknown_tables']:
        lines.append('Unknown package tables:');lines.extend(actions['unknown_tables'])
    if material_diagnostics:
        lines.append('Material diagnostics (known hard closure, not visible shading completeness):')
        for r in material_diagnostics['materials']:
            lines.append(f"{r['package']} | {r['status']} | {', '.join(r['uses'])} | {r['action']}")
            lines.extend(f"  {p}: {status}" for p,status in r['missing_hard_closure'].items())
            lines.extend(f"  Unknown table: {p}" for p in r['unknown_tables'])
            if r['detail']:lines.append('  '+r['detail'])
            lines.extend('  '+str(issue) for issue in r['issues'])
    if performance:
        lines.append(f"Import: {performance['elapsed_seconds']:.2f}s; {performance['table_reads']} table reads; {performance['table_hits']} cache hits")
        lines.extend(f"{name}: {seconds:.3f}s" for name,seconds in performance['stage_seconds'].items())
    text=bpy.data.texts.new(Path(selected).stem+' — source actions.txt');text.write('\n'.join(lines)+'\n')
    state.scene_summary_source=str(selected);state.scene_action_report=text.name
    state.scene_summary=f"{actions['unresolved_packages']} missing/invalid packages; {len(actions['unknown_tables'])} unknown tables"
    if performance:state.scene_summary+=f" | {performance['elapsed_seconds']:.1f}s"


def resolve_report(context, kind):
    """Resolve selected level reports by collection identity, never the last batch name."""
    state=context.scene.ueimport_project
    if UEIMPORT_OT_level_set._active or UEIMPORT_OT_batch._active:return None
    if kind=='LATEST':return bpy.data.texts.get(state.batch_report)
    if not UEIMPORT_OT_import_map.poll(context):return None
    source=state.maps[state.active].filepath
    if kind=='RECOVERY':return recovery_report(context)
    if kind=='ACTIONS':
        return bpy.data.texts.get(state.scene_action_report) if state.scene_summary_source==source else None
    if kind=='LEVEL':
        matches=[c for c in context.scene.collection.children_recursive if c.get('UE_full_scene_source')==source]
    elif kind=='SET':
        matches=[c for c in context.scene.collection.children_recursive if c.get('UE_project_level_set')==state.scanned_project and any(x.get('UE_full_scene_source')==source for x in c.children)]
    else:return None
    return bpy.data.texts.get(matches[0].get('UE_report','')) if len(matches)==1 else None


class UEIMPORT_OT_report(bpy.types.Operator):
    bl_idname='ueimport.report'
    bl_label='Read Import Report'
    bl_description='Open a stored report in a Text Editor or copy its complete contents; no source files are modified'
    kind: EnumProperty(items=[('LEVEL','Selected level',''),('SET','Selected level set',''),('ACTIONS','Selected source actions',''),('RECOVERY','Reviewed recovery plan',''),('LATEST','Last operation','')],default='LEVEL')
    copy: BoolProperty(default=False)

    def execute(self,context):
        text=resolve_report(context,self.kind)
        if text is None:
            self.report({'WARNING'},'Report missing, ambiguous or no longer matches the selection');return {'CANCELLED'}
        # Verify selected transfer reports on demand, not in the frequently redrawn panel.
        if self.kind in ('LEVEL','SET'):
            state=context.scene.ueimport_project;source=state.maps[state.active].filepath
            try:
                data=json.loads(text.as_string())
                valid=(data.get('source')==source if self.kind=='LEVEL' else data.get('project')==state.scanned_project and any(x.get('source')==source for x in data.get('levels',[])))
            except (ValueError,TypeError,AttributeError):valid=False
            if not valid:
                self.report({'WARNING'},'Report contents do not match the selected level');return {'CANCELLED'}
        if self.kind=='RECOVERY' and not recovery_report(context,verify=True):
            self.report({'WARNING'},'Recovery plan contents changed; locate candidates again');return {'CANCELLED'}
        if self.copy:
            context.window_manager.clipboard=text.as_string()
            self.report({'INFO'},'Report copied');return {'FINISHED'}
        screen=context.screen
        area=next((a for a in screen.areas if a.type=='TEXT_EDITOR'),None) if screen else None
        area=area or context.area
        if area is None:
            self.report({'WARNING'},'Open from a Blender editor, or use Copy');return {'CANCELLED'}
        area.type='TEXT_EDITOR';area.spaces.active.text=text
        return {'FINISHED'}


def draw_report_row(layout,context,kind,label):
    if resolve_report(context,kind) is None:return
    row=layout.row(align=True)
    op=row.operator('ueimport.report',text=label,icon='TEXT');op.kind=kind
    op=row.operator('ueimport.report',text='',icon='COPYDOWN');op.kind=kind;op.copy=True


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
            from project_paths import ProjectPaths
            from ue5_scene_dependencies import audit
            from import_workflow import table_scope
            with table_scope(state.scene_cache_mib*1024*1024):report=audit(ProjectPaths(project),selected)
            text=bpy.data.texts.new(Path(selected).stem+' — source dependencies.json');text.write(json.dumps(report,indent=2));state.batch_report=text.name
            publish_scene_actions(state,selected,report)
            self.report({'INFO'},f"{report['scanned_packages']} inspected; {report['unresolved_hard']} hard and {report['unresolved_soft_only']} soft-only unresolved; {len(report['unknown_tables'])} unknown tables. See report.")
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


def recovery_scope(context):
    """Cheap current selection key; no package scan in panel redraws."""
    if not UEIMPORT_OT_import_map.poll(context):return ''
    s=context.scene.ueimport_project
    if not s.recovery_folder.strip():return ''
    try:
        folder=Path(bpy.path.abspath(s.recovery_folder)).expanduser().resolve()
        content=(Path(s.scanned_project).parent/'Content').resolve()
        if not folder.is_dir() or folder.is_relative_to(content):return ''
        return json.dumps([s.scanned_project,s.maps[s.active].filepath,str(folder)])
    except (OSError,ValueError,RuntimeError):return ''


def recovery_report(context,verify=False):
    s=context.scene.ueimport_project;scope=recovery_scope(context)
    if not scope or scope!=s.source_recovery_scope:return None
    text=bpy.data.texts.get(s.source_recovery_plan)
    if text is None or text.get('UE_recovery_scope')!=scope:return None
    if verify and hashlib.sha256(text.as_string().encode()).hexdigest()!=text.get('UE_recovery_digest'):return None
    return text


def recovery_context(context):
    s=context.scene.ueimport_project
    project,_,maps=discover_maps(bpy.path.abspath(s.project_path));selected=s.maps[s.active].filepath
    if project!=s.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
    if not recovery_scope(context):raise ValueError('Choose an existing recovery folder outside project Content')
    from project_paths import ProjectPaths
    return s,ProjectPaths(project),selected,bpy.path.abspath(s.recovery_folder)


class UEIMPORT_OT_locate_sources(bpy.types.Operator):
    bl_idname='ueimport.locate_sources'
    bl_label='Locate Missing Original Packages'
    bl_description='Read only: find missing Game assets by serialized identity, not filename'
    @classmethod
    def poll(cls,context):return UEIMPORT_OT_import_map.poll(context)
    def execute(self,context):
        s=context.scene.ueimport_project;s.source_recovery_plan=s.source_recovery_status=s.source_recovery_scope=''
        try:
            s,project,selected,folder=recovery_context(context)
            from source_recovery import plan
            report=plan(project,selected,folder)
            scope=recovery_scope(context);counts=report['counts']
            t=bpy.data.texts.new(Path(selected).stem+' — source recovery plan.json');t.write(json.dumps(report,indent=2))
            t['UE_recovery_scope']=scope;t['UE_recovery_digest']=hashlib.sha256(t.as_string().encode()).hexdigest();t['UE_recovery_ready']=counts.get('ready',0)
            s.source_recovery_plan=t.name;s.source_recovery_scope=scope
            s.source_recovery_status='; '.join(f"{counts.get(key,0)} {label}" for key,label in [('ready','verified'),('ambiguous','ambiguous'),('not_found','not found'),('unsupported','unsupported'),('blocked','blocked')])
            self.report({'INFO'},s.source_recovery_status);return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


class UEIMPORT_OT_restore_sources(bpy.types.Operator):
    bl_idname='ueimport.restore_sources'
    bl_label='Restore Verified Original Packages'
    bl_description='Copy verified missing assets into project Content; never overwrite existing files. Filesystem changes are not Blender Undo operations.'
    confirmed_digest: StringProperty(options={'HIDDEN','SKIP_SAVE'})
    confirmed_name: StringProperty(options={'HIDDEN','SKIP_SAVE'})
    @classmethod
    def poll(cls,context):
        text=recovery_report(context)
        return text is not None and text.get('UE_recovery_ready',0)>0
    def invoke(self,context,event):
        text=recovery_report(context,verify=True)
        if text is None:
            self.report({'WARNING'},'Recovery plan changed; locate candidates again');return {'CANCELLED'}
        self.confirmed_name=text.name;self.confirmed_digest=text['UE_recovery_digest']
        return context.window_manager.invoke_confirm(self,event,title='Restore verified original packages?',message=f"Restore {text['UE_recovery_ready']} verified packages into Content? Blender Undo cannot reverse this.",confirm_text='Restore Files')
    def execute(self,context):
        try:
            s,project,selected,folder=recovery_context(context)
            text=recovery_report(context,verify=True)
            if text is None or (self.confirmed_name and (text.name!=self.confirmed_name or text['UE_recovery_digest']!=self.confirmed_digest)):
                raise ValueError('Reviewed recovery plan changed; locate candidates again')
            reviewed=json.loads(text.as_string())
            from source_recovery import restore
            report,deps=restore(project,selected,folder,reviewed)
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        s.source_recovery_plan='';s.source_recovery_status=f"Restored {len(report['restored'])} packages; repair missing mesh anchors or reimport explicitly"
        try:
            t=bpy.data.texts.new(Path(selected).stem+' — source recovery result.json');t.write(json.dumps(report,indent=2));s.batch_report=t.name
            publish_scene_actions(s,selected,deps)
        except Exception as exc:self.report({'WARNING'},f'Files restored; report could not be written: {exc}')
        self.report({'INFO'},s.source_recovery_status);return {'FINISHED'}


class UEIMPORT_OT_full_scene(bpy.types.Operator):
    bl_idname = 'ueimport.full_scene'
    bl_label = 'Import Complete Saved Level (Preview)'
    bl_description = 'One operation for supported geometry, materials, characters, light and camera previews; unresolved source data is reported'
    bl_options = {'REGISTER', 'UNDO'}

    @classmethod
    def poll(cls, context):
        return UEIMPORT_OT_import_map.poll(context)

    def invoke(self,context,event):
        state=context.scene.ueimport_project
        try:
            project,_,maps=discover_maps(bpy.path.abspath(state.project_path));selected=state.maps[state.active].filepath
            if project!=state.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            from package_inspector import inspect_package
            from legacy_full_scene import supported
            if supported(inspect_package(selected)):return self.execute(context)
            from ue5_full_scene import iter_reconstruct
            self.state=state;self.selected=selected;self.wm=context.window_manager;self.timer=None;self.next_tick=0.;self.finished=False
            self.iterator=iter_reconstruct(selected,state.partial_materials,state.light_preview_scale,state.strict_scene_dependencies,cache_budget=state.scene_cache_mib*1024*1024)
            UEIMPORT_OT_level_set._active=True
            state.batch_status='Preparing selected level; Esc cancels'
            self.timer=self.wm.event_timer_add(.05,window=context.window);self.wm.modal_handler_add(self)
        except Exception as exc:
            if hasattr(self,'iterator'):return self._finish('failed',str(exc))
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'RUNNING_MODAL'}

    def _finish(self,status,error=''):
        if self.finished:return {'CANCELLED'}
        self.finished=True
        try:
            self.iterator.close()
            self.state.batch_status='Selected level imported' if status=='completed' else f'Selected level {status}; staged data rolled back'
            self.report({'INFO'} if status=='completed' else {'WARNING'} if status=='cancelled' else {'ERROR'},error or self.state.batch_status)
        finally:
            if self.timer:self.wm.event_timer_remove(self.timer)
            UEIMPORT_OT_level_set._active=False
        return {'FINISHED'} if status=='completed' else {'CANCELLED'}

    def modal(self,context,event):
        if event.type=='ESC' and event.value=='PRESS':return self._finish('cancelled')
        if event.type=='TIMER' and time.monotonic()>=self.next_tick:
            try:
                stage=next(self.iterator);self.state.batch_status=f'{stage}; Esc cancels'
                self.next_tick=time.monotonic()+.10
                if context.area:context.area.tag_redraw()
            except StopIteration as done:
                collection,report=done.value;self.state.batch_report=collection['UE_report']
                try:publish_scene_actions(self.state,self.selected,report['source_dependencies'],report.get('performance'),report.get('material_diagnostics'))
                except Exception as exc:self.report({'WARNING'},f'Level imported; source action summary unavailable: {exc}')
                return self._finish('completed')
            except Exception as exc:return self._finish('failed',str(exc))
        return {'RUNNING_MODAL'}

    def cancel(self,context):
        if hasattr(self,'iterator'):self._finish('cancelled')

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
                    from import_workflow import table_scope
                    with table_scope(state.scene_cache_mib*1024*1024):
                        collection,report=reconstruct(selected,state.partial_materials,state.light_preview_scale,state.strict_scene_dependencies,progress=progress)
                    wm.progress_update(14)
                finally:wm.progress_end()
        except Exception as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        state.batch_report=collection['UE_report'];counts=report['counts']
        if 'source_dependencies' in report:
            try:publish_scene_actions(state,selected,report['source_dependencies'],report.get('performance'),report.get('material_diagnostics'))
            except Exception as exc:self.report({'WARNING'},f'Level imported; source action summary unavailable: {exc}')
        self.report({'INFO'},f"Saved level preview: {counts['meshes']} meshes, {counts['armatures']} rigs, {counts['lights']} lights, {counts['cameras']} cameras. Inspect scene transfer report for gaps.")
        return {'FINISHED'}


class UEIMPORT_UL_maps(bpy.types.UIList):
    def draw_item(self,context,layout,data,item,icon,active_data,active_propname,index):
        row=layout.row(align=True);row.prop(item,'enabled',text='');row.label(text=Path(item.name).stem)


class UEIMPORT_OT_check_maps(bpy.types.Operator):
    bl_idname='ueimport.check_maps'
    bl_label='Check or uncheck all levels'
    enabled: BoolProperty(default=True)
    @classmethod
    def poll(cls,context):return UEIMPORT_OT_import_map.poll(context)
    def execute(self,context):
        for item in context.scene.ueimport_project.maps:item.enabled=self.enabled
        return {'FINISHED'}


class UEIMPORT_OT_level_set(bpy.types.Operator):
    bl_idname='ueimport.level_set'
    bl_label='Import Checked Levels (Separate)'
    bl_description='Atomic independent map transfer; Esc rolls back the entire set at safe stage boundaries. No inferred streaming placement.'
    bl_options={'REGISTER','UNDO'}
    _active=False
    @classmethod
    def poll(cls,context):return not cls._active and not UEIMPORT_OT_batch._active and UEIMPORT_OT_import_map.poll(context)
    def prepare(self,context):
        s=context.scene.ueimport_project
        project,_,maps=discover_maps(bpy.path.abspath(s.project_path));paths=[m.filepath for m in s.maps if m.enabled]
        if project!=s.scanned_project or not set(paths)<={p for _,p in maps}:raise ValueError('Project or maps changed; scan again')
        from saved_project_levels import validate_selection,iter_reconstruct
        validate_selection(project,paths)
        self.state=s;self.total=len(paths);self.done=0;self.timer=None;self.wm=context.window_manager;self.next_tick=0.;self.finished=False
        self.iterator=iter_reconstruct(project,paths,s.partial_materials,s.light_preview_scale,s.strict_scene_dependencies,s.cooked_profile,cache_budget=s.scene_cache_mib*1024*1024,stage_steps=True)
        self.wm.progress_begin(0,self.total);type(self)._active=True
        s.batch_status=f'0/{self.total} levels (atomic transfer)'
    def step(self):
        try:row=next(self.iterator)
        except StopIteration as done:
            c,r=done.value;self.state.batch_report=c['UE_report'];return self.finish('completed')
        self.done=row['completed'];self.wm.progress_update(self.done);self.state.batch_status=f'{self.done}/{self.total} levels staged; Esc rolls back set'
        self.map_boundary=not row.get('stage')
        if row.get('stage'):self.state.batch_status=f'{self.done}/{self.total}: {Path(row["source"]).stem} — {row["stage"]}; Esc cancels'
        return None
    def finish(self,status,error=''):
        if self.finished:return {'FINISHED'} if status=='completed' else {'CANCELLED'}
        self.finished=True
        try:
            self.iterator.close()
            self.state.batch_status=f'Imported {self.total} independent levels' if status=='completed' else f'Level set {status}; staged levels rolled back'
            self.report({'INFO'} if status=='completed' else {'WARNING'} if status=='cancelled' else {'ERROR'},error or self.state.batch_status)
        finally:
            if self.timer:self.wm.event_timer_remove(self.timer)
            self.wm.progress_end();type(self)._active=False
        return {'FINISHED'} if status=='completed' else {'CANCELLED'}
    def execute(self,context):
        try:self.prepare(context)
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        try:
            while True:
                result=self.step()
                if result:return result
        except Exception as exc:return self.finish('failed',str(exc))
    def invoke(self,context,event):
        try:self.prepare(context)
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}
        try:
            self.timer=self.wm.event_timer_add(.05,window=context.window);self.wm.modal_handler_add(self)
        except Exception as exc:return self.finish('failed',str(exc))
        return {'RUNNING_MODAL'}
    def modal(self,context,event):
        if event.type=='ESC' and event.value=='PRESS':return self.finish('cancelled')
        if event.type=='TIMER' and time.monotonic()>=self.next_tick:
            try:
                result=self.step()
                if result:return result
                # Give queued desktop input a chance after each stage and completed map.
                self.next_tick=time.monotonic()+(.25 if self.map_boundary else .05)
                if context.area:context.area.tag_redraw()
            except Exception as exc:return self.finish('failed',str(exc))
        return {'RUNNING_MODAL'}
    def cancel(self,context):
        if hasattr(self,'finished'):self.finish('cancelled')


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


class UEIMPORT_OT_select_recoverable_meshes(bpy.types.Operator):
    bl_idname='ueimport.select_recoverable_meshes'
    bl_label='Select Recoverable Mesh Anchors'
    bl_description='Select visible missing mesh anchors in the selected original level whose exact native UE5.6 mesh packages are now available'
    @classmethod
    def poll(cls,context):return UEIMPORT_OT_import_map.poll(context)
    def execute(self,context):
        try:
            s=context.scene.ueimport_project
            project,_,maps=discover_maps(bpy.path.abspath(s.project_path));selected=s.maps[s.active].filepath
            if project!=s.scanned_project or selected not in {p for _,p in maps}:raise ValueError('Project or map changed; scan again')
            owners=[c for c in context.scene.collection.children_recursive if c.get('UE_source_map_path')==selected]
            if len(owners)!=1:raise ValueError('Import the selected map once before selecting recoverable anchors')
            from project_paths import ProjectPaths
            from ue5_editor_repair import source_identity
            from import_workflow import table_scope
            p=ProjectPaths(project);eligible=[];verified={}
            with table_scope():
                for o in owners[0].objects:
                    if o.type!='EMPTY' or o.get('UE_geometry_status')!='missing' or not o.get('UE_preview_only') or any(c.get('UE_repair_child') for c in o.children):continue
                    if not o.visible_get() or o.hide_select:continue
                    package=o.get('UE_mesh_package','')
                    if package not in verified:
                        try:source_identity(Path(p.resolve_package(package)),package);verified[package]=True
                        except (ValueError,OSError,TypeError):verified[package]=False
                    if verified[package]:eligible.append(o)
            if not eligible:raise ValueError('No visible unrepaired anchors with verified available mesh packages; activate the selected level or restore sources first')
            for o in context.selected_objects:o.select_set(False)
            for o in eligible:o.select_set(True)
            context.view_layer.objects.active=eligible[0]
            self.report({'INFO'},f'Selected {len(eligible)} recoverable mesh anchors');return {'FINISHED'}
        except Exception as exc:self.report({'ERROR'},str(exc));return {'CANCELLED'}


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
    def poll(cls,context): return not cls._active and not UEIMPORT_OT_level_set._active

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
        state=context.scene.ueimport_project
        layout=self.layout
        busy=UEIMPORT_OT_level_set._active or UEIMPORT_OT_batch._active
        if busy:
            layout.label(text=state.batch_status or 'Import in progress',icon='TIME')
            layout.label(text='Esc: stop at the next safe boundary')
            return
        layout.prop(state,'project_path',text='Project')
        layout.operator('ueimport.scan_project',icon='FILE_REFRESH')
        ready=UEIMPORT_OT_import_map.poll(context)
        if state.scanned_project and not ready:
            layout.label(text='Project changed or no levels; scan again',icon='INFO')
        if ready:
            layout.label(text=f'Engine: {state.engine} | {len(state.maps)} levels')
            try: redirects=len(json.loads(state.map_redirectors)) if state.map_redirectors else 0
            except (ValueError,TypeError): redirects=0
            if redirects:layout.label(text=f'{redirects} redirector(s) excluded',icon='INFO')
            layout.template_list('UEIMPORT_UL_maps','unreal_maps',state,'maps',state,'active',rows=5)
            row=layout.row(align=True);row.operator('ueimport.check_maps',text='All').enabled=True;row.operator('ueimport.check_maps',text='None').enabled=False
            checked=sum(m.enabled for m in state.maps)
            layout.label(text=f'{checked} of {len(state.maps)} levels checked')
            layout.operator('ueimport.scene_dependencies',icon='VIEWZOOM')
            selected=state.maps[state.active].filepath
            if state.scene_summary_source==selected:
                actions=layout.box()
                for line in state.scene_summary.split('; '):actions.label(text=line)
                draw_report_row(actions,context,'ACTIONS','Read Source Actions')
            imported=any(c.get('UE_full_scene_source')==selected for c in context.scene.collection.children_recursive)
            row=layout.row();row.operator_context='INVOKE_DEFAULT';row.enabled=not imported;row.scale_y=1.3;row.operator('ueimport.full_scene',text='Import Selected Level',icon='SCENE_DATA')
            row=layout.row();row.operator_context='INVOKE_DEFAULT';row.enabled=checked>0;row.operator('ueimport.level_set',text='Import Checked Levels',icon='SCENE_DATA')
            if imported:layout.label(text='Selected level already imported',icon='CHECKMARK')
            draw_report_row(layout,context,'LEVEL','Read Selected Level Report')
            draw_report_row(layout,context,'SET','Read Level Set Report')
            row=layout.row();row.enabled=any(c.get('UE_project_level_set') and any(x.get('UE_full_scene_source')==selected for x in c.children) for c in context.scene.collection.children_recursive);row.operator('ueimport.activate_level',icon='HIDE_OFF')
        if state.batch_status:layout.label(text=state.batch_status)
        draw_report_row(layout,context,'LATEST','Read Last Operation Report')
        def fold(prop):
            section=layout.box();section.prop(state,prop,icon='TRIA_DOWN' if getattr(state,prop) else 'TRIA_RIGHT',emboss=False)
            return section if getattr(state,prop) else None
        section=fold('show_options')
        if section:
            section.prop(state,'partial_materials',text='Allow partial material previews')
            section.prop(state,'scene_cache_mib');section.prop(state,'strict_scene_dependencies');section.prop(state,'light_preview_scale')
        section=fold('show_recovery')
        if section:
            section.prop(state,'recovery_folder',text='Folder');section.operator('ueimport.locate_sources',icon='VIEWZOOM')
            scope=recovery_scope(context);plan=recovery_report(context)
            if scope and scope==state.source_recovery_scope and state.source_recovery_status:
                for line in state.source_recovery_status.split('; '):section.label(text=line)
            if plan is not None:
                draw_report_row(section,context,'RECOVERY','Read Recovery Plan')
                if plan.get('UE_recovery_ready',0)>0:section.operator('ueimport.restore_sources',icon='FILE_REFRESH')
                else:section.label(text='No verified packages to restore',icon='INFO')
            elif state.source_recovery_plan:section.label(text='Selection or folder changed; locate again',icon='INFO')
            section.operator('ueimport.select_recoverable_meshes',icon='RESTRICT_SELECT_OFF');section.operator('ueimport.repair_missing_meshes',icon='FILE_REFRESH')
        section=fold('show_environment')
        if section:
            section.operator('ueimport.apply_sky_preview',icon='WORLD');section.operator('ueimport.toggle_fog_preview');section.label(text='Approximate sky and fog previews')
        section=fold('show_batch')
        if section:
            box=section
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
            draw_report_row(box,context,'LATEST','Read Last Operation Report')
            box.label(text='Esc stops between jobs; save to resume')
            box.label(text='Existing verified jobs are reused')
        section=fold('show_tools')
        if section:
            section.operator('ueimport.native_texture',icon='IMAGE_DATA');section.operator('ueimport.wind_preview',icon='GEOMETRY_NODES')
            section.prop(state,'materials');section.operator('ueimport.import_selected_map',icon='IMPORT')
            section.prop(state,'cooked_profile');section.prop(state,'geometry_folder');section.prop(state,'geometry_physics')
            if state.cooked_profile=='5.6':section.prop(state,'geometry_all_lods')
            section.prop(state,'components');section.prop(state,'static_materials');section.prop(state,'partial_materials')
            section.operator('ueimport.geometry_gallery',icon='OUTLINER_OB_ARMATURE');section.operator('ueimport.reconstruct_static',icon='MESH_DATA')
            section.operator('ueimport.lighting_preview',icon='LIGHT');section.operator('ueimport.camera_preview',icon='CAMERA_DATA')
        layout.label(text='Unsupported source data is reported.',icon='INFO')


CLASSES = (UEIMPORT_Map, UEIMPORT_UL_maps, UEIMPORT_OT_check_maps, UEIMPORT_OT_level_set, UEIMPORT_OT_activate_level, UEIMPORT_Job, UEIMPORT_UL_jobs, UEIMPORT_Settings, UEIMPORT_OT_scan, UEIMPORT_OT_import_map, UEIMPORT_OT_reconstruct_static, UEIMPORT_OT_scene_dependencies, UEIMPORT_OT_copy_scene_actions, UEIMPORT_OT_report, UEIMPORT_OT_locate_sources, UEIMPORT_OT_restore_sources, UEIMPORT_OT_full_scene, UEIMPORT_OT_apply_sky_preview, UEIMPORT_OT_toggle_fog_preview, UEIMPORT_OT_select_recoverable_meshes, UEIMPORT_OT_repair_missing, UEIMPORT_OT_lighting_preview, UEIMPORT_OT_camera_preview, UEIMPORT_OT_geometry_gallery, UEIMPORT_OT_refresh_jobs, UEIMPORT_OT_check_jobs, UEIMPORT_OT_preflight, UEIMPORT_OT_batch, UEIMPORT_PT_project)


def register():
    for cls in CLASSES:
        bpy.utils.register_class(cls)
    bpy.types.Scene.ueimport_project = PointerProperty(type=UEIMPORT_Settings)


def unregister():
    del bpy.types.Scene.ueimport_project
    for cls in reversed(CLASSES):
        bpy.utils.unregister_class(cls)
