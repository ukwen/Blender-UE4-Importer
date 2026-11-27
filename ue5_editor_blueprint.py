"""UE5.7 saved class composition inspection. No execution or invented native defaults."""
import json
import math
from pathlib import Path
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_editor_scene import index_value
from ue5_editor_components import array,name_value
from skeleton_native import Reader

TRANSFORMS={'RelativeLocation':'Vector','RelativeRotation':'Rotator','RelativeScale3D':'Vector'}
SCENE_TYPES={'SceneComponent','ArrowComponent','CapsuleComponent','SkeletalMeshComponent','StaticMeshComponent','CameraComponent','SpringArmComponent','BoxComponent','SphereComponent'}
FLOATS={'CapsuleHalfHeight','CapsuleRadius','FieldOfView','FirstPersonFieldOfView','FirstPersonScale','OrthoWidth','OrthoNearClipPlane','OrthoFarClipPlane','ViewPitchMin','ViewPitchMax'}
BOOLS={'bOnlyOwnerSee','bOwnerNoSee','bUsePawnControlRotation','bEnableFirstPersonFieldOfView','bEnableFirstPersonScale','CastShadow','bAutoCalculateOrthoPlanes','bIsParentComponentNative'}


def inspect_class(path):
    path=Path(path).resolve();m,b,im,ex,ref,pkg=read_tables(path);names=m['names'];require(m['ue5']==1018,'Expected verified UE5.7 editor Blueprint profile')
    classes=[i for i,e in enumerate(ex,1) if not e['outer'] and e['kind']=='BlueprintGeneratedClass'];require(len(classes)==1,'Expected one Blueprint generated class');ci=classes[0];cls=ref(ci)
    cdos=[i for i,e in enumerate(ex,1) if not e['outer'] and e['class_index']==ci and e['name']=='Default__'+cls['name']];require(len(cdos)==1,'Expected one class default object');di=cdos[0]
    def tags(i):return export_tags(b,ref(i),names)
    def imported(i):
        require(i<0,'Expected import');obj=ref(i);seen=set();k=i;root=''
        while k<0:
            require(k not in seen,'Import outer cycle');seen.add(k);t=ref(k)
            if t['kind']=='Package':root=t['name'];break
            k=t['outer']
        require(root.startswith('/'),'Missing import package')
        return dict(package=root,name=obj['name'],kind=obj['kind'])
    def props(t):
        result={}
        for k,v in t.items():
            if k in FLOATS:
                require(v['type']==['FloatProperty'] and len(v['data'])==4 and not v['flags']&0x28,'Invalid '+k);x=Reader(v['data']).unpack('f')[0];require(math.isfinite(x),'Invalid '+k);result[k]=x
            elif k in BOOLS:
                require(v['type']==['BoolProperty'] and not v['data'] and not v['flags']&0x28,'Invalid '+k);result[k]=bool(v['flags']&16)
            elif k=='FirstPersonPrimitiveType':
                require(v['type'][0]=='EnumProperty' and len(v['data'])==8,'Invalid primitive type');result[k]=Reader(v['data']).name(names)
        return result
    cdo=tags(di);root=index_value(cdo,'RootComponent');by_index={};references={}
    for key,v in cdo.items():
        if v['type']!=['ObjectProperty']:continue
        idx=index_value(cdo,key)
        if idx<0:references[key]=imported(idx)
        elif idx>0 and ref(idx)['outer']==di and ref(idx)['kind'].endswith('Component'):
            by_index.setdefault(idx,[]).append(key)
    require(not root or root in by_index,'Invalid CDO root association')
    components={};template_lookup={}
    def add(i,variable,origin,aliases,socket=''):
        require(i>0 and i not in components,'Duplicate component template');e=ref(i);t=tags(i);fields={}
        require(not any(k in t for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')),'Absolute component transforms unsupported')
        for k,typ in TRANSFORMS.items():
            if k not in t:continue
            v=t[k];require(v['type']==['StructProperty',typ,'/Script/CoreUObject'] and len(v['data'])==24 and not v['flags']&0x20,'Invalid '+k);fields[k]=Reader(v['data']).unpack('3d');require(all(math.isfinite(x) for x in fields[k]),'Invalid '+k)
        if 'RelativeScale3D' in fields:require(all(abs(v)>1e-12 for v in fields['RelativeScale3D']),'Invalid scale')
        if 'AttachSocketName' in t:
            name=name_value(t,'AttachSocketName',names);require(not socket or name==socket,'Conflicting socket');socket=name
        if socket=='None':socket=''
        mesh_fields=[k for k in ('SkeletalMesh','SkinnedAsset','StaticMesh') if k in t];meshes=[]
        for k in mesh_fields:
            j=index_value(t,k)
            if j:
                q=imported(j);require(q['kind'] in ('SkeletalMesh','StaticMesh'),'Invalid mesh reference');meshes.append(q['package'])
        require(len(set(meshes))<=1,'Conflicting mesh identities')
        require(e['name'] not in template_lookup,'Ambiguous component template name');template_lookup[e['name']]=i
        components[i]=dict(index=i,variable=variable,aliases=aliases,template=e['name'],kind=e['kind'],origin=origin,package=meshes[0] if meshes else '',explicit=bool(mesh_fields),fields=fields,parent_index=0,parent='',socket=socket,properties=props(t),object_references={k:imported(index_value(t,k)) for k,v in t.items() if v['type']==['ObjectProperty'] and index_value(t,k)<0},scene_component=e['kind'] in SCENE_TYPES,uninterpreted_fields=sorted(set(t)-set(fields)-set(mesh_fields)-set(props(t))-{'AttachParent','AttachSocketName'}))
    for i,aliases in by_index.items():
        add(i,next((a for a in aliases if a!='RootComponent'),aliases[0]),'CDO',aliases)
    for i,c in components.items():
        parent=index_value(tags(i),'AttachParent');require(not parent or parent in components,'Unresolved CDO parent index');c['parent_index']=parent
        if i==root:require(not parent,'Root has an attachment')
    scs=index_value(tags(ci),'SimpleConstructionScript');active_nodes={};parent_nodes={};inactive=[]
    if scs:
        require(scs>0 and ref(scs)['kind']=='SimpleConstructionScript' and ref(scs)['outer']==ci,'Invalid SCS ownership');st=tags(scs);all_nodes=array(st,'AllNodes');roots=array(st,'RootNodes');require(len(set(all_nodes))==len(all_nodes) and len(set(roots))==len(roots) and set(roots)<=set(all_nodes),'Invalid SCS arrays')
        for ni in all_nodes:
            require(ni>0 and ref(ni)['kind']=='SCS_Node' and ref(ni)['outer']==scs,'Invalid SCS node');nt=tags(ni);ti=index_value(nt,'ComponentTemplate');require(ti>0 and ref(ti)['outer']==ci,'Invalid SCS component template');v=name_value(nt,'InternalVariableName',names);require(v and v!='None','Invalid SCS variable')
            comp_cls=index_value(nt,'ComponentClass');require(comp_cls<0 and ref(comp_cls)['name']==ref(ti)['kind'],'SCS class mismatch')
            socket=name_value(nt,'AttachToName',names) if 'AttachToName' in nt else ''
            add(ti,v,'SCS',[v],socket=socket);active_nodes[ni]=ti
            for child in array(nt,'ChildNodes'):
                require(child in all_nodes and child not in parent_nodes and child!=ni,'Invalid SCS child association');parent_nodes[child]=ni
        require(set(roots)==set(all_nodes)-set(parent_nodes),'SCS roots inconsistent with child graph')
        for ni,ti in active_nodes.items():
            nt=tags(ni);c=components[ti];external=name_value(nt,'ParentComponentOrVariableName',names) if 'ParentComponentOrVariableName' in nt else ''
            if ni in parent_nodes:
                require(not external or external=='None','Conflicting SCS parent');c['parent_index']=active_nodes[parent_nodes[ni]]
            elif external and external!='None':
                target=template_lookup.get(external);require(target in by_index and props(nt).get('bIsParentComponentNative') is True,'Unresolved SCS native parent');c['parent_index']=target
            elif not root and len(roots)==1:root=ti
            else:c['unresolved_parent']='Native constructor/SCS root attachment not serialized'
        inactive=[ref(i)['name'] for i,e in enumerate(ex,1) if e['outer']==scs and e['kind']=='SCS_Node' and i not in active_nodes]
    require(len({c['variable'] for c in components.values()})==len(components),'Duplicate component variable name')
    def resolve(i,seen=()):
        require(i not in seen,'Component attachment cycle');c=components[i];parent=c['parent_index']
        if parent:
            require(parent in components,'Missing component parent');resolve(parent,(*seen,i));c['parent']=components[parent]['template']
        elif c['scene_component'] and i!=root:c.setdefault('unresolved_parent','No serialized root attachment')
        if not c['scene_component']:c['placement']='metadata_only_non_scene_component'
        elif c['socket']:c['placement']='unresolved_socket'
        elif c.get('unresolved_parent') or parent and components[parent]['placement']!='anchor':c['placement']='unresolved_parent'
        else:c['placement']='anchor'
    for i in components:resolve(i)
    parent=imported(cls['super_index']);dependencies=sorted({pkg(-i) for i,x in enumerate(im,1) if x['kind'] in ('StaticMesh','SkeletalMesh') and pkg(-i)})
    return dict(version=1018,generated_class=cls['name'],parent_blueprint=parent['package'],parent_class=parent['name'],root_index=root,components=list(components.values()),mesh_dependencies=dependencies,cdo_properties=props(cdo),cdo_references=references,inactive_scs_nodes=inactive,scope='Serialized class defaults and active SCS topology only; no Blueprint execution, native constructor defaults or socket evaluation')


def build_preview(filepath,collection):
    import bpy
    from blueprint_placement import apply_fields
    from project_session import new_ids,rollback_new
    path=Path(filepath).resolve();data=inspect_class(path)
    require(not any(c.get('UE_blueprint_source')==str(path) for c in bpy.context.scene.collection.children_recursive),'Blueprint preview already imported')
    before=set(new_ids());created={}
    try:
        target=bpy.data.collections.new(data['generated_class']+' — saved component preview');collection.children.link(target);target['UE_blueprint_source']=str(path);target['UE_preview_only']=True
        pending=[c for c in data['components'] if c['placement']=='anchor']
        while pending:
            ready=[c for c in pending if not c['parent_index'] or c['parent_index'] in created];require(ready,'Unresolvable preview parent order')
            for c in ready:
                o=bpy.data.objects.new(c['variable'],None);target.objects.link(o);o.empty_display_type='ARROWS' if c['kind']=='ArrowComponent' else 'PLAIN_AXES';o.empty_display_size=.18
                if c['parent_index']:o.parent=created[c['parent_index']]
                fields={'RelativeLocation':(0.,0.,0.),'RelativeRotation':(0.,0.,0.),'RelativeScale3D':(1.,1.,1.)};fields.update(c['fields']);apply_fields(o,fields)
                o['UE_preview_only']=True;o['UE_component_index']=c['index'];o['UE_component_template']=c['template'];o['UE_component_kind']=c['kind'];o['UE_mesh_package']=c['package'];o['UE_blueprint_source']=str(path);o['UE_serialized_fields']=json.dumps(c['fields']);o['UE_component_properties']=json.dumps(c['properties']);o['UE_geometry_status']='not_reconstructed' if c['package'] else 'anchor';created[c['index']]=o;pending.remove(c)
        report=bpy.data.texts.new(target.name+' - report.json');report.write(json.dumps(data,indent=2));target['UE_report']=report.name
        return target,data
    except Exception:
        rollback_new(before);raise
