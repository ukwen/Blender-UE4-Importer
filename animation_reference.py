"""Compare an imported Action with externally provided component-space samples.
Reference provenance is supplied by the caller, never inferred or authenticated.
No mutation of rig, animation or scene (apart from temporarily evaluating frames).
"""
import math


def require(ok,message):
    if not ok:raise ValueError(message)


def compare_reference(arm,scene,reference):
    import bpy
    from mathutils import Matrix,Vector
    require(arm.type=='ARMATURE' and arm.animation_data and arm.animation_data.action,'Select an armature with an active imported Action')
    require(arm.name in scene.objects and isinstance(reference,dict),'Reference must be an object and armature must belong to the evaluated scene')
    a=arm.animation_data.action
    require(not arm.animation_data.nla_tracks and not arm.animation_data.drivers and not any(b.constraints for b in arm.pose.bones),'Reference comparison requires an isolated Action without NLA, drivers or constraints')
    require(a.get('UE_root_translation_mode') is None,'Compare original authored translation, not an in-place Action')
    require(reference.get('schema')=='ue_component_pose_reference_v1','Unknown reference schema')
    provenance=reference.get('provenance');require(isinstance(provenance,dict) and provenance.get('kind') in ('engine_evaluated','authored_fixture') and isinstance(provenance.get('description'),str) and provenance['description'].strip(),'Explicit reference provenance required')
    sha=a.get('UE_source_animation_sha256','');require(len(sha)==64 and reference.get('source_sha256')==sha,'Animation source SHA-256 mismatch')
    require(reference.get('skeleton_package')==a.get('UE_source_skeleton')==arm.get('UE_skeleton_package'),'Skeleton package mismatch')
    require(reference.get('animation_name')==a.get('UE_source_animation_name'),'Animation name mismatch')
    require(reference.get('space')=='unreal_component_cm_column_vector','Expected Unreal component-space matrices in centimeters, row-major storage and column-vector convention')
    names=reference.get('bones');require(isinstance(names,list) and all(isinstance(x,str) for x in names) and len(names)==len(set(names)) and set(names)==set(arm.pose.bones.keys()),'Reference must cover every target bone exactly once')
    frames=reference.get('frames');n=a.get('UE_source_frames');require(type(n) is int and isinstance(frames,list) and len(frames)==n and 2<=n<=10000 and n*len(names)<=250000,'Reference must cover every authored source sample')
    start=a.get('UE_sample_start_frame');step=a.get('UE_sample_step_frames');require(isinstance(start,(float,int)) and isinstance(step,(float,int)) and math.isfinite(start) and math.isfinite(step) and step>0,'Missing source sample timing')
    # Validate all reference content before changing the scene frame.
    for i,frame in enumerate(frames):
        require(isinstance(frame,dict) and type(frame.get('sample')) is int and frame['sample']==i and isinstance(frame.get('matrices'),list) and len(frame['matrices'])==len(names),'Invalid reference sample coverage/order')
        for row in frame['matrices']:
            require(isinstance(row,list) and len(row)==16 and all(type(v) in (float,int) and math.isfinite(v) for v in row) and max(abs(row[j]-v) for j,v in zip(range(12,16),(0.,0.,0.,1.)))<1e-8,'Invalid affine reference matrix')
    bones=[arm.pose.bones[name] for name in names];corrections=[]
    for b in bones:
        rest=b.bone.get('UE_world_matrix_m');require(rest is not None and len(rest)==16,'Missing native source bone metadata')
        corrections.append(b.bone.matrix_local.inverted()@Matrix([rest[j:j+4] for j in range(0,16,4)]))
    axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
    posmax=basemax=0.;worst_pos=None;worst_basis=None;old_frame,old_sub=scene.frame_current,scene.frame_subframe
    try:
        for i,frame in enumerate(frames):
            f=start+i*step;whole=math.floor(f);scene.frame_set(whole,subframe=f-whole);bpy.context.view_layer.update()
            for bone,correction,row in zip(bones,corrections,frame['matrices']):
                want=Matrix([row[j:j+4] for j in range(0,16,4)]);want.translation*=.01;want=axis@want@axis
                actual=bone.matrix@correction;require(all(math.isfinite(v) for row in actual for v in row),'Nonfinite evaluated pose');dp=(want.translation-actual.translation).length;db=max(abs(want[x][y]-actual[x][y]) for x in range(3) for y in range(3))
                if dp>posmax:posmax=dp;worst_pos=[i,bone.name]
                if db>basemax:basemax=db;worst_basis=[i,bone.name]
    finally:scene.frame_set(old_frame,subframe=old_sub);bpy.context.view_layer.update()
    return dict(reference_provenance=provenance,provenance_authenticated=False,source_sha256=sha,animation=a['UE_source_animation_name'],samples=n,bones=len(bones),compared_transforms=n*len(bones),position_tolerance_m=.0001,basis_tolerance=.0001,max_position_error_m=posmax,max_basis_element_error=basemax,worst_position=worst_pos,worst_basis=worst_basis,within_tolerance=posmax<=.0001 and basemax<=.0001)
