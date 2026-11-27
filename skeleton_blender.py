"""Import verified cooked reference-skeleton profiles without Unreal Engine."""
import bpy
from bpy.props import EnumProperty, StringProperty, FloatProperty, BoolProperty, IntProperty
from bpy_extras.io_utils import ImportHelper
from skeleton_native import read_cooked_skeleton, build_armature

class ImportUESkeleton(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_reference_skeleton'
    bl_label='Import UE reference skeleton'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Tagged split package'),('4.27','UE4.27','Tagged split package'),('5.0','UE5.0','Bounded unversioned split profile')],default='4.27')
    def execute(self,context):
        try:
            from pathlib import Path
            from package_inspector import inspect_package
            data={}
            if Path(self.filepath).with_suffix(".uexp").is_file():
                name,bones=read_cooked_skeleton(self.filepath,self.profile); sockets=[]
            else:
                if inspect_package(self.filepath).get('ue5')==1017:
                    from ue5_editor_skeleton import read_skeleton as read_editor_skeleton
                else:
                    from editor_skeleton import read_editor_skeleton
                data=read_editor_skeleton(self.filepath); name,bones,sockets=data["name"],data["bones"],data["sockets"]
            obj=build_armature(name,bones)
            if sockets:
                import json
                obj["UE_socket_definitions"]=json.dumps(sockets)
            if data.get('skeleton_package'):obj['UE_skeleton_package']=data['skeleton_package']
            if data.get('retarget_sources'):
                import json
                obj['UE_retarget_sources_json']=json.dumps(data['retarget_sources']);obj['UE_skeleton_unparsed_tail_bytes']=data['tail_bytes']
            obj['UE_skeleton_source']=self.filepath; obj['UE_skeleton_profile']=self.profile
            self.report({'INFO'},f'Imported {len(bones)} reference bones (no mesh or skin weights)')
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}

class ImportUESkeletalMesh(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_native_skeletal_mesh'
    bl_label='Import native UE skeletal mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Legacy interleaved buffers'),('4.27','UE4.27','Inline separate render buffers'),('5.0','UE5.0','Bounded unversioned split profile'),('5.6','UE5.6','Bounded fixed-weight inline skeletal LODs')],default='4.18')
    lod: IntProperty(name='Source LOD',description='UE5.6 cooked skeletal LOD index; other profiles require 0',default=0,min=0,max=2)
    all_lods: BoolProperty(name='All native LODs on one rig',description='UE5.6 split skeletal mesh; one rig and shared materials with manual LOD switching',default=False)
    def execute(self,context):
        from skeletal_mesh_native import read_native_mesh, build_mesh
        try:
            from pathlib import Path
            from package_inspector import inspect_package
            if not Path(self.filepath).with_suffix('.uexp').is_file() and inspect_package(self.filepath).get('ue5') in (1016,1017):
                if self.lod or self.all_lods: raise ValueError('Only original editor source LOD0 supported; generated LODs are not reconstructed')
                from ue5_editor_mesh import read_skeletal,build_skeletal
                data=read_skeletal(self.filepath);obj,arm=build_skeletal(data,context.collection)
                obj['UE_source_package']=self.filepath
                self.report({'INFO'},f"Imported {len(data['vertices'])} original editor vertices and {len(data['bones'])} bones")
                return {'FINISHED'}
            if self.all_lods:
                if self.profile!='5.6': raise ValueError('Shared LOD import requires the UE5.6 profile')
                from skeletal_lod_group import build_lod_group
                arm,objects=build_lod_group(self.filepath,context.collection)
                for obj in objects: obj['UE_source_package']=self.filepath
                self.report({'INFO'},f'Imported {len(objects)} native LODs on one editable rig')
                return {'FINISHED'}
            data=read_native_mesh(self.filepath,self.profile,self.lod); obj,arm=build_mesh(data)
            obj['UE_source_package']=self.filepath
            self.report({'INFO'},f"Imported {len(data['positions'])} skinned vertices, {len(data['bones'])} bones (material placeholders)")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class SetUELod(bpy.types.Operator):
    bl_idname='object.ue_set_native_lod'
    bl_label='Set Native UE LOD'
    bl_options={'REGISTER','UNDO'}
    lod: IntProperty(name='Source LOD',default=0,min=0,max=2)
    @classmethod
    def poll(cls,context):
        obj=context.object
        return context.mode=='OBJECT' and obj is not None and obj.type=='ARMATURE' and bool(obj.get('UE_lod_group_count'))
    def execute(self,context):
        from skeletal_lod_group import disable_distance_lod
        try: disable_distance_lod(context.object,self.lod)
        except ValueError as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class EnableUELodDistance(bpy.types.Operator):
    bl_idname='object.ue_enable_lod_distance'
    bl_label='Enable UE LOD Camera Distance'
    bl_description='Use explicit camera distances in metres, not Unreal screen-size thresholds'
    bl_options={'REGISTER','UNDO'}
    near: FloatProperty(name='LOD 1 distance (m)',default=5,min=.01)
    far: FloatProperty(name='LOD 2 distance (m)',default=15,min=.01)
    @classmethod
    def poll(cls,context):
        return SetUELod.poll(context) and context.scene.camera is not None
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self)
    def execute(self,context):
        from skeletal_lod_group import enable_distance_lod
        try: enable_distance_lod(context.object,context.scene.camera,float(self.near),float(self.far))
        except ValueError as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}
        return {'FINISHED'}


class UELodPanel(bpy.types.Panel):
    bl_idname='DATA_PT_ue_native_lods'
    bl_label='Unreal Native LODs'
    bl_space_type='PROPERTIES'
    bl_region_type='WINDOW'
    bl_context='data'
    @classmethod
    def poll(cls,context):
        return SetUELod.poll(context)
    def draw(self,context):
        auto=context.object.get('UE_lod_mode')=='CAMERA_DISTANCE'
        self.layout.label(text='Camera distance mode' if auto else 'Manual selection')
        row=self.layout.row(align=True)
        for i in range(3):
            row.operator(SetUELod.bl_idname,text=f'LOD {i}',depress=not auto and context.object.get('UE_active_lod')==i).lod=i
        if not auto: self.layout.operator(EnableUELodDistance.bl_idname)
        else: self.layout.label(text='Choose a LOD to return to manual mode')


class ImportUEAnimation(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_raw_animation'
    bl_label='Import native UE4.27 / UE5.6 editor animation'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    allow_subset: BoolProperty(name='Allow same-skeleton track subset',description='Omit absent tracks only when original skeleton package identity matches; no engine retargeting',default=False)
    allow_source_preview: BoolProperty(name='Allow additive / retarget source preview',description='Import original authored pose samples only, without Unreal runtime additive or retarget evaluation',default=False)
    apply_rate_scale: BoolProperty(name='Apply source playback rate',description='Use serialized RateScale to retime the Action; otherwise preserve authored source time',default=False)
    root_translation_mode: EnumProperty(name='Authored root translation',items=[('SOURCE','Original','Keep original root translation'),('IN_PLACE','In-place + trajectory','Lock root translation to first authored sample; keep editable relative trajectory in meters; not Unreal runtime extraction')],default='SOURCE')
    start_frame: FloatProperty(name='Start frame',default=1.,min=0.,max=100000.)
    @classmethod
    def poll(cls,context):
        return context.object is not None and context.object.type=='ARMATURE' and context.object.mode=='OBJECT'
    def execute(self,context):
        from animation_native import read_animation, make_action
        try:
            data=read_animation(self.filepath)
            action=make_action(context.object,data,context.scene,self.start_frame,self.allow_subset,self.apply_rate_scale,self.allow_source_preview,self.root_translation_mode)
            self.report({'INFO'},f"Imported {data['frames']} raw samples, {len(data['tracks'])} tracks, {len(data.get('scalar_curves',{}))} scalar curves; runtime effects not evaluated")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError,KeyError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class ImportUECookedStatic(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_cooked_static'
    bl_label='Import native cooked UE static mesh'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked asset profile',items=[('4.18','UE4.18','Interleaved buffers'),('4.27','UE4.27','Separate inline buffers'),('5.0','UE5.0','Bounded unversioned split profile'),('5.4','UE5.4','Bounded cooked static only'),('5.5','UE5.5','Bounded cooked static only'),('5.6','UE5.6','Bounded cooked static only')],default='4.27')
    def execute(self,context):
        from cooked_static import read_static,build_static
        try:
            data=read_static(self.filepath,self.profile); mesh=build_static(data)
            obj=bpy.data.objects.new(mesh.name,mesh); context.collection.objects.link(obj)
            obj['UE_source_package']=self.filepath
            self.report({'INFO'},f"Imported {len(mesh.vertices)} vertices, {len(mesh.polygons)} triangles (material placeholders)")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


class ImportUECookedMaterialInstance(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_cooked_material_instance'
    bl_label='Inspect cooked UE material instance'
    bl_description='Recover native source parameters and package identities; parent shader remains unresolved'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    profile: EnumProperty(name='Cooked material profile',items=[('5.4','UE5.4','Bounded instance parameter schema'),('5.6','UE5.6','Bounded instance parameter schema')],default='5.4')
    def execute(self,context):
        from ue5_cooked_material import read_instance,attach_instance_metadata
        mat=None
        try:
            data=read_instance(self.filepath,self.profile)
            mat=bpy.data.materials.new(data['name']);mat['UE_material_package']=data['source_package'];mat.use_fake_user=True
            attach_instance_metadata(mat,data)
            self.report({'INFO'},f"Recovered {len(data['parameters'])} native material parameters; parent shader unresolved")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError) as exc:
            if mat is not None: bpy.data.materials.remove(mat)
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class BindUEAccessory(bpy.types.Operator):
    bl_idname='object.ue_bind_accessory'
    bl_label='UE Bind Compatible Skeletal Accessory'
    bl_description='Select one native accessory mesh and its target armature (active). Align in verified reference space; keep original rig'
    bl_options={'REGISTER','UNDO'}
    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and context.object is not None and context.object.type=='ARMATURE' and len(context.selected_objects)==2 and any(o.type=='MESH' for o in context.selected_objects)
    def execute(self,context):
        from native_attachments import bind_compatible_accessory
        try:
            mesh=next(o for o in context.selected_objects if o.type=='MESH')
            bind_compatible_accessory(mesh,context.object)
            self.report({'INFO'},'Accessory bound; original armature retained')
            return {'FINISHED'}
        except ValueError as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}



class ImportUEPhysics(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_physics_asset'
    bl_label='Import UE Physics Asset (collision preview)'
    bl_description='Attach source collision capsules and joint frames to the selected native rig; does not enable simulation'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and context.object is not None and context.object.type=='ARMATURE' and bool(context.object.get('UE_source_mesh_path'))
    def execute(self,context):
        from physics_native import read_physics,build_physics
        try:
            arm=context.object;data=read_physics(self.filepath);objects=build_physics(arm,data,arm['UE_source_mesh_path'])
            self.report({'INFO'},f"Created {len(objects)} collision/joint preview objects; no simulation enabled")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}

class ImportUEEditorCharacter(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue_editor_character'
    bl_label='Import UE5.6 Blueprint Character Preview'
    bl_description='Reconstruct explicit saved character CDO body and root; no Blueprint runtime or native constructor execution'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    materials: BoolProperty(name='Import editor materials',default=True)
    partial: BoolProperty(name='Allow partial material previews',default=False)
    sockets: BoolProperty(name='Create available native sockets',default=True)
    def execute(self,context):
        from ue5_editor_components import build_character_preview
        try:
            anchor,obj,arm=build_character_preview(self.filepath,context.collection,self.materials,self.partial,self.sockets)
            self.report({'INFO'},'Imported authored CDO character preview; runtime defaults unresolved');return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,NotImplementedError,KeyError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


class ImportUE57Blueprint(bpy.types.Operator, ImportHelper):
    bl_idname='import.ue57_blueprint_preview'
    bl_label='Import UE5.7 Blueprint Component Preview'
    bl_description='Inspect serialized CDO and SCS topology; unresolved sockets and runtime components remain metadata-only'
    bl_options={'REGISTER','UNDO'}
    filename_ext='.uasset'
    filter_glob: StringProperty(default='*.uasset',options={'HIDDEN'})
    def execute(self,context):
        from ue5_editor_blueprint import build_preview
        try:
            target,data=build_preview(self.filepath,context.collection)
            self.report({'INFO'},f"{len(target.objects)} component anchors; {len(data['components'])-len(target.objects)} metadata-only. See report.")
            return {'FINISHED'}
        except (OSError,ValueError,RuntimeError,KeyError,TypeError) as exc:
            self.report({'ERROR'},str(exc));return {'CANCELLED'}


def menu(self,context):
    self.layout.operator(ImportUE57Blueprint.bl_idname,text="UE5.7 Blueprint Component Preview (.uasset)")
    self.layout.operator(ImportUEEditorCharacter.bl_idname,text="UE5.6 Blueprint Character Preview (.uasset)")
    self.layout.operator(ImportUECookedMaterialInstance.bl_idname,text='UE Cooked Material Instance Parameters (.uasset)')
    self.layout.operator(ImportUEPhysics.bl_idname,text='UE Physics Asset — Collision Preview (.uasset)')
    self.layout.operator(ImportUECookedStatic.bl_idname,text='UE Native Cooked Static Mesh (.uasset)')
    self.layout.operator(ImportUESkeleton.bl_idname,text='UE Reference Skeleton (.uasset)')
    self.layout.operator(ImportUESkeletalMesh.bl_idname,text='UE Native Skeletal Mesh (.uasset)')
    self.layout.operator(ImportUEAnimation.bl_idname,text='UE4.27 / UE5.6 Editor Animation (.uasset)')
def register():
    import native_sockets
    native_sockets.register()
    bpy.utils.register_class(ImportUE57Blueprint)
    bpy.utils.register_class(ImportUEEditorCharacter)
    bpy.utils.register_class(SetUELod); bpy.utils.register_class(EnableUELodDistance); bpy.utils.register_class(UELodPanel)
    bpy.utils.register_class(ImportUECookedMaterialInstance); bpy.utils.register_class(ImportUEPhysics); bpy.utils.register_class(BindUEAccessory); bpy.utils.register_class(ImportUECookedStatic); bpy.utils.register_class(ImportUESkeleton); bpy.utils.register_class(ImportUESkeletalMesh); bpy.utils.register_class(ImportUEAnimation); bpy.types.TOPBAR_MT_file_import.append(menu)
def unregister():
    import native_sockets
    bpy.utils.unregister_class(UELodPanel); bpy.utils.unregister_class(EnableUELodDistance); bpy.utils.unregister_class(SetUELod)
    native_sockets.unregister()
    bpy.utils.unregister_class(ImportUEEditorCharacter)
    bpy.utils.unregister_class(ImportUE57Blueprint)
    bpy.types.TOPBAR_MT_file_import.remove(menu); bpy.utils.unregister_class(ImportUEAnimation); bpy.utils.unregister_class(ImportUESkeletalMesh); bpy.utils.unregister_class(ImportUESkeleton); bpy.utils.unregister_class(ImportUECookedStatic); bpy.utils.unregister_class(BindUEAccessory); bpy.utils.unregister_class(ImportUEPhysics); bpy.utils.unregister_class(ImportUECookedMaterialInstance)
