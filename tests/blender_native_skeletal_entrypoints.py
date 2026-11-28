"""Three real editor skeletal profiles through registered direct file-menu import."""
import importlib.abc,json,os,sys
from pathlib import Path
from unittest.mock import patch
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError('Inherited importer prohibited: '+fullname)
assert CORE.isdisjoint(sys.modules);sys.meta_path.insert(0,Block())
from asset_entrypoints import register,unregister,import_mesh
from project_session import new_ids
root=Path(os.environ['UE_WESTERN_PROJECT']);goblin=Path(os.environ['UE_GOBLIN_PROJECT']).parent;modern=Path(os.environ['UE56_EDITOR_PROJECT']).parent
paths=[next(root.rglob('SK_Prop_Cart_01.uasset')),next(goblin.rglob('SK_Chr_Warrior_Male_01.uasset')),next(modern.rglob('SKM_Quinn_Simple.uasset'))]
bpy.ops.wm.read_factory_settings(use_empty=True);register();records=[]
for p in paths:
    before=set(bpy.data.objects)
    assert getattr(bpy.ops,'import').umesh(filepath=str(p),materials=True)=={'FINISHED'}
    added=set(bpy.data.objects)-before;obj,=[o for o in added if o.type=='MESH'];arm,=[o for o in added if o.type=='ARMATURE'];assert len(added)==2
    assert obj.parent==arm and obj.modifiers[0].object==arm
    mesh=obj.data;bindings=json.loads(mesh['UE_material_bindings']);assert len(bindings)==len(mesh.materials)>0
    assert all(m['UE_material_package']==pkg for m,(_,pkg) in zip(mesh.materials,bindings))
    assert max(abs(sum(g.weight for g in v.groups)-1) for v in mesh.vertices)<1e-5
    points=np.array([v.co[:] for v in mesh.vertices]);weights=np.zeros((len(points),len(obj.vertex_groups)))
    for v in mesh.vertices:
        for g in v.groups:weights[v.index,g.group]=g.weight
    j=1+int(np.argmax(np.sum(weights[:,1:]>0,axis=0)));bone=arm.pose.bones[obj.vertex_groups[j].name];bone.rotation_mode='XYZ';bone.rotation_euler.x=.25
    bpy.context.view_layer.update();evaluated=np.array([v.co[:] for v in obj.evaluated_get(bpy.context.evaluated_depsgraph_get()).data.vertices]);matrices=[np.array(arm.pose.bones[g.name].matrix@arm.data.bones[g.name].matrix_local.inverted()) for g in obj.vertex_groups]
    expected=sum((points@m[:3,:3].T+m[:3,3])*weights[:,k,None] for k,m in enumerate(matrices));error=float(np.max(np.linalg.norm(evaluated-expected,axis=1)));motion=float(np.max(np.linalg.norm(evaluated-points,axis=1)));assert error<1e-4 and motion>1e-5,(p.name,error,motion)
    records.append(dict(asset=p.name,object=obj.name,armature=arm.name,vertices=len(points),triangles=len(mesh.polygons),bones=len(arm.data.bones),error_m=error,motion_m=motion,bindings=bindings,material_statuses=[m['UE_material_status'] for m in mesh.materials]))
    print('SKELETAL_ENTRYPOINT',records[-1],flush=True)
before=set(new_ids())
with patch('material_stage.bind_native_mesh_slots',side_effect=ValueError('Injected binding failure')):
    try:import_mesh(paths[0],True,False)
    except ValueError as e:assert str(e)=='Injected binding failure'
    else:raise AssertionError('Failure accepted')
assert set(new_ids())==before
try:import_mesh(paths[0],False,True)
except NotImplementedError:pass
else:raise AssertionError('Unsupported skeletal LOD selection accepted')
assert set(new_ids())==before
out=Path(os.environ['UE_SKELETAL_ENTRYPOINT_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for row in records:
    obj=bpy.data.objects[row['object']];arm=bpy.data.objects[row['armature']];assert obj.parent==arm and obj.modifiers[0].object==arm and len(arm.data.bones)==row['bones'];assert len(obj.data.vertices)==row['vertices'];assert json.loads(obj.data['UE_material_bindings'])==row['bindings']
assert not attempts and CORE.isdisjoint(sys.modules),(attempts,CORE.intersection(sys.modules))
unregister();out.with_suffix('.json').write_text(json.dumps(dict(assets=records,reopen=True,rollback=True,zero_inherited_imports=True),indent=2));print('NATIVE_SKELETAL_ENTRYPOINTS_PASS',flush=True)
