"""Owned file-menu entry points; legacy compatibility is invoked only on demand.

Operator IDs and saved settings remain stable. The old backends are still
present for non-migrated operations; registration itself never imports them.
"""
from pathlib import Path
import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, CollectionProperty, EnumProperty
from bpy_extras.io_utils import ImportHelper
import addon_lifecycle


def selected_paths(operator):
    return [Path(operator.directory)/item.name for item in operator.files if item.name] or [Path(operator.filepath)]


def run_files(operator, action):
    paths=selected_paths(operator); succeeded=0; errors=[]; previews=0
    for path in paths:
        try:
            if not path.is_file(): raise FileNotFoundError(path)
            result=action(path); succeeded+=1
            if isinstance(result,list) and any(isinstance(o,bpy.types.Object) and o.get("UE_unresolved_material") for o in result):
                previews+=1
            if isinstance(result,bpy.types.Material) and result.get("UE_unresolved_material"):
                previews+=1;print(f"{path.name}: {result.get('UE_editor_material_status','partial')} — source graph limitations recorded in material properties")
        except Exception as exc:
            errors.append(f'{path.name}: {type(exc).__name__}: {exc}')
    for error in errors: print(error)
    operator.report({'WARNING'} if errors or previews else {'INFO'},f'Imported {succeeded}/{len(paths)} packages; {len(errors)} failed; {previews} unresolved previews (see console)')
    return {'FINISHED'} if succeeded else {'CANCELLED'}


def import_mesh(path, materials, all_lods, cooked_profile='NONE'):
    """Use native mesh routes only, unless legacy compatibility is explicitly selected."""
    import json
    from package_inspector import inspect_package
    from package_records import read_package
    from project_paths import ProjectPaths
    from project_session import new_ids, rollback_new
    path=Path(path).resolve(); meta=inspect_package(path)
    before=set(new_ids()); meshes=[]
    try:
        if cooked_profile=='LEGACY':
            from umesh import ImportUMeshAsObject
            return ImportUMeshAsObject(str(path),materials=materials,all_lods=all_lods)
        if path.with_suffix('.uexp').is_file():
            from project_geometry import root_class, load_static
            if cooked_profile=='NONE':
                raise ValueError('Select the cooked asset profile explicitly for split packages')
            kind=root_class(path,ProjectPaths(path))
            if kind=='StaticMesh':
                if all_lods: raise NotImplementedError('All cooked static LODs are not supported')
                mesh=load_static(path,ProjectPaths(path),cooked_profile)
                obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
                objects=[obj]
            elif kind=='SkeletalMesh':
                if all_lods:
                    if cooked_profile!='5.6': raise NotImplementedError('All cooked skeletal LODs require UE5.6')
                    from skeletal_lod_group import build_lod_group
                    _,objects=build_lod_group(path)
                else:
                    from skeletal_mesh_native import read_native_mesh,build_mesh
                    obj,_=build_mesh(read_native_mesh(path,cooked_profile));objects=[obj]
            else: raise NotImplementedError('Not a supported split mesh: '+kind)
            for obj in objects:
                obj['UE_source_package']=str(path)
                obj['UE_cooked_profile']=cooked_profile
                obj['UE_unresolved_material']=bool(materials and len(obj.data.materials))
                obj['UE_cooked_material_status']='slot identities only; cooked shader reconstruction unsupported'
            return objects
        if meta.get('status')=='tables_inspected' and not meta.get('flags',0)&0x80002000 and not meta.get('sidecars') and meta.get('ue4') in (508,522) and meta.get('ue5') in (None,1016,1017):
            _,_,table=read_package(path)
            if any(e.kind=='StaticMesh' and not e.outer for e in table.exports):
                if meta['ue5'] in (1016,1017):
                    from ue5_editor_mesh import read_static,build_static
                    meshes=[build_static(read_static(path))]
                elif meta['ue4']==508:
                    from legacy_static import read_legacy_static_path,build_legacy_static
                    meshes=[build_legacy_static(read_legacy_static_path(path))]
                else:
                    from editor_static522 import read_static_lods,build_static
                    data=read_static_lods(path)
                    meshes=[build_static(d) for d in (data if all_lods else data[:1])]
            elif any(e.kind=='SkeletalMesh' and not e.outer for e in table.exports):
                if all_lods:
                    raise NotImplementedError('All source LODs currently supported for static meshes only')
                if meta['ue5'] in (1016,1017):
                    from ue5_editor_mesh import read_skeletal,build_skeletal
                    obj,arm=build_skeletal(read_skeletal(path))
                else:
                    from skeletal_mesh_native import read_native_mesh,build_mesh
                    obj,arm=build_mesh(read_native_mesh(path,'4.27'))
                if materials:
                    from material_stage import MaterialResolver,bind_native_mesh_slots
                    resolver=MaterialResolver(ProjectPaths(path),allow_partial=True)
                    bind_native_mesh_slots(obj.data,resolver)
                    obj['UE_material_report']=json.dumps(resolver.records,sort_keys=True)
                    obj['UE_unresolved_material']=any(r['status']!='graph_imported_unverified' for r in resolver.records.values())
                return [obj]
        if meshes:
            objects=[]
            if materials:
                from material_stage import MaterialResolver,bind_native_mesh_slots
                resolver=MaterialResolver(ProjectPaths(path),allow_partial=True)
                for mesh in meshes: bind_native_mesh_slots(mesh,resolver)
            for i,mesh in enumerate(meshes):
                if all_lods: mesh.name+=f"_LOD{mesh.get('UE_lod_index',0)}"
                obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
                if all_lods and i: obj.hide_set(True);obj.hide_render=True
                if materials:
                    obj['UE_material_report']=json.dumps(resolver.records,sort_keys=True)
                    obj['UE_unresolved_material']=any(r['status']!='graph_imported_unverified' for r in resolver.records.values())
                    if obj['UE_unresolved_material']: print(path.name+': unresolved material branches; see UE_material_report')
                objects.append(obj)
            return objects
    except Exception:
        rollback_new(before);raise
    raise NotImplementedError('Native mesh profile unsupported or package is not a mesh; select Legacy compatibility explicitly if required')


class ImportMesh(bpy.types.Operator, ImportHelper):
    bl_idname='import.umesh'
    bl_label='Import Unreal Mesh'
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'},maxlen=255)
    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={'HIDDEN','SKIP_SAVE'})
    directory: StringProperty(options={'HIDDEN'})
    materials: BoolProperty(name='Materials',default=True)
    all_lods: BoolProperty(name='All supported source LODs',default=False)
    cooked_profile: EnumProperty(name='Mesh import profile',items=[('NONE','Native editor (select profile if cooked)','Required for split packages'),('LEGACY','Legacy compatibility (editor or cooked)','Explicitly use the historical mesh importer for unsupported packages'),('4.18','UE4.18','Legacy buffers'),('4.27','UE4.27','Separate buffers'),('5.0','UE5.0','Bounded cooked geometry'),('5.4','UE5.4','Bounded cooked static'),('5.5','UE5.5','Bounded cooked static'),('5.6','UE5.6','Bounded cooked geometry')],default='NONE')

    def execute(self,context):
        return run_files(self,lambda path:import_mesh(path,self.materials,self.all_lods,self.cooked_profile))


def import_material(path, allow_partial=False, profile='NONE'):
    from package_inspector import inspect_package
    from project_paths import ProjectPaths
    from project_session import new_ids, rollback_new
    path=Path(path).resolve();meta=inspect_package(path)
    before=set(new_ids())
    try:
        if profile=='LEGACY':
            from umat import ImportNodeGraph
            return ImportNodeGraph(str(path))
        if profile!='NONE':
            from cooked_material_catalog import import_cooked_material
            return import_cooked_material(path,profile,allow_partial)
        if meta.get('sidecars'):
            raise NotImplementedError('Select an explicit cooked material profile')
        if meta.get('ue5') in (1004,1012,1013,1014,1015,1016,1017,1018) and not meta['sidecars'] and not meta.get('flags',0)&0x80002000:
            from ue5_editor_material import build_material
            project=ProjectPaths(path);content=(Path(project.dir)/'Content').resolve()
            if not path.is_relative_to(content):raise ValueError('Select a material inside its original project Content directory')
            package='/Game/'+path.relative_to(content).with_suffix('').as_posix()
            mat=build_material(content,package,allow_partial=allow_partial)
            mat.use_fake_user=True
            return mat
        if meta.get('ue4') in (508,522) and meta.get('ue5') is None and not meta['sidecars']:
            if meta['ue4']==522 and not meta.get('flags',0)&0x80002000 and meta.get('status')=='tables_inspected':
                from package_records import read_package
                from layer_function_graph import USAGES,load_function
                _,_,table=read_package(path)
                if any(e.kind in USAGES and not e.outer for e in table.exports):
                    try:group,_=load_function(path)
                    except NotImplementedError:pass
                    else:
                        group.use_fake_user=True
                        return group
            from classic_material import read_material, build_material
            try: data=read_material(path)
            except NotImplementedError:
                if meta['ue4']==522:
                    from classic_material_graph import read_graph
                else:
                    from classic_particle_material import read_graph
                try: graph=read_graph(path)
                except NotImplementedError: pass
                else:
                    if graph['kind'] in ('material','instance'):
                        from ue5_editor_material import build_material as build_graph
                        project=ProjectPaths(path);content=(Path(project.dir)/'Content').resolve()
                        if not path.is_relative_to(content):raise ValueError('Material outside project Content directory')
                        mat=build_graph(content,'/Game/'+path.relative_to(content).with_suffix('').as_posix(),allow_partial=allow_partial)
                        mat.use_fake_user=True
                        return mat
            else:
                mat=build_material(ProjectPaths(path),path,data)
                mat.use_fake_user=True
                return mat
        raise NotImplementedError('Native material graph profile unsupported; select Legacy compatibility explicitly if needed')
    except Exception:
        rollback_new(before)
        raise


class ImportMaterial(bpy.types.Operator, ImportHelper):
    bl_idname='import.umat'
    bl_label='Import Unreal Material'
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'},maxlen=255)
    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={'HIDDEN','SKIP_SAVE'})
    directory: StringProperty(options={'HIDDEN'})

    allow_partial: BoolProperty(name='Allow partial material preview',description='Preview supported branches; unresolved source expressions remain reported',default=False)

    profile: EnumProperty(name='Material import profile',items=[('NONE','Native editor','Editable supported source graph'),('4.18','UE4.18 cooked dependencies','Raw dependencies; optional bounded direct surface preview'),('4.27','UE4.27 cooked dependencies','Raw texture dependencies, shader unresolved'),('5.0','UE5.0 cooked dependencies','Raw texture dependencies, shader unresolved'),('LEGACY','Legacy compatibility','Explicit historical graph importer')],default='NONE')

    def execute(self,context):
        return run_files(self,lambda path:import_material(path,self.allow_partial,self.profile))


def import_saved_levels(paths, partial=False, strict=False, preview_scale=1., profile='4.27'):
    """Use the same atomic native saved-project transaction as the project browser.

    No fallback to the historical map operator. Require one original project;
    independent levels are grouped without inventing runtime streaming transforms.
    """
    from project_paths import ProjectPaths
    from saved_project_levels import reconstruct
    paths=[Path(p).resolve() for p in paths]
    if not paths:
        raise ValueError('Select at least one saved level')
    project=ProjectPaths(paths[0]).descriptor
    if project is None or any(ProjectPaths(p).descriptor != project for p in paths):
        raise ValueError('Select saved levels inside one original Unreal project with its .uproject')
    return reconstruct(project,paths,partial,preview_scale,strict,profile)


class ImportSavedLevel(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_saved_level'
    bl_label='Import Unreal Saved Level'
    bl_description='Reconstruct saved levels into editable Blender scenes; retain unresolved dependencies in the scene report'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.umap'
    filter_glob: StringProperty(default='*.umap',options={'HIDDEN'},maxlen=255)
    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={'HIDDEN','SKIP_SAVE'})
    directory: StringProperty(options={'HIDDEN'})
    allow_partial: BoolProperty(name='Keep incomplete surface previews',default=False)
    strict_dependencies: BoolProperty(name='Require resolved source dependencies',default=False)
    preview_scale: FloatProperty(name='Light preview multiplier',default=1.,min=.001,max=1000.)
    cooked_profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Legacy buffers'),('4.27','UE4.27','Separate buffers'),('5.0','UE5.0','Bounded cooked geometry'),('5.4','UE5.4','Bounded cooked static'),('5.5','UE5.5','Bounded cooked static'),('5.6','UE5.6','Bounded cooked geometry')],default='4.27')

    def execute(self,context):
        try:
            group,report=import_saved_levels(selected_paths(self),self.allow_partial,self.strict_dependencies,self.preview_scale,self.cooked_profile)
        except Exception as exc:
            self.report({'ERROR'},f'Saved level import failed: {exc}')
            return {'CANCELLED'}
        self.report({'INFO'},f"Imported {len(report['levels'])} saved level(s); see {group['UE_report']}")
        return {'FINISHED'}


class ImportLevel(bpy.types.Operator, ImportHelper):
    bl_idname='import.umap'
    bl_label='Import Unreal Level (compatibility)'
    filename_ext='.umap'
    filter_glob: StringProperty(default='*.umap',options={'HIDDEN'},maxlen=255)
    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={'HIDDEN','SKIP_SAVE'})
    directory: StringProperty(options={'HIDDEN'})
    folders: BoolProperty(name='Collections',default=True)
    meshes: BoolProperty(name='Meshes',default=True)
    materials: BoolProperty(name='Materials',default=True)
    cameras: BoolProperty(name='Cameras',default=True)
    lights_point: BoolProperty(name='Point Lights',default=False)
    lights_spot: BoolProperty(name='Spot Lights',default=True)
    lights_dir: BoolProperty(name='Directional Lights',default=True)
    cubemaps: BoolProperty(name='Cubemaps',default=True)
    lightprobes: BoolProperty(name='Irradiance Volumes',default=True)
    force_shadows: BoolProperty(name='Force Shadows',default=False)
    light_intensity: FloatProperty(name='Light Brightness',default=1,min=0)
    light_angle_coef: FloatProperty(name='Light Angle',default=1,min=0)

    def execute(self,context):
        from umap import UMapImportSettings, LoadUMap
        names=('folders','meshes','materials','cameras','lights_point','lights_spot','lights_dir','cubemaps','lightprobes','force_shadows','light_intensity','light_angle_coef')
        return run_files(self,lambda path:LoadUMap(str(path),UMapImportSettings(**{key:getattr(self,key) for key in names})))


def draw_menu(self,context):
    self.layout.operator(ImportSavedLevel.bl_idname,text='UE Saved Level (.umap)')
    self.layout.operator(ImportLevel.bl_idname,text='UE Map — Legacy Compatibility (.umap)')
    self.layout.operator(ImportMesh.bl_idname,text='UE Mesh (.uasset)')
    self.layout.operator(ImportMaterial.bl_idname,text='UE Material (.uasset)')
    self.layout.operator('ueimport.native_texture',text='UE Texture (.uasset)')


CLASSES=(ImportMesh,ImportMaterial,ImportSavedLevel,ImportLevel)
def register():
    addon_lifecycle.register(CLASSES,bpy.types.TOPBAR_MT_file_import,draw_menu)
def unregister():
    addon_lifecycle.unregister(CLASSES,bpy.types.TOPBAR_MT_file_import,draw_menu)
