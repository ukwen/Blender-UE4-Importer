"""Owned file-menu entry points; legacy compatibility is invoked only on demand.

Operator IDs and saved settings remain stable. The old backends are still
present for non-migrated operations; registration itself never imports them.
"""
from pathlib import Path
import bpy
from bpy.props import StringProperty, BoolProperty, FloatProperty, CollectionProperty
from bpy_extras.io_utils import ImportHelper
import addon_lifecycle


def selected_paths(operator):
    return [Path(operator.directory)/item.name for item in operator.files if item.name] or [Path(operator.filepath)]


def run_files(operator, action):
    paths=selected_paths(operator); succeeded=0; errors=[]
    for path in paths:
        try:
            if not path.is_file(): raise FileNotFoundError(path)
            action(path); succeeded+=1
        except Exception as exc:
            errors.append(f'{path.name}: {type(exc).__name__}: {exc}')
    for error in errors: print(error)
    operator.report({'WARNING'} if errors else {'INFO'},f'Imported {succeeded}/{len(paths)} packages; {len(errors)} failed (see console)')
    return {'FINISHED'} if succeeded else {'CANCELLED'}


def import_mesh(path, materials, all_lods):
    # Geometry-only supported editor meshes need no legacy module. Full graph
    # and other profiles retain the previous compatibility implementation.
    if not materials:
        from package_inspector import inspect_package
        meta=inspect_package(path)
        data=mesh=None
        if meta.get('ue5') is None and not meta['sidecars']:
            if meta.get('ue4')==508:
                from legacy_static import read_legacy_static_path, build_legacy_static
                from package_records import read_package
                _,_,table=read_package(path)
                if any(e.kind=='StaticMesh' and not e.outer for e in table.exports):
                    mesh=build_legacy_static(read_legacy_static_path(path))
            elif meta.get('ue4')==522:
                from package_records import read_package
                _,_,table=read_package(path)
                if any(e.kind=='StaticMesh' and not e.outer for e in table.exports):
                    from editor_static522 import read_static, build_static, UnsupportedProfile
                    try: data=read_static(path)
                    except UnsupportedProfile: pass
                    else: mesh=build_static(data)
        if mesh is not None:
            if all_lods: mesh.name += '_LOD0'
            try:
                obj=bpy.data.objects.new(mesh.name,mesh);bpy.context.collection.objects.link(obj)
            except Exception:
                if mesh.users==0:bpy.data.meshes.remove(mesh)
                raise
            return [obj]
    from umesh import ImportUMeshAsObject
    return ImportUMeshAsObject(str(path),materials=materials,all_lods=all_lods)


class ImportMesh(bpy.types.Operator, ImportHelper):
    bl_idname='import.umesh'
    bl_label='Import Unreal Mesh'
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'},maxlen=255)
    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={'HIDDEN','SKIP_SAVE'})
    directory: StringProperty(options={'HIDDEN'})
    materials: BoolProperty(name='Materials',default=True)
    all_lods: BoolProperty(name='All static source LODs',default=False)

    def execute(self,context):
        return run_files(self,lambda path:import_mesh(path,self.materials,self.all_lods))


def import_material(path):
    from package_inspector import inspect_package
    meta=inspect_package(path)
    if meta.get('ue4')==508 and meta.get('ue5') is None and not meta['sidecars']:
        from classic_material import read_material, build_material
        try: data=read_material(path)
        except NotImplementedError: pass  # non-basic graphs retain the compatibility route
        else:
            from project_paths import ProjectPaths
            from project_session import new_ids, rollback_new
            before=set(new_ids())
            try:
                mat=build_material(ProjectPaths(path),path,data)
                mat.use_fake_user=True  # keep a directly imported, unassigned material on reopen
                return mat
            except Exception:
                rollback_new(before)
                raise
    from umat import ImportNodeGraph
    return ImportNodeGraph(str(path))


class ImportMaterial(bpy.types.Operator, ImportHelper):
    bl_idname='import.umat'
    bl_label='Import Unreal Material'
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'},maxlen=255)
    files: CollectionProperty(type=bpy.types.OperatorFileListElement,options={'HIDDEN','SKIP_SAVE'})
    directory: StringProperty(options={'HIDDEN'})

    def execute(self,context):
        return run_files(self,import_material)


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
    self.layout.operator(ImportLevel.bl_idname,text='UE Map (.umap)')
    self.layout.operator(ImportMesh.bl_idname,text='UE Mesh (.uasset)')
    self.layout.operator(ImportMaterial.bl_idname,text='UE Material (.uasset)')


CLASSES=(ImportMesh,ImportMaterial,ImportLevel)
def register():
    addon_lifecycle.register(CLASSES,bpy.types.TOPBAR_MT_file_import,draw_menu)
def unregister():
    addon_lifecycle.unregister(CLASSES,bpy.types.TOPBAR_MT_file_import,draw_menu)
