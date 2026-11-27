"""Saved UE5.6 Blueprint static component instances, with explicit CDO/SCS defaults.
No execution of construction scripts or native C++ constructors.
"""
from pathlib import Path
import math,re
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_editor_scene import index_value,external_packages
from skeleton_native import Reader


def array(tags,key):
    if key not in tags:return []
    v=tags[key];require(v['type']==['ArrayProperty','ObjectProperty'],'Invalid object array '+key)
    r=Reader(v['data']);a=[r.i() for _ in range(r.count(4096))];require(r.pos==len(r.data),'Invalid object array extent');return a


def name_value(tags,key,names):
    v=tags[key];require(v['type']==['NameProperty'] and len(v['data'])==8,'Invalid name '+key);return Reader(v['data']).name(names)


def class_defaults(path,classname):
    m,b,im,ex,ref,pkg=read_tables(path);names=m['names'];require(m['ue5'] in (1016,1017),'Unsupported Blueprint version')
    cls=[i for i,e in enumerate(ex,1) if e['kind']=='BlueprintGeneratedClass' and e['name']==classname and not e['outer']];require(len(cls)==1,'Class identity mismatch');cls=cls[0]
    cdo=[i for i,e in enumerate(ex,1) if e['name']=='Default__'+classname and e['class_index']==cls and not e['outer']];require(len(cdo)==1,'Missing class default object');cdo=cdo[0]
    defaults={}
    def add(name,i,origin):
        e=ref(i);require(name not in defaults,'Ambiguous component default '+name);defaults[name]=(e['kind'],export_tags(b,e,names),ref,pkg,names,origin)
    for i,e in enumerate(ex,1):
        if e['outer']==cdo and e['kind'].endswith('Component'):add(e['name'],i,'CDO')
    ct=export_tags(b,ref(cls),names);scs=index_value(ct,'SimpleConstructionScript')
    if scs:
        require(scs>0 and ref(scs)['kind']=='SimpleConstructionScript' and ref(scs)['outer']==cls,'Invalid SCS ownership')
        st=export_tags(b,ref(scs),names)
        for i in array(st,'AllNodes'):
            require(i>0 and ref(i)['kind']=='SCS_Node' and ref(i)['outer']==scs,'Invalid SCS node')
            nt=export_tags(b,ref(i),names);ti=index_value(nt,'ComponentTemplate');require(ti>0 and ref(ti)['outer']==cls,'Invalid SCS template')
            name=name_value(nt,'InternalVariableName',names)
            if name not in defaults:add(name,ti,'SCS')
            else:require(defaults[name][0]==ref(ti)['kind'],'Conflicting CDO/SCS component '+name)
    # Construction-script templates are not executed. An instance may use a
    # same-name class-owned template only with an exact matching import.
    for i,e in enumerate(ex,1):
        if e['outer']==cls and e['kind']=='StaticMeshComponent' and e['name'].startswith('NODE_AddStaticMeshComponent-'):
            add(e['name'],i,'construction_template')
    return defaults


def numbered_construction_template(e, tags, owned, read_owned, defaults, names, root):
    """Resolve repeated UCS additions only with a matching numbered FName,
    serialized UCS index, unique base template and complete sibling sequence.
    No nearest-name or missing-index fallback. Runtime verification remains open.
    """
    match=re.fullmatch(r'(NODE_AddStaticMeshComponent-\d+)_(\d+)',e['name'])
    if not match:return None
    base,number=match.group(1),int(match.group(2));d=defaults.get(base)
    if not d or d[0]!=e['kind'] or d[-1]!='construction_template':return None
    def ucs(t):
        v=t.get('CreationMethod');idx=t.get('UCSSerializationIndex')
        if not v or v['type']!=['EnumProperty','EComponentCreationMethod','/Script/Engine','ByteProperty'] or len(v['data'])!=8:return None
        if Reader(v['data']).name(names)!='EComponentCreationMethod::UserConstructionScript':return None
        if not idx or idx['type']!=['IntProperty'] or len(idx['data'])!=4:return None
        return Reader(idx['data']).i()
    if ucs(tags)!=number+1:return None
    siblings={}
    for j,v in owned.items():
        if v['kind']!=e['kind']:continue
        name=v['name'];m=re.fullmatch(re.escape(base)+r'_(\d+)',name)
        if name!=base and not m:continue
        expected=0 if name==base else int(m.group(1))+1;t=read_owned(j)
        if ucs(t)!=expected or expected in siblings or index_value(t,'AttachParent')!=root:return None
        siblings[expected]=name
    if not siblings or sorted(siblings)!=list(range(max(siblings)+1)) or 0 not in siblings:return None
    return base,d


def placements(content,map_path):
    content=Path(content).resolve();map_path=Path(map_path).resolve();level='/Game/'+map_path.relative_to(content).with_suffix('').as_posix();out=[];skipped=[];cache={}
    for source in [map_path,*external_packages(content,map_path)]:
        try:m,b,im,ex,ref,pkg=read_tables(source)
        except Exception:continue # package-level failures are reported by existing map audit
        names=m['names']
        for ai,a in enumerate(ex,1):
            if not (a['kind'].endswith('_C') and a['class_index']<0):continue
            parent=ref(a['outer']);
            if not parent or parent.get('kind')!='Level' or parent['name']!='PersistentLevel':continue
            if source!=map_path and (a['outer']>=0 or pkg(a['outer'])!=level):continue
            if source==map_path and a['outer']<=0:continue
            owned={i:e for i,e in enumerate(ex,1) if e['outer']==ai and e['kind'].endswith('Component')};meshes=[i for i,e in owned.items() if e['kind']=='StaticMeshComponent']
            if not meshes:continue
            try:
                cp=pkg(a['class_index']);require(cp.startswith('/Game/'),'External class unsupported');p=(content/(cp[6:]+'.uasset')).resolve();require(p.is_relative_to(content) and p.is_file(),'Missing Blueprint package')
                key=(p,a['kind']);
                if key not in cache:cache[key]=class_defaults(p,a['kind'])
                defaults=cache[key];at=export_tags(b,a,names);root=index_value(at,'RootComponent');require(root in owned,'Missing saved root component');label=a['name']
                if 'ActorLabel' in at:
                    r=Reader(at['ActorLabel']['data']);label=r.string();require(r.pos==len(r.data),'Invalid actor label')
                plans={}
                def plan(i,stack=()):
                    require(i in owned and i not in stack,'Invalid or cyclic saved attachment');
                    if i in plans:return
                    e=owned[i];t=export_tags(b,e,names);template_name=e['name'];d=defaults.get(template_name);numbered=False
                    if d is None:
                        match=numbered_construction_template(e,t,owned,lambda j:export_tags(b,owned[j],names),defaults,names,root)
                        if match:template_name,d=match;numbered=True
                    require(d is not None and d[0]==e['kind'],'No exact serialized component default for '+e['name'])
                    dt,dr,dp,dn,origin=d[1:]
                    if origin=='construction_template':
                        matching=[v for j,v in enumerate(im,1) if v['name']==template_name and v['kind']==e['kind'] and v['outer']==a['class_index'] and pkg(-j)==cp]
                        require(len(matching)==1,'Missing exact construction-template import')
                        if numbered:origin='indexed_construction_template'
                    require(not any(k in t or k in dt for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale','AttachSocketName')),'Absolute/socket transform unsupported')
                    pi=index_value(t,'AttachParent');require((i==root and not pi) or (i!=root and pi in owned),'Missing explicit saved parent')
                    if pi:plan(pi,(*stack,i))
                    fields={}
                    for k,kind,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]:
                        v=t.get(k,dt.get(k));fields[k]=default
                        if v:
                            require(v['type']==['StructProperty',kind,'/Script/CoreUObject'] and len(v['data'])==24 and not v['flags']&0x20,'Invalid component transform');fields[k]=Reader(v['data']).unpack('3d')
                    require(all(math.isfinite(x) for v in fields.values() for x in v) and all(abs(x)>1e-12 for x in fields['RelativeScale3D']),'Invalid component transform')
                    mesh='';overrides=[]
                    if e['kind']=='StaticMeshComponent':
                        local='StaticMesh' in t;mt=t if local else dt;rr,pp=(ref,pkg) if local else (dr,dp);mi=index_value(mt,'StaticMesh');require(mi<0 and rr(mi)['kind']=='StaticMesh' and pp(mi),'Missing explicit static mesh');mesh=pp(mi)
                        local='OverrideMaterials' in t;rr,pp=(ref,pkg) if local else (dr,dp)
                        for mi in array(t if local else dt,'OverrideMaterials'):
                            require(mi==0 or mi<0 and rr(mi)['kind'] in ('Material','MaterialInstanceConstant') and pp(mi),'Invalid material override');overrides.append(pp(mi) if mi else '')
                    require(e['kind'] in ('StaticMeshComponent','SceneComponent','CapsuleComponent','SphereComponent','BoxComponent'),'Unsupported ancestor '+e['kind'])
                    plans[i]=dict(index=i,parent=pi,name=e['name'],kind=e['kind'],package=mesh,fields=fields,overrides=overrides,default_origin=origin,template_name=template_name)
                for i in meshes:
                    try:plan(i)
                    except Exception as exc:skipped.append(dict(source=str(source.relative_to(content)),actor=a['name'],component=owned[i]['name'],detail=str(exc)))
                # Retain only chains ending in successfully resolved mesh components.
                needed=set()
                for i in meshes:
                    if i in plans:
                        while i and i not in needed:needed.add(i);i=plans[i]['parent']
                if needed:out.append(dict(source=source.relative_to(content).as_posix(),actor=a['name'],label=label,blueprint=cp,components=[v for i,v in plans.items() if i in needed]))
            except Exception as exc:skipped.append(dict(source=str(source.relative_to(content)),actor=a['name'],detail=str(exc)))
    return out,skipped


def character_fields(tags):
    require(not any(k in tags for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale','AttachSocketName')),'Unsupported character transform');out={}
    for k,kind,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]:
        v=tags.get(k);out[k]=default
        if v:
            require(v['type']==['StructProperty',kind,'/Script/CoreUObject'] and len(v['data'])==24 and not v['flags']&0x20,'Invalid character transform');out[k]=Reader(v['data']).unpack('3d')
    require(all(math.isfinite(x) for v in out.values() for x in v) and min(out['RelativeScale3D'])>0,'Invalid character transform');return out

def character_defaults(path):
    """Explicit CDO body/root pair. No inference from imported mesh lists."""
    path=Path(path).resolve();m,b,im,ex,ref,pkg=read_tables(path);names=m['names'];require(m['ue5'] in (1016,1017),'Unsupported editor Blueprint version')
    classes=[i for i,e in enumerate(ex,1) if e['kind']=='BlueprintGeneratedClass' and not e['outer']];require(len(classes)==1,'Expected one generated class');ci=classes[0];cls=ref(ci)
    cdos=[i for i,e in enumerate(ex,1) if e['class_index']==ci and e['name']=='Default__'+cls['name'] and not e['outer']];require(len(cdos)==1,'Missing CDO');di=cdos[0];t=export_tags(b,ref(di),names)
    ri,mi=index_value(t,'RootComponent'),index_value(t,'Mesh');require(ri>0 and mi>0 and ri==index_value(t,'CapsuleComponent'),'Expected explicit character root and body')
    root,mesh=ref(ri),ref(mi);require(root['outer']==mesh['outer']==di and root['kind']=='CapsuleComponent' and mesh['kind']=='SkeletalMeshComponent','Invalid CDO component ownership')
    rt,mt=export_tags(b,root,names),export_tags(b,mesh,names);require(index_value(mt,'AttachParent')==ri and not index_value(rt,'AttachParent'),'Unsupported body attachment')
    refs=[]
    for k in ('SkeletalMesh','SkinnedAsset'):
        if k in mt:
            j=index_value(mt,k);require(j<0 and ref(j)['kind']=='SkeletalMesh' and pkg(j),'Invalid skeletal mesh reference');refs.append(pkg(j))
    require(len(set(refs))==1,'No unique explicit skeletal mesh')
    content=next((p for p in path.parents if p.name=='Content' and len(list(p.parent.glob('*.uproject')))==1),None);require(content is not None,'Blueprint must be inside original project Content')
    overrides=[]
    for j in array(mt,'OverrideMaterials'):
        require(j==0 or j<0 and ref(j)['kind'] in ('Material','MaterialInstanceConstant') and pkg(j),'Invalid class body material override');overrides.append(pkg(j) if j else '')
    package='/Game/'+path.relative_to(content).with_suffix('').as_posix()
    require(not m.get('package_name') or m['package_name']==package,'Character Blueprint package identity mismatch')
    return dict(overrides=overrides,name=cls['name'],source=package,mesh_package=refs[0],root_fields=character_fields(rt),mesh_fields=character_fields(mt),root_name=root['name'],mesh_name=mesh['name'],root_tags=rt,mesh_tags=mt,content=content)


def build_character_preview(path,collection=None,materials=False,partial=False,sockets=True):
    data=character_defaults(path)
    return build_character_data(data,collection,materials,partial,sockets)

def build_character_data(data,collection=None,materials=False,partial=False,sockets=True,allow_unresolved_slots=False,decoded_cache=None,allow_missing_sockets=False):
    import bpy,json
    from blueprint_placement import apply_fields
    from ue5_editor_mesh import read_skeletal,build_skeletal
    from project_session import new_ids,rollback_new
    content=data['content'];package=data['mesh_package'];require(package.startswith('/Game/'),'Unsupported skeletal mesh mount')
    source=(content/(package[6:]+'.uasset')).resolve();require(source.is_relative_to(content) and source.is_file(),'Missing original skeletal mesh '+package)
    if decoded_cache is None:decoded_cache={}
    if source not in decoded_cache:decoded_cache[source]=read_skeletal(source,allow_unresolved_slots=allow_unresolved_slots)
    decoded=decoded_cache[source];before=set(new_ids());collection=collection or bpy.context.collection
    try:
        obj,arm=build_skeletal(decoded,collection);anchor=bpy.data.objects.new(data['name'],None);collection.objects.link(anchor);anchor.empty_display_type='PLAIN_AXES';anchor.empty_display_size=.2;apply_fields(anchor,data['root_fields']);arm.parent=anchor;apply_fields(arm,data['mesh_fields']);anchor['UE_blueprint_package']=data['source'];anchor['UE_native_defaults_unverified']=True;anchor['UE_preview_only']=True;obj['UE_mesh_package']=package
        if data.get('overrides'):
            obj['UE_material_override_packages']=json.dumps(data['overrides'])
            if decoded.get('unresolved_material_groups'):obj['UE_unresolved_override_slots']=True
            for i,pkg in enumerate(data['overrides'] if not decoded.get('unresolved_material_groups') else []):
                require(i<len(obj.material_slots),'Invalid override slot index')
                if pkg:
                    mat=bpy.data.materials.new(pkg.rsplit('/',1)[-1]);mat['UE_material_package']=pkg;mat['UE_unresolved_material']=True;obj.material_slots[i].link='OBJECT';obj.material_slots[i].material=mat
        if materials:
            from ue5_editor_material import bind_slots
            bind_slots([obj],content,partial)
        if sockets:
            from ue5_editor_skeleton import read_skeleton
            from native_sockets import create_socket_anchors
            sp=decoded['skeleton_package'];require(sp.startswith('/Game/'),'Unsupported skeleton mount');p=(content/(sp[6:]+'.uasset')).resolve();require(p.is_relative_to(content),'Reference skeleton escapes Content')
            if not p.is_file() and allow_missing_sockets:
                arm['UE_socket_status']='missing original reference skeleton: '+sp;return anchor,obj,arm
            require(p.is_file(),'Missing original reference skeleton')
            sk=read_skeleton(p);require(sk['skeleton_package']==sp,'Skeleton identity mismatch');records=sk['sockets'];available=[r for r in records if arm.data.bones.get(r['bone']) is not None]
            arm['UE_socket_definitions']=json.dumps(records);arm['UE_omitted_socket_names']=json.dumps([r['name'] for r in records if r not in available])
            if available:create_socket_anchors(arm,available,collection)
        return anchor,obj,arm
    except Exception:
        rollback_new(before);raise
