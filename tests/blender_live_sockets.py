import bpy,sys,json,math,os
from mathutils import Matrix,Quaternion,Vector
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from native_sockets import create_socket_anchors,register,unregister
full=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('UE_socket_definitions'))
body=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('UE_skeleton_package'))
records=json.loads(full['UE_socket_definitions']); assert len(records)==20
full.hide_set(False); full.hide_render=False
register()
try:
    for target in (full,body):
        bpy.ops.object.select_all(action='DESELECT'); full.select_set(True); target.select_set(True); bpy.context.view_layer.objects.active=target
        assert bpy.ops.object.ue_create_socket_anchors()=={'FINISHED'}
    try: create_socket_anchors(body,records)
    except ValueError: pass
    else: raise AssertionError('duplicate accepted')
    assert sum(bool(o.get('UE_socket_name')) for o in bpy.data.objects)==40
finally: unregister()
axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
def expected(arm,rec):
    # Independently compute the Unreal FRotator quaternion, then reflect axes.
    p,y,r=[math.radians(v)/2 for v in rec['rotation_pyr']]; sp,cp,sy,cy,sr,cr=math.sin(p),math.cos(p),math.sin(y),math.cos(y),math.sin(r),math.cos(r)
    q=Quaternion((cr*cp*cy+sr*sp*sy,cr*sp*sy-sr*cp*cy,-cr*sp*cy-sr*cp*sy,cr*cp*sy-sr*sp*cy))
    local=axis@Matrix.LocRotScale(Vector(rec['location_cm'])*.01,q,Vector(rec['scale']))@axis
    b=arm.data.bones[rec['bone']]; v=b['UE_world_matrix_m']; source=Matrix([v[i:i+4] for i in range(0,16,4)])
    return arm.matrix_world@arm.pose.bones[b.name].matrix@b.matrix_local.inverted()@source@local

def verify(arm):
    bpy.context.view_layer.update(); err=0
    for o in arm.children:
        if not o.get('UE_socket_name'): continue
        rec=json.loads(o['UE_socket_definition']); want=expected(arm,rec)
        err=max(err,max(abs(o.matrix_world[i][j]-want[i][j]) for i in range(4) for j in range(4)))
        assert (o.matrix_world.to_3x3().determinant()<0)==(want.to_3x3().determinant()<0)
    return err
scene=bpy.context.scene
report=[]
for clip in ('ThirdPersonIdle','ThirdPersonWalk','ThirdPersonRun'):
    for rig,curves in [(full,720),(body,440)]:
        action=next(a for a in bpy.data.actions if a.name.startswith(clip) and len(a.fcurves)==curves); rig.animation_data_create().action=action
    errs=[]; origins=[]
    for frac in (0,.25,.5,.75,1):
        t=1+(body.animation_data.action.frame_range[1]-1)*frac; f=math.floor(t); scene.frame_set(f,subframe=t-f)
        errs.append(max(verify(full),verify(body)))
        origins.append(next(o for o in body.children if o.get('UE_socket_name')=='SOC_hand_r').matrix_world.translation.copy())
    motion=max((v-origins[0]).length for v in origins); assert max(errs)<1e-5 and motion>1e-4
    report.append(dict(clip=clip,samples=5,anchors=40,max_matrix_error=max(errs),hand_motion_m=motion)); print(report[-1])
# Verify a child object follows the actual anchor without fake source geometry.
anchor=next(o for o in body.children if o.get('UE_socket_name')=='SOC_hand_r')
probe=bpy.data.objects.new('TEST ONLY socket follower',None); bpy.context.collection.objects.link(probe); probe.parent=anchor; probe.location=(.1,.02,.03)
bpy.context.view_layer.update(); assert (probe.matrix_world.translation-anchor.matrix_world@Vector(probe.location)).length<1e-6
bpy.data.objects.remove(probe,do_unlink=True)
full.hide_set(True); full.hide_render=True
for o in full.children:
    if o.get('UE_socket_name'): o.hide_set(True); o.hide_render=True
body.animation_data.action=next(a for a in bpy.data.actions if a.name.startswith('ThirdPersonWalk') and len(a.fcurves)==440)
scene.frame_set(1); bpy.ops.object.select_all(action='DESELECT'); body.select_set(True); bpy.context.view_layer.objects.active=body
out=os.environ['UE_SOCKET_OUTPUT']; bpy.ops.wm.save_as_mainfile(filepath=out); bpy.ops.wm.open_mainfile(filepath=out)
body=next(o for o in bpy.data.objects if o.type=='ARMATURE' and o.get('UE_skeleton_package')); bpy.context.scene.frame_set(16); assert verify(body)<1e-5 and sum(bool(o.get('UE_socket_name')) for o in bpy.data.objects)==40
Path(os.environ['UE_SOCKET_REPORT']).write_text(json.dumps(report,indent=2)); print('SOCKET_REOPEN_PASS')
