"""UE5.6 editor FK control-rig dense transform samples, not runtime evaluation."""
import math
from skeleton_native import Reader
from ue5_blueprint import read_tables, require
from ue5_editor_tags import export_tags, read_tags, read_tag_stream


def quaternion_xyz(x,y,z):
    r,p,yaw=[math.radians(a)*.5 for a in (x,y,z)]
    cr,sr=math.cos(r),-math.sin(r); cp,sp=math.cos(p),-math.sin(p); cy,sy=math.cos(yaw),math.sin(yaw)
    return (sr*cp*cy-cr*sp*sy,cr*sp*cy+sr*cp*sy,cr*cp*sy-sr*sp*cy,cr*cp*cy+sr*sp*sy)


def read_channel(data,n):
    r=Reader(data); require(r.unpack('BBi')==(4,4,4),'Unsupported movie scene float channel header')
    count=r.count(10000); require(count in (0,n),'Unsupported sparse transform channel')
    require(all(r.i()==i for i in range(count)),'Nonconsecutive channel key times')
    require(r.i()==28 and r.i()==count,'Unsupported channel value layout')
    values=[]
    for _ in range(count):
        v=r.unpack('f')[0];r.take(24);require(math.isfinite(v),'Nonfinite channel value');values.append(v)
    default,has_default,num,den,show=r.unpack('f4i');require(has_default in (0,1) and (num,den,show)==(30,1,0) and r.pos==len(data),'Unsupported channel trailer')
    require(count or (has_default and math.isfinite(default)),'Missing constant channel')
    return values if count else [default]*n


def read_scalar_channel(data,n):
    """Read sparse source scalar keys; unweighted tangents in value/source-frame units."""
    r=Reader(data);require(r.unpack('BBi')==(4,4,4),'Unsupported scalar extrapolation')
    count=r.count(10000);times=[r.i() for _ in range(count)]
    require(all(0<=t<n for t in times) and all(a<b for a,b in zip(times,times[1:])),'Invalid scalar key times')
    require(r.unpack('ii')==(28,count),'Unsupported scalar key layout');keys=[]
    for t in times:
        raw=r.take(28);v,a,b,aw,bw,weight,*pad=rdr_scalar(raw)
        interp,tangent=pad[3:5]
        require(all(math.isfinite(x) for x in (v,a,b,aw,bw)) and weight==0 and interp in (0,1,2) and tangent in (0,1,2) and not any(pad[:3]+pad[5:]),'Unsupported scalar tangent or interpolation mode')
        keys.append(dict(frame=t,value=v,arrive=a,leave=b,arrive_weight=aw,leave_weight=bw,interpolation=interp,tangent_mode=tangent))
    default,has_default,num,den,show=r.unpack('f4i');require(has_default in (0,1) and (num,den,show)==(30,1,0) and r.pos==len(data) and math.isfinite(default) and (keys or has_default),'Invalid scalar channel trailer')
    return dict(keys=keys,default=default,has_default=bool(has_default))


def rdr_scalar(raw):
    import struct
    return struct.unpack('<5f8B',raw)


def read_animation(path):
    m,b,im,ex,ref,pkg=read_tables(path);names=m['names'];require(m['ue5']==1017,'Expected UE5.6 editor animation profile 1017')
    def val(t,k,typ,fmt,default=None):
        if k not in t:return default
        v=t[k];require(v['type']==typ,'Unexpected '+k+' type');r=Reader(v['data']);x=r.unpack(fmt);require(r.pos==len(r.data),'Invalid '+k+' extent');return x[0] if len(x)==1 else x
    def obj(t,k,typ='ObjectProperty'):return val(t,k,[typ],'i',0)
    def nm(t,k):
        v=t[k];r=Reader(v['data']);s=r.name(names);require(r.pos==len(r.data),'Invalid name '+k);return s
    def boolean(t,k):
        if k not in t:return False
        v=t[k];require(v['type']==['BoolProperty'] and not v['data'],'Invalid bool '+k);return bool(v['flags']&16)
    def owned(i,kind,parent):
        require(i>0 and ref(i)['kind']==kind and ref(i)['outer']==parent,'Invalid '+kind+' ownership');return export_tags(b,ref(i),names)
    def one(t,k):
        v=t[k];require(v['type']==['ArrayProperty','ObjectProperty'],'Invalid '+k);r=Reader(v['data']);require(r.i()==1,'Expected single '+k);i=r.i();require(r.pos==len(r.data),'Invalid array extent');return i
    def rate(t,k):
        v=t[k];require(v['type']==['StructProperty','FrameRate','/Script/CoreUObject'],'Invalid frame rate');p=read_tags(v['data'],names);require(val(p,'Numerator',['IntProperty'],'i')==30 and val(p,'Denominator',['IntProperty'],'i',1)==1 and not set(p)-{'Numerator','Denominator'},'Unsupported frame rate')
    roots=[i for i,e in enumerate(ex,1) if not e['outer'] and e['kind']=='AnimSequence'];require(len(roots)==1,'Expected one root animation');root=roots[0];t=export_tags(b,ref(root),names)
    preview=bool({'AdditiveAnimType','RetargetSourceAsset','RetargetSourceAssetReferencePose'} & set(t))
    additive={}; retarget={}
    if 'AdditiveAnimType' in t:
        require(t['AdditiveAnimType']['type']==['ByteProperty','EAdditiveAnimationType','/Script/Engine'] and t['RefPoseType']['type']==['ByteProperty','EAdditiveBasePoseType','/Script/Engine'],'Invalid additive metadata types')
        mode,base=nm(t,'AdditiveAnimType'),nm(t,'RefPoseType');require(mode in ('AAT_LocalSpaceBase','AAT_RotationOffsetMeshSpace') and base in ('ABPT_AnimFrame','ABPT_LocalAnimFrame'),'Unsupported additive metadata')
        frame=val(t,'RefFrameIndex',['IntProperty'],'i',0);require(0<=frame<10000,'Invalid additive reference frame')
        idx=obj(t,'RefPoseSeq');source=None
        if idx:
            item=ref(idx);require(item['kind']=='AnimSequence','Invalid additive reference class');source=dict(name=item['name'],package=pkg(idx),self_reference=idx==root)
            require(source['package'] or source['self_reference'],'Unresolved additive reference')
        require((base=='ABPT_AnimFrame' and source is not None) or (base=='ABPT_LocalAnimFrame' and source is None),'Unexpected additive base sequence')
        additive=dict(mode=mode,base_type=base,frame=frame,sequence=source)
    if 'RetargetSourceAsset' in t:
        from ue5_dependencies import read_dependencies
        from ue5_editor_skeleton import checked_transform
        idx=obj(t,'RetargetSourceAsset','SoftObjectProperty');paths=read_dependencies(path)['soft_object_paths'];require(0<=idx<len(paths) and paths[idx]['package'] and not paths[idx]['subpath'],'Invalid retarget source asset')
        pose=[]
        if 'RetargetSourceAssetReferencePose' in t:
            v=t['RetargetSourceAssetReferencePose'];require(v['type']==['ArrayProperty','StructProperty','Transform','/Script/CoreUObject'],'Invalid retarget reference pose type');rr=Reader(v['data'])
            for _ in range(rr.count(8192)):
                tags=read_tag_stream(rr,names);require(set(tags)=={'Rotation','Translation','Scale3D'},'Invalid retarget transform fields');vals=[]
                for k,typ,fmt in [('Rotation','Quat','4d'),('Translation','Vector','3d'),('Scale3D','Vector','3d')]:
                    v=tags[k];require(v['type']==['StructProperty',typ,'/Script/CoreUObject'],'Invalid retarget transform type');vreader=Reader(v['data']);vals.extend(vreader.unpack(fmt));require(vreader.pos==len(vreader.data),'Invalid retarget transform extent')
                pose.append(checked_transform(vals))
            require(pose and rr.pos==len(rr.data),'Invalid retarget reference pose extent')
        retarget=dict(asset=paths[idx],pose=pose,reference_pose_present=bool(pose))
    else:require('RetargetSourceAssetReferencePose' not in t,'Retarget pose has no asset identity')
    rate_scale=val(t,'RateScale',['FloatProperty'],'f',1.);require(math.isfinite(rate_scale) and 0<rate_scale<=100,'Invalid rate scale')
    duration=val(t,'SequenceLength',['FloatProperty'],'f');require(duration is not None and math.isfinite(duration) and 0<duration<=3600,'Invalid sequence length');n=round(duration*30)+1;require(2<=n<=10000 and abs(duration*30-(n-1))<.002,'Nonintegral source duration')
    sk=obj(t,'Skeleton');require(sk<0 and ref(sk)['kind']=='Skeleton' and pkg(sk),'Missing source skeleton')
    mi=obj(t,'DataModelInterface','InterfaceProperty');model=owned(mi,'AnimationSequencerDataModel',root);require(boolean(model,'bPopulated'),'Unpopulated animation model');si=obj(model,'MovieScene');scene=owned(si,'MovieScene',mi);rate(scene,'TickResolution');rate(scene,'DisplayRate')
    def check_range(t,k,section):
        v=t[k];require(v['type']==['StructProperty','MovieSceneFrameRange','/Script/MovieScene'],'Invalid range');r=Reader(v['data']);a,x,z,y=r.unpack('BiBi');require(r.pos==len(r.data) and (a,x)==(1,0) and ((z,y)==(1,n-1) or (not section and (z,y)==(0,n))),'Unsupported animation range')
    check_range(scene,'PlaybackRange',False);ti=one(scene,'Tracks');track=owned(ti,'MovieSceneControlRigParameterTrack',si);ci=obj(track,'ControlRig');rig=owned(ci,'FKControlRig',ti);require(nm(rig,'ApplyMode')=='EControlRigFKRigExecuteMode::Direct' and not obj(rig,'DynamicHierarchy'),'Unsupported FK rig mode');active=rig['IsControlActive'];require(active['type']==['ArrayProperty','BoolProperty'],'Invalid control activation');ar=Reader(active['data']);require(len(ar.data)>4 and ar.take(ar.count(8192))==b'\1'*(len(ar.data)-4) and ar.pos==len(ar.data),'Inactive control unsupported')
    section_index=one(track,'Sections');section=owned(section_index,'MovieSceneControlRigParameterSection',ti);require(obj(section,'ControlRig')==ci,'Section rig mismatch');cls=obj(section,'ControlRigClass');require(cls<0 and ref(cls)['name']=='FKControlRig','Unexpected section rig class');check_range(section,'SectionRange',True)
    easing=read_tags(section['Easing']['data'],names);require(set(easing)=={'EaseIn','EaseOut'},'Unsupported section easing')
    for k in easing:require(not owned(obj(easing,k,'InterfaceProperty'),'MovieSceneBuiltInEasingFunction',section_index),'Nondefault section easing unsupported')
    blend=read_tags(section['BlendType']['data'],names);require(set(blend)=={'bIsValid'} and boolean(blend,'bIsValid'),'Unsupported section blend')
    require(not set(section)-{'ControlRig','ControlRigClass','TransformParameterNamesAndCurves','Easing','SectionRange','BlendType','Signature','ScalarParameterNamesAndCurves','ControlChannelMap'},'Additional section channels unsupported')
    curves={}
    if 'ScalarParameterNamesAndCurves' in section:
        v=section['ScalarParameterNamesAndCurves'];require(v['type']==['ArrayProperty','StructProperty','ScalarParameterNameAndCurve','/Script/MovieSceneTracks'],'Invalid scalar curve array');sr=Reader(v['data'])
        for _ in range(sr.count(256)):
            st=read_tag_stream(sr,names);require(set(st)=={'ParameterName','ParameterCurve'},'Invalid scalar parameter fields');name=nm(st,'ParameterName');require(name.endswith('_CURVE_CONTROL') and name[:-14] and name[:-14] not in curves,'Invalid or duplicate scalar name');v=st['ParameterCurve'];require(v['type']==['StructProperty','MovieSceneFloatChannel','/Script/MovieScene'],'Invalid scalar channel type');curves[name[:-14]]=read_scalar_channel(v['data'],n)
        require(sr.pos==len(sr.data),'Invalid scalar array extent')
    require('ControlChannelMap' not in section or bool(curves),'Unresolved control channel map')
    v=section['TransformParameterNamesAndCurves'];require(v['type']==['ArrayProperty','StructProperty','TransformParameterNameAndCurves','/Script/MovieSceneTracks'],'Invalid transform curve array');r=Reader(v['data']);count=r.count(8192);require(0<count<=512 and count*n<=250000,'Unsupported dense control count');tracks={}
    keys=[(k if j==0 else (k,j)) for k in ('Translation','Rotation','Scale') for j in range(3)]
    for _ in range(count):
        p=read_tag_stream(r,names,indexed=True);require(set(p)==set(keys)|{'ParameterName'},'Invalid transform channel set');name=nm(p,'ParameterName');require(name.endswith('_CONTROL') and name[:-8].casefold() not in {k.casefold() for k in tracks},'Invalid or duplicate control name');channels=[]
        for k in keys:
            v=p[k];require(v['type']==['StructProperty','MovieSceneFloatChannel','/Script/MovieScene'],'Invalid transform channel type');channels.append(read_channel(v['data'],n))
        trans=list(zip(*channels[:3]));rot=[quaternion_xyz(*xyz) for xyz in zip(*channels[3:6])];scale=list(zip(*channels[6:]));require(all(min(s)>0 for s in scale),'Nonpositive source scale');tracks[name[:-8]]=[trans,rot,scale]
    require(r.pos==len(r.data),'Unexpected transform array trailer')
    return dict(name=ref(root)['name'],frames=n,duration=(n-1)/30,tracks=tracks,skeleton_package=pkg(sk),compressed_tail=0,semantics='editor_fk_direct_local_transforms_no_engine_root_motion_or_retargeting',source_root_motion=boolean(t,'bEnableRootMotion'),source_root_lock=boolean(t,'bForceRootLock'),source_fps=30,source_controls=count,source_preview_required=preview,source_additive=additive,source_retarget=retarget,source_rate_scale=rate_scale,scalar_curves=curves,ignored_metadata=[key for key in t if key in ('AttributeCurves','RawCurveData','AnimNotifyTracks','AuthoredSyncMarkers')]+(['ControlChannelMap'] if 'ControlChannelMap' in section else []),source_retarget_name=nm(t,'RetargetSource') if 'RetargetSource' in t else '')
