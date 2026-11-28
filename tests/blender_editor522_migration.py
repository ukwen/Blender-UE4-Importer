"""Original skeletal data, pose and physics acceptance without inherited parser."""
import hashlib,json,os,sys
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from editor_skeletal import read_editor_mesh
from editor_skeleton import read_editor_skeleton
from skeletal_mesh_native import build_mesh
from skeleton_native import build_armature
from physics_native import read_physics,mesh_physics_reference,build_physics
root=Path(os.environ['UE_EDITOR522_FIXTURES']);out=Path(os.environ['UE_EDITOR522_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True)
class DenyLegacy:
    def find_spec(self,fullname,path=None,target=None):
        if fullname=='uasset':raise ImportError('Inherited parser forbidden in migration acceptance')
        return None
assert 'uasset' not in sys.modules
sys.meta_path.insert(0,DenyLegacy())
def digest(data):return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
results=[];cursor=0
for path in sorted(root.glob('SK_*.uasset')):
    data=read_editor_mesh(path);mesh,arm=build_mesh(data);arm['UE_source_mesh_path']=str(path);arm.location.x=cursor;cursor+=4
    pts=np.array([v.co[:] for v in mesh.data.vertices]);source=np.array(data['positions'])[:,[1,0,2]]*.01
    assert np.max(abs(pts-source))<1e-5
    weights=np.zeros((len(pts),len(data['bones'])))
    for i,w in enumerate(data['weights']):
        for j,v in w.items():weights[i,j]=v/255
    def evaluated():
        bpy.context.view_layer.update();return np.array([v.co[:] for v in mesh.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices])
    assert np.max(abs(evaluated()-pts))<1e-5
    j=1+int(np.argmax(np.sum(weights[:,1:]>0,axis=0)));bone=arm.pose.bones[data['bones'][j]['name']]
    phys_path=root/(mesh_physics_reference(path).rsplit('/',1)[-1]+'.uasset');overlays=[];ph=None
    if phys_path.is_file():
        ph=read_physics(phys_path);overlays=build_physics(arm,ph,path)
        assert len(overlays)==sum(len(b['shapes']) for b in ph['bodies'])+2*len(ph['joints'])
    bone.rotation_mode='XYZ';bone.rotation_euler.x=.25;moved=evaluated()
    matrices=[np.array(arm.pose.bones[b['name']].matrix@arm.data.bones[b['name']].matrix_local.inverted()) for b in data['bones']]
    want=sum((pts@m[:3,:3].T+m[:3,3])*weights[:,k,None] for k,m in enumerate(matrices))
    error=float(np.max(np.linalg.norm(moved-want,axis=1)));motion=float(np.max(np.linalg.norm(moved-pts,axis=1)))
    assert error<1e-4 and motion>1e-5,(path.name,error,motion)
    assert all(o.parent==arm and o.parent_type=='BONE' and o.hide_render for o in overlays)
    bone.rotation_euler.x=0;assert np.max(abs(evaluated()-pts))<1e-5
    results.append(dict(asset=path.name,vertices=len(pts),triangles=len(mesh.data.polygons),bones=len(data['bones']),motion_m=motion,error_m=error,overlays=len(overlays),decoded_sha256=digest(data),physics_sha256=digest(ph) if ph else None))
    print('MIGRATED_MESH',results[-1],flush=True)
skeleton=read_editor_skeleton(root/'UE4_Mannequin_Skeleton.uasset');arm=build_armature(skeleton['name'],skeleton['bones']);assert len(arm.data.bones)==72 and len(skeleton['sockets'])==20
assert len(results)==5 and 'uasset' not in sys.modules
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
assert sum(o.type=='ARMATURE' for o in bpy.data.objects)==6
assert sum(o.get('UE_physics_kind') is not None for o in bpy.data.objects)==sum(x['overlays'] for x in results)
assert sum(o.type=='MESH' and any(m.type=='ARMATURE' for m in o.modifiers) for o in bpy.data.objects)==5
out.with_suffix('.json').write_text(json.dumps(dict(meshes=results,skeleton_bones=72,skeleton_sockets=20,skeleton_sha256=digest(skeleton),reopen=True,legacy_import_blocked=True),indent=2))
print('EDITOR522_MIGRATION_PASS',flush=True)
