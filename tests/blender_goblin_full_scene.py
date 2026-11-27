"""Actual one-click version 522 Overview; partial mixed-version fixture, no guessed meshes."""
import bpy,os,sys,json,hashlib
from pathlib import Path
from collections import Counter
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from uasset import UAsset
import legacy_full_scene as legacy
import uproject_browser as browser
from project_session import new_ids
from static_scene import reconstruct_static_map
project=Path(os.environ['UE_GOBLIN_PROJECT']);p=project.parent/'Content/FixtureMaps/Overview.umap';out=Path(os.environ['UE_GOBLIN_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();scene=bpy.context.scene
sentinel=bpy.data.objects.new('User camera',bpy.data.cameras.new('User camera'));scene.collection.objects.link(sentinel);scene.camera=sentinel
s=scene.ueimport_project;s.project_path=str(project);s.partial_materials=True
assert bpy.ops.ueimport.scan_project()=={'FINISHED'};s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p)
before=set(new_ids())
try:legacy.reconstruct(str(p),strict_dependencies=True);raise AssertionError('strict gate accepted incomplete fixture')
except ValueError as e:assert 'Source dependency check failed' in str(e)
assert set(new_ids())==before
# Late rollback with real geometry and textures allocated.
old=legacy.add_lights
def fail(*a,**k):raise RuntimeError('injected lighting failure')
legacy.add_lights=fail
try:
    try:legacy.reconstruct(str(p),partial=True);raise AssertionError('late failure swallowed')
    except RuntimeError as e:assert 'injected lighting failure' in str(e)
    assert set(new_ids())==before and scene.camera==sentinel
finally:legacy.add_lights=old
assert bpy.ops.ueimport.full_scene()=={'FINISHED'}
c=next(c for c in scene.collection.children if c.get('UE_full_scene_source')==str(p));r=json.loads(bpy.data.texts[c['UE_report']].as_string());g=r['stages']['geometry'];comp=g['component_report']
assert r['package_profile']==522 and r['counts']['meshes']==36 and r['counts']['armatures']==30 and r['counts']['lights']==1
assert g['actor_status']=={'missing':559,'reconstructed':3} and not g['unresolved_parents']
assert r['coverage']['serialized_level_exports']==602 and r['coverage']['representation_counts']['unresolved_geometry']==559
assert not g['material_report']['errors'] and g['material_report']['bound_meshes']==35
assert all(o.material_slots and all(slot.material for slot in o.material_slots) for o in c.all_objects if o.type=='MESH')
assert r['material_status']=={'partial_graph_unresolved':1,'missing_dependencies':2}
bodies=[x for x in comp['records'] if x['reference_origin']=='CDO'];accessories=[x for x in comp['records'] if x['reference_origin']=='SCS']
assert len(bodies)==15 and all(x['status']=='reconstructed' and x['sockets']['created']==20 for x in bodies)
assert Counter(x['status'] for x in accessories)=={'reconstructed':3,'missing':34}
assert sum(bool(o.get('UE_master_pose_component')) for o in c.all_objects)==2
assert sum(bool(o.get('UE_socket_name')) for o in c.all_objects)==300
# Compare all 592 direct saved mesh/character relative locations against the original map, not the imported report.
roots={};maxerror=0.
for o in c.all_objects:
    if o.get('UE_actor') and (o.get('UE_component_anchor') or o.get('UE_geometry_status')):
        roots[(o['UE_actor'],o.get('UE_component') if o.get('UE_component_anchor') else None)]=o
bpy.context.view_layer.update();validated=0
with UAsset(str(p)) as a:
    for e in a.exports:
        if e.export_class_type not in ('StaticMeshActor','SkeletalMeshActor') and not (e.export_class_type or '').startswith('BP_Chr_'):continue
        if not 0<e.outer_index<=len(a.exports) or a.GetExport(e.outer_index).export_class_type!='Level':continue
        e.ReadProperties(False);root=e.properties.TryGetValue('RootComponent');root.ReadProperties(False)
        v=root.properties.TryGetValue('RelativeLocation');expected=Vector((v.y*.01,v.x*.01,v.z*.01)) if v else Vector((0,0,0))
        obj=roots[(e.object_name,None if e.export_class_type=='StaticMeshActor' else root.object_name)];maxerror=max(maxerror,(obj.matrix_basis.translation-expected).length);validated+=1
assert validated==592 and maxerror<.0001,(validated,maxerror)
matrices={o.name:[list(row) for row in o.matrix_world] for o in c.all_objects}
slots={o.name:[s.material.name if s.material else None for s in o.material_slots] for o in c.all_objects if o.type=='MESH'}
images={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file};assert len(images)>=3
ids=set(new_ids())
for fn in (legacy.reconstruct,reconstruct_static_map):
    try:fn(str(p));raise AssertionError('duplicate accepted')
    except ValueError as e:assert 'already imported' in str(e)
    assert set(new_ids())==ids
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));bpy.context.view_layer.update();assert bpy.context.scene.camera.name=='User camera'
assert images=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
for name,m in matrices.items():assert max(abs(bpy.data.objects[name].matrix_world[i][j]-m[i][j]) for i in range(4) for j in range(4))<.0001,name
for name,materials in slots.items():assert materials==[s.material.name if s.material else None for s in bpy.data.objects[name].material_slots]
c=next(c for c in bpy.context.scene.collection.children if c.get('UE_full_scene_source')==str(p));assert json.loads(bpy.data.texts[c['UE_report']].as_string())==r
out.with_suffix('.json').write_text(json.dumps(dict(scope='Partial mixed-version fixture; original UE4.26 map, test-only descriptor',counts=r['counts'],static_status=g['actor_status'],component_status=comp['status'],coverage=r['coverage']['representation_counts'],source_relative_locations_validated=validated,max_relative_position_error_m=maxerror,character_bodies=len(bodies),sockets=300,accessories=dict(Counter(x['status'] for x in accessories)),packed_images=len(images),material_status=r['material_status'],dependency_gaps=r['source_dependencies']['unresolved_hard'],strict_gate=True,late_rollback=True,duplicates_refused=True,reopen=True,active_camera_preserved=True),indent=2));print('GOBLIN_FULL_SCENE_PASS',r['counts'],maxerror,len(images),flush=True)
