"""Original saved sky records, explicit activation, rollback and save/reopen in Blender."""
import os,sys,json,math
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_lighting import records
from ue5_environment_preview import build,activate
from project_session import new_ids,rollback_new
import uproject_browser as browser
from ue5_full_scene import reconstruct
project=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);c=project.parent/'Content'
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();scene=bpy.context.scene
user=bpy.data.worlds.new('User world');scene.world=user
s=scene.ueimport_project;s.project_path=str(project);s.partial_materials=True;assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
reports={};max_error=0
for p in c.rglob('*.umap'):
    try:d=records(c,p)
    except ValueError:continue
    if p.name=='Lvl_ThirdPerson.umap':
        s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p);assert bpy.ops.ueimport.full_scene()=={'FINISHED'}
        root=next(x for x in scene.collection.children if x.get('UE_full_scene_source')==str(p));report=json.loads(bpy.data.texts[root['UE_report']].as_string())['stages']['environment']
        sun=next(o for o in root.all_objects if o.type=='LIGHT' and o.data.type=='SUN');bpy.context.view_layer.update();max_error=(sun.matrix_world.to_quaternion()@Vector((0,0,1))-Vector(report['sun_direction'])).length;assert max_error<1e-6
    else:
        root=bpy.data.collections.new(p.stem);scene.collection.children.link(root);root['UE_full_scene_source']=str(p);report=build(root,d['records'])
    assert scene.world==user
    if report['status']=='sky_preview_ready':
        world=root['UE_environment_world'];node=next(n for n in world.node_tree.nodes if n.type=='TEX_SKY');assert not node.sun_disc;assert abs(node.sun_elevation-report['sun_elevation'])<1e-6;assert abs(node.sun_rotation-report['sun_rotation'])<1e-6
    else:assert root.get('UE_environment_world') is None
    reports[str(p)]=report
assert sum(r['status']=='sky_preview_ready' for r in reports.values())==5
p=c/'ThirdPerson/Lvl_ThirdPerson.umap';s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p);assert bpy.ops.ueimport.apply_sky_preview()=={'FINISHED'};assert scene.world.name==reports[str(p)]['world'];scene.world=user
# Verify a rollback removes the newly created world and root without changing the existing scene world.
ids=set(new_ids());root=bpy.data.collections.new('rollback');scene.collection.children.link(root);build(root,records(c,p)['records']);rollback_new(ids);assert set(new_ids())==ids and scene.world==user
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));scene=bpy.context.scene;assert scene.world.name=='User world'
for path,r in reports.items():
    if r['status']=='sky_preview_ready':
        world=activate(scene,path);assert world.name==r['world'];node=next(n for n in world.node_tree.nodes if n.type=='TEX_SKY');assert abs(node.sun_rotation-r['sun_rotation'])<1e-6
scene.world=bpy.data.worlds['User world'];out.with_suffix('.json').write_text(json.dumps(dict(reports=reports,worlds=5,max_sun_direction_error=max_error,explicit_activation=True,rollback=True,reopen=True,original_world_preserved=True),indent=2));print('ENVIRONMENT_PREVIEW_PASS',flush=True)
