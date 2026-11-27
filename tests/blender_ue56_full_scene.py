"""Actual one-click scene operator, source coverage, linked camera and save/reopen."""
import os,sys,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from ue5_full_scene import reconstruct
from project_session import new_ids
project=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);content=project.parent/'Content'
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();scene=bpy.context.scene
sentinel=bpy.data.objects.new('User camera',bpy.data.cameras.new('User camera'));scene.collection.objects.link(sentinel);scene.camera=sentinel;sentinel.location=(3,4,5)
s=scene.ueimport_project;s.project_path=str(project);s.partial_materials=True
assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
expected={}
for rel in ('ThirdPerson/Lvl_ThirdPerson.umap','MyStuff/Maps/TestLevel.umap'):
    p=content/rel;s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p)
    assert bpy.ops.ueimport.full_scene()=={'FINISHED'};root=next(c for c in scene.collection.children if c.get('UE_full_scene_source')==str(p));report=json.loads(bpy.data.texts[root['UE_report']].as_string());expected[rel]=report['counts'];print('FULL',rel,report['counts'],report['material_status'],report['coverage']['representation_counts'],flush=True)
    assert report['inventory_errors']==[] and report['coverage']['serialized_level_exports']>0
    if rel.startswith('ThirdPerson'):
        assert report['stages']['geometry']['actor_status']=={'reconstructed':53,'missing':2},report['stages']['geometry']['actor_status'];assert report['counts']['lights']>=1;assert report['counts']['meshes']>=53;assert report['material_status'].get('supported_pbr_subset',0)+report['material_status'].get('partial',0)>0
    else:
        assert report['counts']['armatures']==1 and report['counts']['cameras']==1 and report['linked_character_cameras']==1,report['counts']
        camera=next(o for o in root.all_objects if o.type=='CAMERA');anchor=camera.parent.parent.parent.parent;assert anchor.get('UE_character_record');bpy.context.view_layer.update();before=camera.matrix_world.translation.copy();anchor.location.x+=2;bpy.context.view_layer.update();assert abs((camera.matrix_world.translation-before).x-2)<1e-5;anchor.location.x-=2
    ids=set(new_ids())
    try:reconstruct(str(p));raise AssertionError('duplicate accepted')
    except ValueError as e:assert 'already imported' in str(e)
    assert set(new_ids())==ids
    from ue5_editor_scene import reconstruct as geometry
    try:geometry(str(p));raise AssertionError('standalone duplicate accepted')
    except ValueError as e:assert 'already imported' in str(e)
    assert set(new_ids())==ids
    if rel.startswith('ThirdPerson'):
        single=out.with_name('thirdperson-transfer-074.blend');bpy.ops.wm.save_as_mainfile(filepath=str(single));bpy.ops.wm.open_mainfile(filepath=str(single));scene=bpy.context.scene;s=scene.ueimport_project;sentinel=scene.camera
        assert len([c for c in scene.collection.children if c.get('UE_full_scene_source')])==1
# Inject failure in a late stage on a different level; no newly created data survives.
import ue5_editor_camera as cam
original=cam.reconstruct
p=content/'MyStuff/Maps/MainLevel.umap'
def fail(*a,**k):raise RuntimeError('injected camera stage failure')
cam.reconstruct=fail
ids=set(new_ids())
try:
    try:reconstruct(str(p));raise AssertionError('failure not propagated')
    except RuntimeError as e:assert 'injected camera stage' in str(e)
    assert set(new_ids())==ids and scene.camera==sentinel
finally:cam.reconstruct=original

def verify():
    scene=bpy.context.scene;assert scene.camera.name=='User camera' and tuple(scene.camera.location)==(3,4,5)
    for rel,counts in expected.items():
        root=next(c for c in scene.collection.children if c.get('UE_full_scene_source')==str(content/rel));report=json.loads(bpy.data.texts[root['UE_report']].as_string());assert report['counts']==counts and len(root.all_objects)==counts['objects'];assert len(root.children)>=1
        if counts['cameras']:assert next(o for o in root.all_objects if o.type=='CAMERA').parent.parent.parent.parent.get('UE_character_record')
verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));verify();out.with_suffix('.json').write_text(json.dumps(dict(levels=expected,reopen=True,duplicate_refused=True,late_failure_rollback=True,active_camera_preserved=True),indent=2));print('FULL_SCENE_PASS',flush=True)
