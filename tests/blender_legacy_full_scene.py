"""Actual one-click commercial legacy level transfer, linked foliage and strict gate."""
import bpy,sys,os,json,math,hashlib
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
import legacy_full_scene as legacy
from project_session import new_ids
from static_scene import reconstruct_static_map
from foliage_legacy import read_component
from uasset import UAsset
root=Path(os.environ['UE_WESTERN_PROJECT']);out=Path(os.environ['UE_WESTERN_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();scene=bpy.context.scene
sentinel=bpy.data.objects.new('User camera',bpy.data.cameras.new('User camera'));scene.collection.objects.link(sentinel);scene.camera=sentinel
s=scene.ueimport_project;s.project_path=str(next(root.glob('*.uproject')));assert bpy.ops.ueimport.scan_project()=={'FINISHED'}
expected={};matrices={};maxerr=0.;reports={};bindings={};light_matrices={};light_error=0.
for p in sorted(root.rglob('*.umap')):
    s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p)
    # strict source gate: known missing engine packages in these originals
    ids=set(new_ids());
    try:legacy.reconstruct(str(p),strict_dependencies=True);raise AssertionError('strict gate accepted incomplete source')
    except ValueError as e:assert 'Source dependency check failed' in str(e),str(e)
    assert set(new_ids())==ids
    if p.stem=='Overview':
        # A late lighting-stage failure after geometry and material creation must roll back.
        original=legacy.add_lights
        def fail(*a,**k):raise RuntimeError('injected legacy lighting failure')
        legacy.add_lights=fail
        try:
            try:legacy.reconstruct(str(p));raise AssertionError('late failure swallowed')
            except RuntimeError as e:assert 'injected legacy' in str(e)
            assert set(new_ids())==ids and scene.camera==sentinel
        finally:legacy.add_lights=original
    assert bpy.ops.ueimport.full_scene()=={'FINISHED'}
    c=next(c for c in scene.collection.children if c.get('UE_full_scene_source')==str(p));r=json.loads(bpy.data.texts[c['UE_report']].as_string());reports[p.stem]=r
    assert r['status']=='bounded_legacy_scene_preview';g=r['stages']['geometry'];assert r['counts']['lights']==1 and r['counts']['cameras']==0;assert not r['stages']['lighting']['skipped']
    assert g['actor_status']==({'reconstructed':1994,'missing':1} if p.stem=='Demonstration' else {'reconstructed':322,'missing':1})
    assert r['foliage_instances']==(462 if p.stem=='Demonstration' else 0);assert r['counts']['armatures']==(6 if p.stem=='Demonstration' else 30)
    assert not g['material_report']['errors'] and all(v['status']=='graph_imported_unverified' for v in g['material_report']['packages'].values())
    assert all(o.material_slots and all(slot.material and not slot.material.get('UE_unresolved_material') for slot in o.material_slots) for o in c.objects if o.type=='MESH')
    bpy.context.view_layer.update()
    for o in c.objects:
        if o.type=='MESH':bindings[o.name]=[slot.material['UE_material_package'] for slot in o.material_slots]
    sun=next(o for o in c.objects if o.type=='LIGHT');record=next(r for r in r['stages']['lighting']['records'] if r['kind']=='DirectionalLight');loc=record['fields']['RelativeLocation'];pitch,yaw,roll=map(math.radians,record['fields']['RelativeRotation'])
    pos=Vector((loc[1]*.01,loc[0]*.01,loc[2]*.01));direction=Vector((math.sin(yaw)*math.cos(pitch),math.cos(yaw)*math.cos(pitch),math.sin(pitch)))
    light_error=max(light_error,(sun.matrix_world.translation-pos).length,(sun.matrix_world.to_3x3()@Vector((0,0,-1))-direction).length)
    assert light_error<1e-5 and abs(sun.data.energy-record['properties']['Intensity'])<1e-5
    light_matrices[sun.name]=[list(row) for row in sun.matrix_world]
    with UAsset(str(p)) as a:
        for e in a.exports:
            if e.export_class_type!='FoliageInstancedStaticMeshComponent':continue
            _,pkg,records=read_component(e);objs=sorted((o for o in c.objects if o.get('UE_foliage_component')==e.object_name),key=lambda o:o['UE_foliage_instance_index']);assert len(objs)==len(records) and len({o.data.as_pointer() for o in objs})==1
            for o,row in zip(objs,records):
                assert o.get('UE_actor') and o.get('UE_source_actor_package') and o['UE_mesh_package']==pkg
                for v in ((0,0,0),(1,0,0),(0,1,0),(0,0,1)):
                    x,y,z=v[1]*100,v[0]*100,v[2]*100;q=[(x*row[j]+y*row[4+j]+z*row[8+j]+row[12+j])*.01 for j in range(3)]
                    maxerr=max(maxerr,(o.matrix_basis@Vector(v)-Vector((q[1],q[0],q[2]))).length)
                matrices[o.name]=[list(row) for row in o.matrix_world]
    expected[p.stem]=r['counts'];ids=set(new_ids())
    for fn in (legacy.reconstruct,reconstruct_static_map):
        try:fn(str(p));raise AssertionError('duplicate accepted')
        except ValueError as e:assert 'already imported' in str(e)
        assert set(new_ids())==ids
    if p.stem=='Overview':c.hide_render=True;c.hide_viewport=True
    print('LEGACY_LEVEL_PASS',p.stem,r['counts'],r['foliage_instances'],r['material_status'],flush=True)
assert len(matrices)==462 and maxerr<.00005
assert scene.camera==sentinel
images={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file};assert len(images)==5
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));assert bpy.context.scene.camera.name=='User camera'
# Hidden collections are excluded from depsgraph evaluation after reopening.
hidden=[c for c in bpy.context.scene.collection.children if c.get('UE_full_scene_source') and c.hide_viewport]
for c in hidden:c.hide_viewport=False
bpy.context.view_layer.update()
assert images=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
for name,materials in bindings.items():assert materials==[slot.material['UE_material_package'] for slot in bpy.data.objects[name].material_slots]
for name,m in light_matrices.items():assert max(abs(bpy.data.objects[name].matrix_world[i][j]-m[i][j]) for i in range(4) for j in range(4))<1e-5
for name,m in matrices.items():assert max(abs(bpy.data.objects[name].matrix_world[i][j]-m[i][j]) for i in range(4) for j in range(4))<.00005
for stem,counts in expected.items():
    c=next(c for c in bpy.context.scene.collection.children if c.get('UE_full_scene_source','').endswith('/'+stem+'.umap'));assert len(c.all_objects)==counts['objects'];assert json.loads(bpy.data.texts[c['UE_report']].as_string())['counts']==counts
for c in hidden:c.hide_viewport=True
out.with_suffix('.json').write_text(json.dumps(dict(levels=expected,foliage_instances=len(matrices),max_foliage_local_error_m=maxerr,reopen=True,duplicates_refused=True,strict_gate=True,late_failure_rollback=True,active_camera_preserved=True,material_bound_mesh_objects=len(bindings),packed_images=len(images),max_light_position_or_direction_error=light_error,material_status={k:v['material_status'] for k,v in reports.items()},unrepresented_classes={k:v['coverage']['unrepresented_classes'] for k,v in reports.items()},dependency_gaps={k:v['source_dependencies']['unresolved_hard'] for k,v in reports.items()}),indent=2))
print('LEGACY_FULL_SCENE_PASS',maxerr,flush=True)
