"""Bounded saved UE5.6 character spring-arm camera previews, not runtime viewpoints."""
import json, math
from pathlib import Path
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_editor_scene import external_packages,index_value
from ue5_editor_components import name_value
from skeleton_native import Reader

TRANSFORMS=(('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.)))
BOOLS=('bUsePawnControlRotation','bDoCollisionTest','bEnableCameraLag','bEnableCameraRotationLag','bInheritPitch','bInheritYaw','bInheritRoll','bConstrainAspectRatio','bUseFieldOfViewForLOD')


def merged_fields(instance,default):
    require(not any(k in instance or k in default for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')),'Absolute camera transform unsupported')
    def vector(k,typ):
        t=instance.get(k,default.get(k))
        if t is None:return None
        require(t['type']==['StructProperty',typ,'/Script/CoreUObject'] and len(t['data'])==24 and not t['flags']&0x20,'Invalid '+k)
        value=Reader(t['data']).unpack('3d');require(all(math.isfinite(v) for v in value),'Nonfinite '+k);return value
    fields={k:vector(k,typ) or fallback for k,typ,fallback in TRANSFORMS}
    require(all(abs(v-1)<1e-9 for v in fields['RelativeScale3D']),'Scaled spring-arm hierarchy unsupported')
    props={}
    for k in ('TargetArmLength','FieldOfView','AspectRatio'):
        t=instance.get(k,default.get(k))
        if t is not None:
            require(t['type']==['FloatProperty'] and len(t['data'])==4 and not t['flags']&0x28,'Invalid '+k);v=Reader(t['data']).unpack('f')[0];require(math.isfinite(v) and v>0,'Invalid '+k);props[k]=v
    for k in ('SocketOffset','TargetOffset'):
        v=vector(k,'Vector')
        if v is not None:props[k]=v
    for k in BOOLS:
        t=instance.get(k,default.get(k))
        if t is not None:
            require(t['type']==['BoolProperty'] and not t['data'] and not t['flags']&0x28,'Invalid '+k);props[k]=bool(t['flags']&16)
    if 'FieldOfView' in props:require(props['FieldOfView']<179,'Unsupported field of view')
    return fields,props


def class_camera(path,package,classname):
    m,b,im,ex,ref,pkg=read_tables(path);require(m['ue5'] in (1016,1017) and m.get('package_name')==package,'Blueprint package identity mismatch');names=m['names']
    cls=[i for i,e in enumerate(ex,1) if not e['outer'] and e['kind']=='BlueprintGeneratedClass' and e['name']==classname];require(len(cls)==1,'Class identity mismatch')
    cdo=[i for i,e in enumerate(ex,1) if not e['outer'] and e['class_index']==cls[0] and e['name']=='Default__'+classname];require(len(cdo)==1,'Missing camera CDO');di=cdo[0];at=export_tags(b,ref(di),names);indices=[index_value(at,k) for k in ('RootComponent','CameraBoom','FollowCamera')]
    require(all(i>0 for i in indices) and len(set(indices))==3,'Missing distinct CDO camera components')
    out=[]
    for i,kind,parent in zip(indices,('CapsuleComponent','SpringArmComponent','CameraComponent'),(0,indices[0],indices[1])):
        e=ref(i);require(e['outer']==di and e['kind']==kind,'Invalid CDO camera ownership');t=export_tags(b,e,names);require(index_value(t,'AttachParent')==parent,'Invalid CDO camera attachment');out.append((e['name'],t,names))
    return out


def records(content,map_path):
    content=Path(content).resolve();map_path=Path(map_path).resolve();m,_,_,ex,_,_=read_tables(map_path);require(m['ue5'] in (1016,1017) and any(e['kind']=='World' and not e['outer'] for e in ex),'Expected UE5.6 editor World');level='/Game/'+map_path.relative_to(content).with_suffix('').as_posix();result=[];skipped=[];cache={}
    for source in [map_path,*external_packages(content,map_path)]:
        rel=source.relative_to(content).as_posix()
        try:
            m,b,im,ex,ref,pkg=read_tables(source);names=m['names']
            for i,e in enumerate(ex,1):
                if e['kind']!='CameraComponent':continue
                try:
                    ai=e['outer'];a=ref(ai);require(ai>0 and a['kind'].endswith('_C') and a['class_index']<0,'Unsupported camera actor class');outer=a['outer'];parent=ref(outer);require(parent and parent['kind']=='Level' and parent['name']=='PersistentLevel','Not a PersistentLevel actor');require((source==map_path and outer>0) or (source!=map_path and outer<0 and pkg(outer)==level),'Camera level ownership mismatch')
                    at=export_tags(b,a,names);indices=[index_value(at,k) for k in ('RootComponent','CameraBoom','FollowCamera')];require(indices[-1]==i and all(j>0 for j in indices) and len(set(indices))==3,'Invalid saved camera component associations')
                    cp=pkg(a['class_index']);require(cp.startswith('/Game/'),'External camera class unsupported');p=(content/(cp[6:]+'.uasset')).resolve();require(p.is_relative_to(content) and p.is_file(),'Missing camera class package');key=(cp,a['kind'])
                    if key not in cache:cache[key]=class_camera(p,cp,a['kind'])
                    parts=[]
                    for j,kind,pi,d in zip(indices,('CapsuleComponent','SpringArmComponent','CameraComponent'),(0,indices[0],indices[1]),cache[key]):
                        v=ref(j);require(v['outer']==ai and v['kind']==kind and v['name']==d[0],'Camera component template mismatch');t=export_tags(b,v,names);require(index_value(t,'AttachParent')==pi,'Saved camera attachment mismatch');dt,dn=d[1:];fields,props=merged_fields(t,dt)
                        socket=name_value(t,'AttachSocketName',names) if 'AttachSocketName' in t else name_value(dt,'AttachSocketName',dn) if 'AttachSocketName' in dt else ''
                        require(socket in ('','None') or kind=='CameraComponent' and socket=='SpringEndpoint','Unexpected camera socket');parts.append(dict(name=v['name'],kind=kind,fields=fields,properties=props,serialized_socket=socket,untranslated_fields=sorted((set(t)|set(dt))-set(fields)-set(props)-{'AttachParent','AttachSocketName'})))
                    boom=parts[1]['properties'];require('TargetArmLength' in boom and boom['TargetArmLength']<=100000,'Missing or unsupported explicit spring-arm length');require(not any(boom.get('TargetOffset',(0.,0.,0.))),'Nonzero world-space spring target offset unsupported');cam=parts[2]['properties'];require('ProjectionMode' not in parts[2]['untranslated_fields'],'Explicit projection mode unsupported');label=a['name']
                    if 'ActorLabel' in at:
                        t=at['ActorLabel'];require(t['type']==['StrProperty'],'Invalid actor label');r=Reader(t['data']);label=r.string();require(r.pos==len(r.data),'Invalid actor label extent')
                    result.append(dict(source=rel,actor=a['name'],label=label,blueprint=cp,components=parts,fov_degrees=cam.get('FieldOfView',90.),fov_source='serialized' if 'FieldOfView' in cam else 'preview_default_not_serialized'))
                except Exception as exc:skipped.append(dict(source=rel,component=e['name'],detail=str(exc)))
        except Exception as exc:skipped.append(dict(source=rel,detail=str(exc)))
    require(len({(r['source'],r['actor']) for r in result})==len(result),'Duplicate saved camera actor identity')
    return dict(level=level,records=result,skipped=skipped)


def reconstruct(filepath):
    import bpy
    from mathutils import Matrix
    from blueprint_placement import apply_fields
    from project_session import new_ids,rollback_new
    from uasset import UProject
    path=Path(filepath).resolve();project=UProject(str(path));data=records(Path(project.dir)/'Content',path);require(data['records'],'No supported saved spring-arm camera records');require(not any(c.get('UE_camera_source')==str(path) for c in bpy.context.scene.collection.children_recursive),'Cameras already imported; remove prior camera preview collection before reimporting')
    before=set(new_ids())
    try:
        collection=bpy.data.collections.new('UE5 camera rig preview — '+path.stem);bpy.context.scene.collection.children.link(collection)
        for r in data['records']:
            def anchor(name,parent=None):
                o=bpy.data.objects.new(r['label']+' / '+name,None);collection.objects.link(o);o.parent=parent;o.empty_display_type='ARROWS';o.empty_display_size=.18;o['UE_preview_only']=True;o['UE_actor']=r['actor'];o['UE_source_actor_package']=r['source'];return o
            root,boom,cam=r['components'];a=anchor(root['name']);apply_fields(a,root['fields']);b=anchor(boom['name'],a);apply_fields(b,boom['fields']);endpoint=anchor('Unoccluded SpringEndpoint',b);p=boom['properties'];x,y,z=p.get('SocketOffset',(0.,0.,0.));endpoint.location=(y*.01,(x-p['TargetArmLength'])*.01,z*.01)
            d=bpy.data.cameras.new(r['label']+' / FollowCamera');d.type='PERSP';d.sensor_fit='HORIZONTAL';d.angle=math.radians(r['fov_degrees']);o=bpy.data.objects.new(r['label']+' / FollowCamera',d);collection.objects.link(o);o.parent=endpoint;apply_fields(o,cam['fields']);rot=o.rotation_euler.to_matrix()@Matrix.Rotation(math.pi/2,3,'X');o.rotation_mode='QUATERNION';o.rotation_quaternion=rot.to_quaternion();o['UE_preview_only']=True;o['UE_actor']=r['actor'];o['UE_source_actor_package']=r['source'];o['UE_camera_record']=json.dumps(r,sort_keys=True);o['UE_fov_source']=r['fov_source']
            for obj,part in ((a,root),(b,boom)):obj['UE_camera_component']=json.dumps(part,sort_keys=True)
        collection['UE_camera_source']=str(path);collection['UE_preview_only']=True;report=dict(**data,scope='Unoccluded spring-arm endpoint preview; explicit saved CDO and instance properties only. Camera FOV defaults to editable 90-degree preview if not serialized. Runtime control rotation, collisions, camera lag, native constructor defaults and post-processing are not evaluated. Active scene camera is not changed.');text=bpy.data.texts.new(collection.name+' - import report.json');text.write(json.dumps(report,indent=2));collection['UE_report']=text.name
        return collection,report
    except Exception:
        rollback_new(before);raise
