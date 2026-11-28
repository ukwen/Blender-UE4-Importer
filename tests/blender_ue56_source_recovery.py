"""Original packages deliberately withheld in disposable project; registered recovery UI and nested overlay."""
import json,os,sys,shutil,tempfile
from pathlib import Path
import bpy
from mathutils import Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from project_session import hash_file
from saved_project_levels import activate
src=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT'])
with tempfile.TemporaryDirectory() as t:
    work=Path(t);root=work/'ShooterSam';shutil.copytree(src.parent,root);project=root/src.name;content=root/'Content';folder=work/'Recovery';folder.mkdir()
    paths=['LevelPrototyping/Meshes/SM_Cube.uasset','LevelPrototyping/Interactable/Door/Assets/Meshes/SM_DoorFrame_Edge.uasset'];keys=['/Game/'+Path(x).with_suffix('').as_posix() for x in paths]
    for i,n in enumerate(paths):shutil.move(content/n,folder/f'original_{i}.uasset')
    p=content/'Variant_Combat/Lvl_Combat.umap';q=content/'ThirdPerson/Lvl_ThirdPerson.umap'
    bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();s=bpy.context.scene.ueimport_project;s.project_path=str(project);s.recovery_folder=str(folder);s.partial_materials=True;s.static_materials=True
    assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
    for m in s.maps:m.enabled=Path(m.filepath) in (p,q)
    assert bpy.ops.ueimport.level_set()=={'FINISHED'};scene=bpy.context.scene;group=next(c for c in scene.collection.children if c.get('UE_project_level_set'));roots={c['UE_full_scene_source']:c for c in group.children};activate(scene,str(p));s.active=next(i for i,m in enumerate(s.maps) if m.filepath==str(p))
    geo=next(c for c in roots[str(p)].children if c.get('UE_source_map_path')==str(p));anchors=[o for o in geo.objects if o.get('UE_mesh_package') in keys and o.get('UE_geometry_status')=='missing'];assert len(anchors)==36,len(anchors)
    historical=bpy.data.texts[geo['UE_report']].as_string();members={o.name for o in geo.objects}
    assert bpy.ops.ueimport.locate_sources()=={'FINISHED'};reviewed=json.loads(bpy.data.texts[s.source_recovery_plan].as_string());assert reviewed['counts']['ready']==2,reviewed['counts'];assert not any((content/n).exists() for n in paths)
    assert bpy.ops.ueimport.restore_sources()=={'FINISHED'};restored=json.loads(bpy.data.texts[s.batch_report].as_string());assert len(restored['restored'])==2
    for n in paths:assert hash_file(content/n)==hash_file(src.parent/'Content'/n)
    assert bpy.ops.ueimport.select_recoverable_meshes()=={'FINISHED'};assert set(bpy.context.selected_objects)==set(anchors)
    anchors[0].location.x+=.123
    assert bpy.ops.ueimport.repair_missing_meshes()=={'FINISHED'};overlay=next(c for c in geo.children if c.get('UE_repair_source_map'));assert len(overlay.objects)==36;assert len({o.data.as_pointer() for o in overlay.objects})==2
    assert bpy.data.texts[geo['UE_report']].as_string()==historical and set(o.name for o in geo.objects)==members
    def verify():
        bpy.context.view_layer.update();err=0
        for o in overlay.objects:
            assert o.parent and o.matrix_basis==Matrix.Identity(4)
            err=max(err,max(abs(o.matrix_world[i][j]-o.parent.matrix_world[i][j]) for i in range(4) for j in range(4)))
        assert err<1e-6;return err
    error=verify();activate(scene,str(q));bpy.context.view_layer.update();assert all(not o.visible_get() for o in overlay.objects);activate(scene,str(p));bpy.context.view_layer.update();assert all(o.visible_get() for o in overlay.objects)
    for a in anchors:a.select_set(True)
    bpy.context.view_layer.objects.active=anchors[0]
    assert bpy.ops.ueimport.repair_missing_meshes()=={'FINISHED'};assert len([o for o in bpy.data.objects if o.get('UE_repair_child')])==36
    bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));scene=bpy.context.scene;overlay=next(c for c in bpy.data.collections if c.get('UE_repair_source_map'));assert len(overlay.objects)==36;assert verify()==error
    activate(scene,str(q));bpy.context.view_layer.update();assert all(not o.visible_get() for o in overlay.objects)
    report=dict(restored=restored,plan_counts=reviewed['counts'],recovered_meshes=36,unique_meshes=2,max_world_matrix_error=error,visibility_isolated=True,automatic_anchor_selection=True,reopen=True,original_report_unchanged=True,scope='Original packages withheld in disposable copy; no genuinely absent source acquired')
    out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('SOURCE_RECOVERY_PASS',report,flush=True)
