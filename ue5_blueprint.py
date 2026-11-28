"""Read-only UE5 1012–1018 tagged editor package tables and selected Blueprint fields.
Layout reference: UAssetAPI Import.cs, Export.cs, MainSerializer.cs, FPropertyTypeName.cs.
Does not execute Blueprint code or reconstruct inherited transforms.
"""
from pathlib import Path
from package_inspector import inspect_package
from skeleton_native import Reader


def require(ok,message):
    if not ok: raise ValueError(message)


def read_tables(path):
    from import_workflow import cached_tables
    return cached_tables(path, _read_tables)


def _read_tables(path):
    from package_records import compatibility_tables
    meta, raw, imports, exports, ref, package = compatibility_tables(path)
    require(meta['ue5'] is not None and 1012 <= meta['ue5'] <= 1018, 'Expected UE5 1012–1018 tagged editor package')
    return meta, raw, imports, exports, ref, package


def read_properties(raw,e,names):
    """Read only bounded tagged script data, skipping uninterpreted payloads by size."""
    r=Reader(raw[e['offset']+e['script_start']:e['offset']+e['script_end']]); out={}
    require(r.unpack("B")[0]==0,"Unsupported class serialization control")
    while True:
        key=r.name(names)
        if key=='None':
            require(r.pos==len(r.data),'Unexpected bytes after script property terminator'); return out
        nodes=[]; remaining=1
        while remaining:
            typ,n=r.name(names),r.count(64); nodes.append(typ); remaining+=n-1
            require(len(nodes)+remaining<=128,'Oversized property type tree')
        size=r.i(); flags=r.unpack('B')[0]
        require(size>=0 and not flags&~0x3f,'Invalid property tag')
        idx=r.i() if flags&1 else 0
        if flags&2: r.take(16)
        if flags&4:
            ext=r.unpack('B')[0]; require(not ext&~2,'Unsupported property extension')
            if ext&2: r.take(5)
        payload=r.take(size)
        require(idx==0 and key not in out,'Repeated property unsupported')
        typ=nodes[0]; p=Reader(payload); value=None
        if typ=='ObjectProperty' and size==4 and not flags&0x28: value=p.i()
        elif typ=='NameProperty' and size==8 and not flags&0x28: value=p.name(names)
        elif typ=='ArrayProperty' and nodes[1:]==['ObjectProperty'] and not flags&0x28:
            count=p.count(100000); value=[p.i() for _ in range(count)]; require(p.pos==len(payload),'Invalid object array')
        out[key]=(typ,value)


def inspect_blueprint(path):
    meta,raw,imports,exports,ref,package=read_tables(path); names=meta['names']
    if meta['ue5']==1018:
        from ue5_editor_blueprint import inspect_class
        return inspect_class(path)
    require(meta['ue5']==1012,'Unsupported Blueprint property profile')
    classes=[(i,e) for i,e in enumerate(exports,1) if e['outer']==0 and e['kind']=='BlueprintGeneratedClass']
    require(len(classes)==1,'Expected one generated class'); ci,cls=classes[0]
    cdo=[(i,e) for i,e in enumerate(exports,1) if e['class_index']==ci and e['outer']==0 and e['name']=='Default__'+cls['name']]; require(len(cdo)==1,'Expected one CDO'); di,default=cdo[0]
    scripts=[(i,e) for i,e in enumerate(exports,1) if e['outer']==ci and e['kind']=='SimpleConstructionScript']; require(len(scripts)<=1,'Ambiguous SCS')
    components=[]
    def add(index,name,origin,socket=None,parent=None):
        e=ref(index); require(index>0 and e['outer'] in (ci,di),'Invalid component template')
        if e['kind'] not in ('StaticMeshComponent','SkeletalMeshComponent','SceneComponent','CapsuleComponent','InstancedStaticMeshComponent','HierarchicalInstancedStaticMeshComponent'): return
        p=read_properties(raw,e,names); keys=('SkinnedAsset','SkeletalMesh') if e['kind']=='SkeletalMeshComponent' else ('StaticMesh',)
        fields=[(k,p[k][1]) for k in keys if k in p]
        require(all(type(v) is int for k,v in fields),'Unsupported mesh reference field')
        packages={package(v) for k,v in fields if v}; require(len(packages)<=1 and '' not in packages,'Conflicting mesh refs')
        from blueprint_placement import props5,FIELDS
        transform_fields=props5(raw,e,names) if origin=='SCS' else {}
        components.append(dict(fields={k:transform_fields[k] for k in FIELDS if k in transform_fields},variable=name,template=e['name'],kind=e['kind'],origin=origin,package=next(iter(packages),''),socket=socket or '',parent=parent or '',explicit=bool(fields)))
    for name,(typ,value) in read_properties(raw,default,names).items():
        if typ=='ObjectProperty' and isinstance(value,int) and value>0 and ref(value)['outer']==di: add(value,name,'CDO')
    for si,script in scripts:
        props=read_properties(raw,script,names)
        for index in props.get('AllNodes',(None,[]))[1]:
            node=ref(index); require(index>0 and node['outer']==si and node['kind']=='SCS_Node','Invalid SCS node')
            p=read_properties(raw,node,names); val=lambda k:p.get(k,(None,None))[1]
            add(val('ComponentTemplate'),val('InternalVariableName'),'SCS',val('AttachToName'),val('ParentComponentOrVariableName'))
    dependencies=sorted({package(-i) for i,x in enumerate(imports,1) if x['kind'] in ('StaticMesh','SkeletalMesh') and package(-i)})
    si=cls['super_index']; parent=ref(si)
    require(si<0 and parent is not None,'Unsupported superclass reference')
    # Preserve direct parent class and native /Script package identity separately.
    parent_pkg=package(si)
    if not parent_pkg:
        seen=set(); idx=si
        while idx<0:
            require(idx not in seen,'Superclass import cycle'); seen.add(idx); item=ref(idx)
            if item['kind']=='Package' and item['name'].startswith('/Script/'):
                parent_pkg=item['name']; break
            idx=item['outer']
    return dict(version=1012,generated_class=cls['name'],parent_blueprint=parent_pkg,parent_class=parent['name'],components=components,mesh_dependencies=dependencies)
