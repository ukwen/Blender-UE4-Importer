"""Bounded UE4 editor raw animation tracks. No compressed-codec guessing."""
import math
from pathlib import Path
from skeleton_native import Reader


def require(ok, message):
    if not ok: raise ValueError(message)


def read_raw_tracks(r, frame_count, expected=None):
    count=r.count(8192)
    require(expected is None or count==expected,'Raw track/name count mismatch')
    require(count*frame_count<=250000,'Animation sample limit exceeded')
    tracks=[]
    for _ in range(count):
        channels=[]
        for width,fmt in ((12,'3f'),(16,'4f'),(12,'3f')):
            stride,n=r.unpack('ii')
            require(stride==width and n in ((0,1,frame_count) if fmt=='3f' and len(channels)==2 else (1,frame_count)), 'Unsupported raw channel layout')
            values=[r.unpack(fmt) for _ in range(n)]
            require(all(math.isfinite(v) for key in values for v in key),'Nonfinite animation key')
            if fmt=='4f': require(all(abs(sum(x*x for x in q)-1)<.002 for q in values),'Invalid animation quaternion')
            if len(channels)==2: require(all(min(v)>0 for v in values),'Nonpositive animation scale unsupported')
            channels.append(values)
        tracks.append(channels)
    return tracks


def read_tagged_properties(r,names):
    """Read bounded UE4 tagged fields without interpreting unrelated payloads."""
    tags={}; kinds={}
    simple={'IntProperty','FloatProperty','ObjectProperty','NameProperty','StrProperty','Int64Property','UInt32Property','DoubleProperty','TextProperty','SoftObjectProperty'}
    while True:
        key=r.name(names)
        if key=='None': break
        typ=r.name(names); size,index=r.unpack('ii'); require(key not in tags and index==0 and size>=0,'Invalid animation property tag')
        inner=None; flag=None
        if typ=='StructProperty': inner=r.name(names); r.take(16)
        elif typ in ('ArrayProperty','SetProperty','ByteProperty','EnumProperty'): inner=r.name(names)
        elif typ=='MapProperty': inner=r.name(names); r.name(names)
        elif typ=='BoolProperty': flag=r.unpack('B')[0]; require(flag in (0,1) and size==0,'Invalid bool property')
        elif typ not in simple: raise ValueError('Unsupported animation property tag type: '+typ)
        guid=r.unpack('B')[0]; require(guid in (0,1),'Invalid property GUID flag')
        if guid: r.take(16)
        tags[key]=flag if typ=='BoolProperty' else r.take(size); kinds[key]=(typ,inner)
    return tags,kinds


def read_export(data,names,name):
    """Decode the tagged UE4.27 editor export and its native raw-track arrays."""
    r=Reader(data); tags,kinds=read_tagged_properties(r,names)
    def field(key,typ,fmt,default=None):
        if key not in tags: return default
        require(kinds[key][0]==typ,'Unexpected '+key+' type')
        v=Reader(tags[key]); result=v.unpack(fmt)[0]; require(v.pos==len(v.data),'Invalid '+key+' extent'); return result
    def enum(key):
        if key not in tags: return None
        require(kinds[key][0] in ('ByteProperty','EnumProperty','NameProperty'),'Unexpected '+key+' type')
        v=Reader(tags[key]); value=v.name(names); require(v.pos==len(v.data),'Invalid '+key+' extent'); return value
    frames=field('NumFrames','IntProperty','i'); duration=field('SequenceLength','FloatProperty','f')
    require(type(frames) is int and 1<=frames<=10000 and duration is not None and math.isfinite(duration) and 0<duration<=3600,'Invalid sequence timing')
    require(enum('AdditiveAnimType') in (None,'AAT_None'),'Additive animation unsupported')
    require(not tags.get('bEnableRootMotion',0),'Extracted root motion unsupported')
    if 'RetargetSource' in tags: require(enum('RetargetSource')=='None','Retarget source unsupported')
    require(field('RateScale','FloatProperty','f',1.)==1.,'Nonunit playback rate unsupported')
    require(kinds.get('AnimationTrackNames')==('ArrayProperty','NameProperty'),'Missing raw track names')
    tr=Reader(tags['AnimationTrackNames']); count=tr.count(8192); tracks=[tr.name(names) for _ in range(count)]
    require(tr.pos==len(tr.data) and count and len({n.casefold() for n in tracks})==count,'Invalid raw track names')
    skeleton=field('Skeleton','ObjectProperty','i'); require(skeleton is not None and skeleton<0,'Missing imported skeleton reference')
    guid=r.i(); require(guid in (0,1),'Unsupported animation object GUID');
    if guid: r.take(16)
    # Observed UE4.27 AnimationAsset editor native GUID, distinct from RawDataGuid.
    native_guid=None
    if 'RawDataGuid' in tags:
        require(kinds['RawDataGuid']==('StructProperty','Guid') and len(tags['RawDataGuid'])==16,'Unsupported raw-data GUID tag')
        native_guid=r.take(16).hex()
    require(r.unpack('BB')==(0,0),'Editor raw tracks unavailable or unsupported strip flags')
    raw=read_raw_tracks(r,frames,count)
    # Editor-only source tracks may also be present. Validate their extent; do not use them.
    source=read_raw_tracks(r,frames)
    compressed=r.i(); require(compressed in (0,1),'Invalid compressed-data flag')
    if not compressed: require(r.pos==len(r.data),'Unexpected animation trailer')
    else: require(r.pos<len(r.data),'Truncated compressed trailer')
    return dict(name=name,frames=frames,duration=duration,tracks=dict(zip(tracks,raw)),skeleton_index=skeleton,compressed_tail=len(r.data)-r.pos,source_tracks=len(source),native_guid=native_guid,ignored_curve_metadata=[key for key in tags if 'Curve' in key or 'Notify' in key])


def read_animation(path):
    """Versioned, monolithic UE4.27 editor assets with raw tracks only."""
    from package_inspector import inspect_package
    from uasset import UAsset
    from material_stage import package_reference
    path=Path(path); meta=inspect_package(path)
    require(meta.get('status')=='tables_inspected' and meta.get('legacy')==-7 and meta.get('ue4')==522 and meta.get('ue5') is None and not meta['sidecars'] and not meta['flags']&0x80002000 and meta['size']<=128*1024*1024,'Expected versioned monolithic UE4.27 editor animation')
    asset=UAsset(str(path),False)
    try:
        asset.Read(False)
        matches=[e for e in asset.exports if e.export_class_type=='AnimSequence' and e.outer_index==0]
        require(len(matches)==1,'Expected one root AnimSequence export')
        e=matches[0]; offset,size=e.serial_desc.offset,e.serial_desc.count
        require(meta['header_end']<=offset and 0<size<=meta['size']-offset,'Invalid animation export extent')
        asset.f.Seek(offset); data=read_export(asset.f.ReadBytes(size),asset.names,e.object_name)
        idx=data['skeleton_index']; require(-len(asset.imports)<=idx<0,'Invalid animation skeleton reference')
        ref=asset.DecodePackageIndex(idx); require(ref.class_name=='Skeleton','Animation skeleton reference is not USkeleton')
        package=package_reference(ref); require(bool(package),'Unresolved skeleton package')
        data['skeleton_package']=package; return data
    finally: asset.Close()


def make_action(arm,data,scene,start=1.,allow_subset=False):
    """Convert sampled UE local transforms to Blender rest-relative pose channels."""
    import bpy
    from mathutils import Matrix, Quaternion, Vector
    require(arm and arm.type=='ARMATURE' and arm.mode=='OBJECT','Select a native armature in Object mode')
    ad=arm.animation_data
    require(not ad or (ad.action is None and not ad.nla_tracks and not ad.drivers),'Existing animation present; import into an unanimated armature')
    require(not any(b.constraints for b in arm.pose.bones),'Constrained armatures unsupported')
    bones=sorted(arm.data.bones,key=lambda b:b.get('UE_bone_index',-1)); names=[b.name for b in bones]
    require(bones and [b.get('UE_bone_index') for b in bones]==list(range(len(bones))),'Native reference bone metadata required')
    source_package=data.get('skeleton_package'); target_package=arm.get('UE_skeleton_package')
    require(not target_package or target_package==source_package,'Animation skeleton package does not match selected armature')
    dropped=sorted(set(data['tracks'])-set(names))
    require(not dropped or (allow_subset and source_package and source_package==target_package and set(data['tracks']).intersection(names)), 'Animation tracks do not match selected skeleton; enable same-package subset explicitly')
    n=data['frames']; require(n*len(bones)<=250000,'Animation sample limit exceeded')
    axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
    rest=[]; defaults=[]; parents=[]
    for i,b in enumerate(bones):
        parent=names.index(b.parent.name) if b.parent else -1
        require(parent<i,'Invalid native bone hierarchy')
        parents.append(parent)
        defaults.append((tuple(b['UE_local_translation_cm']),tuple(b['UE_local_rotation_xyzw']),tuple(b['UE_local_scale'])))
        v=b['UE_world_matrix_m']; rest.append(Matrix([v[j:j+4] for j in range(0,16,4)]))
    def local(t,q,s):
        x,y,z,w=q
        return axis@Matrix.LocRotScale(Vector(t)*.01,Quaternion((w,x,y,z)).normalized(),Vector(s))@axis
    fps=scene.render.fps/scene.render.fps_base
    times=[start+(data['duration']*fps*i/(n-1) if n>1 else 0) for i in range(n)]
    values={name:[] for name in names}; prev={}
    for i in range(n):
        worlds=[]; desired=[]
        for j,b in enumerate(bones):
            t,q,s=defaults[j]; track=data['tracks'].get(b.name)
            if track:
                t,q,s=[channel[0 if len(channel)==1 else i] if channel else fallback for channel,fallback in zip(track,(t,q,s))]
            transform=local(t,q,s); p=parents[j]
            world=worlds[p]@transform if p>=0 else transform; worlds.append(world)
            pose=world@rest[j].inverted()@b.matrix_local; desired.append(pose)
            kwargs={'parent_matrix':desired[p],'parent_matrix_local':bones[p].matrix_local} if p>=0 else {}
            basis=b.convert_local_to_pose(pose,b.matrix_local,invert=True,**kwargs)
            loc,rot,scale=basis.decompose(); check=Matrix.LocRotScale(loc,rot,scale)
            require(max(abs(basis[x][y]-check[x][y]) for x in range(4) for y in range(4))<.0001,'Animation requires unsupported shear')
            if b.name in prev and rot.dot(prev[b.name])<0: rot.negate()
            prev[b.name]=rot.copy(); values[b.name].append(tuple(loc)+tuple(rot)+tuple(scale))
    action=bpy.data.actions.new(data['name']); action.use_fake_user=True
    modes={b.name:b.rotation_mode for b in arm.pose.bones}; had_animation=ad is not None
    try:
        for name,rows in values.items():
            pb=arm.pose.bones[name]
            for prop,offset,width in (('location',0,3),('rotation_quaternion',3,4),('scale',7,3)):
                for j in range(width):
                    fc=action.fcurves.new(pb.path_from_id(prop),index=j,action_group=name)
                    fc.keyframe_points.add(n); fc.keyframe_points.foreach_set('co',[v for i,row in enumerate(rows) for v in (times[i],row[offset+j])])
                    for key in fc.keyframe_points: key.interpolation='LINEAR'
                    fc.update()
        action['UE_duration_seconds']=data['duration']; action['UE_source_frames']=n; action['UE_source_skeleton']=data.get('skeleton_package',''); action['UE_compressed_tail_bytes']=data['compressed_tail']
        action['UE_omitted_tracks']=','.join(dropped); action['UE_animation_semantics']='raw_local_transforms_no_engine_retargeting'
        for b in arm.pose.bones: b.rotation_mode='QUATERNION'
        arm.animation_data_create().action=action
        return action
    except Exception:
        if arm.animation_data and arm.animation_data.action==action: arm.animation_data.action=None
        if not had_animation: arm.animation_data_clear()
        for name,mode in modes.items(): arm.pose.bones[name].rotation_mode=mode
        bpy.data.actions.remove(action); raise
