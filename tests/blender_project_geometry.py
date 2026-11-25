"""Mixed native project gallery and cached cooked static level dependency routing."""
import json,os,sys,tempfile,shutil
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser, project_geometry as pg, static_scene, uasset

bpy.ops.wm.read_factory_settings(use_empty=True)
profile=os.environ.get('UE_GALLERY_PROFILE','4.27')
source=Path(os.environ['MATYA_ASSETS'])/profile
with tempfile.TemporaryDirectory() as temp:
    root=Path(temp); descriptor=root/'Gallery.uproject'; descriptor.write_text('{"EngineAssociation":"4.27"}')
    folder=root/'Content'/'Assets'; folder.mkdir(parents=True)
    # Renamed packages demonstrate class-based routing, not SM_/SK_ name guesses.
    for old,new in [('SM_Worm','A_static'),('SK_Worm','B_character'),('SK_Worm_Skeleton','C_skeleton'),('SM_Worm','D_broken')]:
        shutil.copyfile(source/(old+'.uasset'),folder/(new+'.uasset'))
        shutil.copyfile(source/(old+'.uexp'),folder/(new+'.uexp'))
    broken=folder/'D_broken.uexp'; broken.write_bytes(broken.read_bytes()[:-12])
    shutil.copyfile(os.environ['UE_ROPE_ASSET'],folder/'E_editor.uasset')
    browser.register()
    try:
        state=bpy.context.scene.ueimport_project; state.project_path=str(descriptor); state.geometry_folder='Assets'; state.cooked_profile=profile
        assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
        assert bpy.ops.ueimport.geometry_gallery()=={'FINISHED'}
        collection=next(c for c in bpy.data.collections if c.name.startswith('UE native geometry gallery'))
        report=json.loads(bpy.data.texts[collection['UE_report']].as_string())
        print('GALLERY',report)
        assert report['counts']=={'reconstructed':3,'skipped_non_geometry':1,'failed':1}
        assert report['totals']=={'vertices':1312,'triangles':1204,'bones':6}
        assert len(collection.objects)==4
        obj=next(o for o in collection.objects if o.get('UE_mesh_package')=='/Game/Assets/B_character')
        assert obj.parent.type=='ARMATURE' and obj.modifiers[0].object==obj.parent and len(obj.vertex_groups)==6
        # Cooked geometry now uses the same resolver as the actual static map workflow.
        resolver=static_scene.MeshResolver(uasset.UProject(str(descriptor)),profile)
        a,status=resolver('/Game/Assets/A_static'); b,status2=resolver('/Game/Assets/A_static')
        assert status==status2=='reconstructed' and a==b and resolver.decode_attempts==1
        assert len(a.vertices)==640 and json.loads(a['UE_material_bindings'])==[['M_Worm','/Game/M_Worm']]
        assert len(a.attributes['UE_source_material_index'].data)==572
        # Binding uses the decoded source slots rather than dropping cooked assignments.
        import material_stage
        c=bpy.data.collections.new('Cooked binding check'); bpy.context.scene.collection.children.link(c)
        check=bpy.data.objects.new('Cooked binding check',a); c.objects.link(check)
        result=material_stage.bind_scene_materials(c,resolver.project)
        assert result['bound_meshes']==1 and not result['errors']
        assert a.materials[0]['UE_material_package']=='/Game/M_Worm' and a.materials[0]['UE_material_status']=='missing_dependencies'
        bpy.data.objects.remove(check,do_unlink=True); bpy.data.collections.remove(c); bpy.data.meshes.remove(a)
        assert resolver('/Game/Assets/D_broken')[1]=='failed'
        assert resolver('/Game/Assets/D_broken')[1]=='failed' and resolver.decode_attempts==2
        try: pg.import_geometry_folder(str(descriptor),'..')
        except ValueError: pass
        else: raise AssertionError('Folder traversal accepted')
        out=os.environ['UE_GALLERY_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
        collection=next(c for c in bpy.data.collections if c.name.startswith('UE native geometry gallery'))
        assert len(collection.objects)==4 and json.loads(bpy.data.texts[collection['UE_report']].as_string())==report
        print('PROJECT_GEOMETRY_PASS')
    finally: browser.unregister()
