"""Genuine cooked UE4.18 render mesh versus original GLB and actual deformation."""
import json,os,struct,sys,tempfile
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from skeletal_mesh_native import read_mesh
import skeleton_blender as sb
root=Path(os.environ['MATYA_ASSETS']); path=root/'4.18/SK_Worm.uasset'
d=read_mesh(path); assert len(d['positions'])==640 and len(d['faces'])==572 and len(d['bones'])==6
raw=(root/'raw/SK_Worm.glb').read_bytes(); n=struct.unpack_from('<I',raw,12)[0]; gltf=json.loads(raw[20:20+n]); binary=raw[28+n:]
def acc(i):
    a=gltf['accessors'][i]; v=gltf['bufferViews'][a['bufferView']]; width={'VEC3':3,'VEC2':2,'VEC4':4,'SCALAR':1}[a['type']]
    return np.frombuffer(binary,dtype={5126:'<f4',5121:'u1',5123:'<u2'}[a['componentType']],count=a['count']*width,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(a['count'],width)
p,j,w,uv=acc(0),acc(3),acc(4),acc(2); joints=[gltf['nodes'][i]['name'] for i in gltf['skins'][0]['joints']]; names=[b['name'] for b in d['bones']]
reference=np.zeros((len(p),len(names)))
for i in range(len(p)):
    for bone,weight in zip(j[i],w[i]): reference[i,names.index(joints[bone])]+=weight
pos_err=weight_err=uv_err=0.
for i,(x,y,z) in enumerate(d['positions']):
    distances=np.linalg.norm(p-np.array([x,z,y])*.01,axis=1); pos_err=max(pos_err,float(distances.min())); match=np.flatnonzero(distances<1e-6); assert len(match)
    actual=np.array([d['weights'][i].get(k,0)/255 for k in range(len(names))]); weight_err=max(weight_err,float(np.abs(reference[match]-actual).max(axis=1).min())); uv_err=max(uv_err,float(np.abs(uv[match]-d['uvs'][i]).max(axis=1).min()))
assert pos_err<1e-6 and weight_err<=1/255+1e-6 and uv_err<.001
print('GLB_REFERENCE',pos_err,weight_err,uv_err)
bpy.ops.wm.read_factory_settings(use_empty=True); sb.register()
try: assert getattr(bpy.ops,'import').ue_native_skeletal_mesh(filepath=str(path))=={'FINISHED'}
finally: sb.unregister()
obj=next(o for o in bpy.data.objects if o.type=='MESH'); arm=obj.parent
assert len(obj.data.vertices)==640 and len(obj.data.polygons)==572 and obj.data.has_custom_normals and len(obj.data.uv_layers)==1 and len(arm.data.bones)==6
for i,v in enumerate(obj.data.vertices):
    assert set(g.group for g in v.groups)==set(d['weights'][i]); assert max(abs(g.weight-d['weights'][i][g.group]/255) for g in v.groups)<1e-7
# Actual linear blend skinning: compare evaluated Blender mesh to independent
# weighted pose/rest transforms. Rest should be unchanged.
def evaluated():
    bpy.context.view_layer.update(); ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); return [v.co.copy() for v in ev.data.vertices]
neutral=[v.co.copy() for v in obj.data.vertices]; rest=evaluated(); assert max((a-b).length for a,b in zip(neutral,rest))<1e-5
bone=arm.pose.bones['bone_c']; bone.rotation_mode='XYZ'; bone.rotation_euler.x=.45; moved=evaluated(); matrices=[arm.pose.bones[name].matrix@arm.data.bones[name].matrix_local.inverted() for name in names]
expected=[sum((matrices[j]@p*(w/255.) for j,w in weights.items()),Vector((0,0,0))) for p,weights in zip(neutral,d['weights'])]
err=max((a-b).length for a,b in zip(moved,expected)); motion=max((a-b).length for a,b in zip(moved,neutral)); assert err<1e-5 and motion>.1
print('SKIN_POSE',err,motion,sum((a-b).length>1e-5 for a,b in zip(moved,neutral)))
bone.rotation_euler.x=0; assert max((a-b).length for a,b in zip(evaluated(),neutral))<1e-5
# Keep source package intact; truncated and wrong profile must fail before creation.
for bad in (root/'4.27/SK_Worm.uasset',root/'4.18/SK_Worm_Skeleton.uasset'):
    try: read_mesh(bad)
    except ValueError: pass
    else: raise AssertionError('Unsupported package accepted')
with tempfile.TemporaryDirectory() as tmp:
    bad=Path(tmp)/'truncated.uasset'; bad.write_bytes(path.read_bytes()); bad.with_suffix('.uexp').write_bytes(path.with_suffix('.uexp').read_bytes()[:-10])
    try: read_mesh(bad)
    except ValueError: pass
    else: raise AssertionError('Truncated package accepted')
# Store a short editable pose action as acceptance evidence, not source animation.
bone.keyframe_insert(data_path='rotation_euler',frame=1); bone.rotation_euler.x=.45; bone.keyframe_insert(data_path='rotation_euler',frame=20); bone.rotation_euler.x=0; bone.keyframe_insert(data_path='rotation_euler',frame=40); arm.animation_data.action.name='Native skin acceptance - authored test pose'; bpy.context.scene.frame_set(1)
out=os.environ['UE_SKIN_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
obj=next(o for o in bpy.data.objects if o.type=='MESH'); arm=obj.parent; assert len(obj.vertex_groups)==6 and arm.animation_data.action and obj.modifiers[0].object==arm
bpy.context.scene.frame_set(20); bpy.context.view_layer.update(); ev=obj.evaluated_get(bpy.context.evaluated_depsgraph_get()); assert max((a.co-b).length for a,b in zip(ev.data.vertices,neutral))>.1
print('NATIVE_SKELETAL_PASS')
