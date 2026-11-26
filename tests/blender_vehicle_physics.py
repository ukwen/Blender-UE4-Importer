"""Real assets acceptance, including exact package association and missing dependency behavior."""
import bpy,sys,os,pathlib,json,shutil,math
from mathutils import Matrix,Vector
from collections import Counter
root=pathlib.Path(__file__).resolve().parents[1];sys.path.insert(0,str(root))
from physics_native import read_physics,mesh_physics_reference,associate_physics,joint_local,build_physics,build_convex_mesh
from native_sockets import socket_local
from project_geometry import import_geometry_folder
raw=pathlib.Path(os.environ['UE_VEHICLE_MESHES']);phys=pathlib.Path(os.environ['UE_VEHICLE_PHYSICS']);project=pathlib.Path(os.environ['UE_VEHICLE_PROJECT']);content=project/'Content';project.mkdir(parents=True,exist_ok=True);desc=project/'VehicleTest.uproject';desc.write_text('{"EngineAssociation":"4.27"}')
bpy.ops.wm.read_factory_settings(use_empty=True)
records={};source_points=0
for path in sorted(phys.glob('PHYS_Veh*.uasset')):
    d=read_physics(path);source=raw/(d['preview_mesh'].rsplit('/',1)[-1]+'.uasset');ref=mesh_physics_reference(source);assert ref.rsplit('/',1)[-1]==d['name'];target=content/(d['preview_mesh'][6:]+'.uasset');target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,target);pp=content/(ref[6:]+'.uasset');pp.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(path,pp);records[str(target.resolve())]=(d,pp)
assert len(records)==13
coll,report=import_geometry_folder(str(desc),include_physics=True)
assert report['counts'].get('reconstructed')==13 and report['physics_counts']=={'reconstructed':13},report
results=[]
for arm in [o for o in coll.objects if o.type=='ARMATURE']:
    d,pp=records[arm['UE_source_mesh_path']];children=[o for o in arm.children if o.get('UE_physics_asset')];expected=[]
    for b in d['bodies']:
        for s in b['shapes']:
            local=socket_local(dict(location_cm=s['center_cm'],rotation_pyr=s['rotation_pyr'],scale=(1,1,1))) if s['kind']=='capsule' else Matrix.Identity(4)
            expected.append((s['kind'],b['bone'],s,local))
    for j in d['joints']:
        for b,f in zip(j['bones'],j['frames']):expected.append(('joint',b,j,joint_local(f)))
    assert len(children)==len(expected);counts=Counter();max_bounds=0.;max_plane=0.;pairs=[]
    for o in children:
        rec=json.loads(o['UE_physics_record']);kind=o['UE_physics_kind'];bone=o['UE_physics_bone'];idx=next(i for i,(k,b,s,l) in enumerate(expected) if k==kind and b==bone and json.loads(json.dumps(s))==rec);k,b,s,local=expected.pop(idx);pairs.append((o,b,local));counts[kind]+=1;assert o.hide_render
        if kind=='convex':
            pts=[Vector((y*.01,x*.01,z*.01)) for x,y,z in s['vertices_cm']];source_points+=len(pts)
            assert all(min((v.co-p).length for p in pts)<1e-6 for v in o.data.vertices)
            for axis in range(3):
                for fn in (min,max):max_bounds=max(max_bounds,abs(fn(v.co[axis] for v in o.data.vertices)-fn(p[axis] for p in pts)))
            # All source support points must lie within the reconstructed hull.
            for face in o.data.polygons:
                max_plane=max(max_plane,max(face.normal.dot(p-face.center) for p in pts))
                assert max_plane<1e-4,(d['name'],o.name,max_plane)
        elif kind=='capsule':
            assert abs(max(v.co.z for v in o.data.vertices)-min(v.co.z for v in o.data.vertices)-(s['length_cm']+2*s['radius_cm'])*.01)<1e-6
    assert not expected and max_bounds<1e-6
    def verify():
        bpy.context.view_layer.update();err=0
        for o,bone,local in pairs:
            b=arm.data.bones[bone];m=b['UE_world_matrix_m'];rest=Matrix([m[k:k+4] for k in range(0,16,4)]);want=arm.matrix_world@arm.pose.bones[bone].matrix@b.matrix_local.inverted()@rest@local;err=max(err,max(abs(o.matrix_world[a][z]-want[a][z]) for a in range(4) for z in range(4)))
        return err
    rest=verify();before=[o.matrix_world.copy() for o,_,_ in pairs]
    for b in arm.pose.bones:
        if b.parent:b.rotation_mode='XYZ';b.rotation_euler.x=.12
    posed=verify();motion=max((o.matrix_world.translation-m.translation).length for (o,_,_),m in zip(pairs,before));rotation_change=max(max(abs(o.matrix_world[a][z]-m[a][z]) for a in range(3) for z in range(3)) for (o,_,_),m in zip(pairs,before));assert motion>1e-5 or rotation_change>1e-5,(d['name'],motion,rotation_change)
    for b in arm.pose.bones:b.matrix_basis=Matrix.Identity(4)
    neutral=verify();assert max(rest,posed,neutral)<1e-4
    try:associate_physics(arm,arm['UE_source_mesh_path'],content);raise AssertionError('duplicate accepted')
    except ValueError:pass
    results.append(dict(mesh=d['preview_mesh'],counts=dict(counts),bounds_error_m=max_bounds,hull_plane_error_m=max_plane,rest_error=rest,posed_error=posed,neutral_error=neutral,motion_m=motion,rotation_matrix_change=rotation_change));print('VEHICLE_PHYSICS_PASS',d['name'],dict(counts),flush=True)
# Missing dependency is explicitly reported, preserving gallery geometry.
arm=next(o for o in coll.objects if o.type=='ARMATURE');d,pp=records[arm['UE_source_mesh_path']];hold=pp.with_suffix('.hidden');pp.rename(hold)
try: assert associate_physics(arm,arm['UE_source_mesh_path'],content)['status']=='missing'
finally:hold.rename(pp)
# Degenerate hull refusal.
m=bpy.data.meshes.new('invalid test');
try:
    try:build_convex_mesh(m,[(0,0,0),(1,0,0),(2,0,0),(3,0,0)]);raise AssertionError('degenerate accepted')
    except ValueError:pass
finally:bpy.data.meshes.remove(m)
summary=dict(vehicles=results,source_convex_points=source_points,counts=dict(sum((Counter(r['counts']) for r in results),Counter())),association=report['physics_counts'],simulation='not implemented')
assert summary['counts']['convex']==69
bpy.data.texts.new('UE vehicle physics acceptance.json').write(json.dumps(summary,indent=2));out=os.environ['UE_VEHICLE_OUTPUT'];bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out);assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==13;assert Counter(o['UE_physics_kind'] for o in bpy.data.objects if 'UE_physics_kind' in o)==summary['counts'];pathlib.Path(os.environ['UE_VEHICLE_REPORT']).write_text(json.dumps(summary,indent=2));print('VEHICLE_REOPEN_PASS',summary['counts'],flush=True)

# Fresh scene: gallery must keep geometry even when physics is absent.
bpy.ops.wm.read_factory_settings(use_empty=True);missing_project=project/'missing_case';missing_project.mkdir(exist_ok=True);missing_desc=missing_project/'Missing.uproject';missing_desc.write_text('{"EngineAssociation":"4.27"}');first=pathlib.Path(next(iter(records)));target=missing_project/'Content'/first.relative_to(content);target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(first,target);missing_coll,missing_report=import_geometry_folder(str(missing_desc),include_physics=True);assert missing_report['counts']=={'reconstructed':1} and missing_report['physics_counts']=={'missing':1};assert len([o for o in missing_coll.objects if o.type=='ARMATURE'])==1;print('MISSING_DEPENDENCY_GALLERY_PASS',flush=True)
