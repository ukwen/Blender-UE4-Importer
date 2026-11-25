"""Genuine cooked USkeleton acceptance, independent GLB rest-origin comparison."""
import os,sys,json,struct,tempfile
from pathlib import Path
import bpy
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import skeleton_native as sn, skeleton_blender as sb
root=Path(os.environ['MATYA_ASSETS'])
bpy.ops.wm.read_factory_settings(use_empty=True)
raw=(root/'raw/SK_Worm.glb').read_bytes(); size=struct.unpack_from('<I',raw,12)[0]
gltf=json.loads(raw[20:20+size]); joints=gltf['skins'][0]['joints']; nodes=gltf['nodes']
# Original GLB joint translations all lie on Y; rotate to Blender Z.
expected={}; parents={}
for i,j in enumerate(joints):
    node=nodes[j]; p=next((nodes[k]['name'] for k in joints if j in nodes[k].get('children',[])),None)
    parents[node['name']]=p
    t=node.get('translation',[0,0,0]); assert abs(t[0])+abs(t[2])<1e-6
    expected[node['name']]=(expected[p] if p else 0)+t[1]
objects=[]; decoded=[]; maximum=0
sb.register()
try:
    for version in ('4.18','4.27'):
        path=root/version/'SK_Worm_Skeleton.uasset'; name,bones=sn.read_cooked_skeleton(path,version); decoded.append(bones)
        assert len(bones)==6
        before=set(bpy.data.objects)
        assert getattr(bpy.ops,'import').ue_reference_skeleton(filepath=str(path),profile=version)=={'FINISHED'}
        obj=(set(bpy.data.objects)-before).pop(); objects.append(obj)
        for i,b in enumerate(bones):
            bone=obj.data.bones[b['name']]; assert bone['UE_bone_index']==i
            assert (bone.parent.name if bone.parent else None)==parents[b['name']]
            assert tuple(bone['UE_local_rotation_xyzw'])==b['rotation']
            err=(bone.head_local-Vector((0,0,expected[b['name']]))).length; maximum=max(maximum,err); assert err<1e-5
        assert abs(obj.data.bones['Trans']['UE_local_scale'][2]-100)<1e-6
        print('SKELETON',version,len(bones),[(b.name,tuple(b.head_local)) for b in obj.data.bones])
    assert decoded[0]==decoded[1]
    # Reject real wrong class and truncated sidecar before Blender creation.
    try: sn.read_cooked_skeleton(root/'4.27/SK_Worm.uasset','4.27')
    except ValueError: pass
    else: raise AssertionError('Mesh misidentified as skeleton')
    with tempfile.TemporaryDirectory() as tmp:
        p=Path(tmp)/'broken.uasset'; p.write_bytes(path.read_bytes()); p.with_suffix('.uexp').write_bytes(path.with_suffix('.uexp').read_bytes()[:-10])
        try: sn.read_cooked_skeleton(p,'4.27')
        except ValueError: pass
        else: raise AssertionError('Truncated sidecar accepted')
finally: sb.unregister()
objects[1].location.x=1
out=os.environ['UE_SKELETON_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
assert len(bpy.data.objects)==2 and all(len(o.data.bones)==6 and o['UE_skeleton_status']=='reference_pose_only' for o in bpy.data.objects)
print('REFERENCE_SKELETON_PASS maximum_origin_error_m',maximum)
