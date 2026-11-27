"""Native UE5.6 editor MeshDescription fixed-extent attribute channels.
Reads local editor payload identity, never scans for geometry bytes.
"""
import math
import struct
from pathlib import Path
from mesh_description import Reader
from skeleton_native import Reader as PackageReader
from ue5_blueprint import read_tables, require
from ue5_editor_payload import read_trailer,extract_payload
from ue5_editor_tags import export_tags


def decode_mesh_description(raw):
    r=Reader(raw); groups={}; kinds={0:'4f',1:'3f',2:'2f',3:'f',4:'i',5:'B'}
    for _ in range(r.count(32)):
        name=r.string(); require(name not in groups,'Duplicate mesh element container')
        channels=[]
        for _ in range(r.count(16)):
            n=r.count(); masks=struct.unpack('<'+'I'*((n+31)//32),r.take(4*((n+31)//32)))
            require(not (n%32 and masks[-1]>>(n%32)),'Invalid element allocation mask')
            live=[i for i in range(n) if masks[i//32]&(1<<(i%32))]
            free=r.count(); require(free==0,'Sparse free-list layout not validated')
            require(r.count()==n,'Element attribute count mismatch')
            attrs={}
            for _ in range(r.count(128)):
                key=r.string().strip();kind,extent,count=r.integer(),r.count(64),r.count()
                require(key not in attrs and count==n,'Invalid mesh attribute header')
                if extent==0:
                    if key!='SkinWeights' or kind!=4:raise NotImplementedError('Unknown variable attribute '+key)
                    arrays=[]
                    for _ in range(r.count(16)):
                        require(r.count()==(count+255)//256,'Skin weight chunk count mismatch');values=[]
                        for start in range(0,count,256):
                            k=r.count(256*64);packed=struct.unpack('<'+str(k)+'I',r.take(4*k));nchunk=r.count(256)
                            require(nchunk==min(256,count-start),'Invalid weight chunk size')
                            offsets,sizes,caps=[struct.unpack('<'+str(nchunk)+'i',r.take(4*nchunk)) for _ in range(3)]
                            at=0
                            for off,sz,cap in zip(offsets,sizes,caps):
                                require(off==at and 0<=sz<=cap<=64 and off+cap<=k,'Invalid weight chunk allocation')
                                values.append(packed[off:off+sz]);at+=cap
                            require(at==k,'Unaccounted skin weight chunk')
                        require(r.count()==count,'Skin weight count mismatch');arrays.append(values)
                    require(r.integer()==0 and r.integer()==0,'Unsupported skin weight default');flags=r.integer();attrs[key]=(kind,extent,arrays,flags);continue
                if kind not in (*kinds,6,7):raise NotImplementedError('Unknown mesh attribute '+key)
                arrays=[]
                for _ in range(r.count(16)):
                    require(r.integer()==extent,'Attribute extent mismatch')
                    if kind==7:
                        require(key=='Pose' and extent==1 and r.count()==count,'Invalid transform attribute array');vals=list(struct.iter_unpack('<10d',r.take(80*count)))
                    elif kind==6:
                        require(r.count()==count*extent,'Invalid name array count')
                        vals=[r.string() for _ in range(count*extent)]
                    else:
                        fmt='<'+kinds[kind];width=struct.calcsize(fmt)
                        require(r.integer()==width and r.count()==count*extent,'Invalid fixed attribute array extent')
                        vals=list(struct.iter_unpack(fmt,r.take(width*count*extent)))
                        if kinds[kind].endswith('f'):require(all(math.isfinite(v) for row in vals for v in row),'Non-finite mesh attribute')
                    arrays.append(vals if extent==1 else [tuple(vals[i:i+extent]) for i in range(0,len(vals),extent)])
                if kind==7:r.take(80)
                elif kind==6:r.string()
                else:r.take(4 if kind==5 else struct.calcsize('<'+kinds[kind]))
                flags=r.integer(); attrs[key]=(kind,extent,arrays,flags)
            channels.append((live,attrs))
        groups[name]=channels
    require(r.pos==len(raw),'Unexpected MeshDescription tail')
    def channel(name):
        require(name in groups and len(groups[name])==1,'Missing or ambiguous element '+name); return groups[name][0]
    def attr(group,name,kind,extent=1,channels=None,optional=False):
        _,attrs=channel(group)
        if optional and name not in attrs:return None
        require(name in attrs,'Missing attribute '+name);k,e,a,_=attrs[name]
        require(k==kind and e==extent and a and (channels is None or len(a)==channels),'Incorrect attribute type '+name);return a
    v,_=channel('Vertices');vi,_=channel('VertexInstances');t,_=channel('Triangles');pg,_=channel('PolygonGroups');p,_=channel('Polygons');ed,_=channel('Edges')
    pos=attr('Vertices','Position',1,channels=1)[0]
    inds=attr('VertexInstances','VertexIndex',4,channels=1)[0]
    corners=attr('Triangles','VertexInstanceIndex',4,3,1)[0]
    tg=attr('Triangles','PolygonGroupIndex',4,channels=1)[0]
    tp=attr('Triangles','PolygonIndex',4,channels=1)[0]
    pgroup=attr('Polygons','PolygonGroupIndex',4,channels=1)[0]
    edges=attr('Edges','VertexIndex',4,2,1)[0]
    slots=attr('PolygonGroups','ImportedMaterialSlotName',6,channels=1)[0]
    vset=set(v);viset=set(vi);pset=set(p);pgset=set(pg)
    require(v and vi and t and pg,'Empty source mesh')
    instances={i:inds[i][0] for i in vi}; require(all(i in vset for i in instances.values()),'Invalid vertex instance index')
    edge_map={i:tuple(v[0] for v in edges[i]) for i in ed};require(all(a!=b and a in vset and b in vset for a,b in edge_map.values()),'Invalid edge references')
    triangles=[]
    for i in t:
        f=tuple(c[0] for c in corners[i]);g=tg[i][0];poly=tp[i][0]
        require(poly in pset and g in pgset and pgroup[poly][0]==g and all(c in viset for c in f) and len({instances[c] for c in f})==3,'Invalid source triangle reference')
        triangles.append((g,f))
    normal=attr('VertexInstances','Normal',1,channels=1)[0]
    uv=attr('VertexInstances','TextureCoordinate',2,optional=True) or []
    def optional(key,kind):
        a=attr('VertexInstances',key,kind,channels=1,optional=True);return a[0] if a else None
    hard=attr('Edges','IsHard',5,channels=1,optional=True)
    data=dict(vertices={i:pos[i] for i in v},instances=instances,triangles=triangles,normals=normal,uvs=uv,colors=optional('Color',0),tangents=optional('Tangent',1),signs=optional('BinormalSign',3),slots={i:slots[i] for i in pg},edges=edge_map,hard_edges={i:bool(hard[0][i][0]) for i in ed} if hard else None)
    if 'BonesElementName' in groups:
        bone_ids,_=channel('BonesElementName');require(bone_ids==list(range(len(bone_ids))) and 0<len(bone_ids)<=8192,'Invalid bone element IDs')
        names=attr('BonesElementName','Name',6,channels=1)[0];parents=attr('BonesElementName','ParentIndex',4,channels=1)[0];poses=attr('BonesElementName','Pose',7,channels=1)[0]
        bones=[]
        for i in bone_ids:
            parent=parents[i][0];q,t,s=poses[i][:4],poses[i][4:7],poses[i][7:]
            require(parent in ([-1] if i==0 else range(i)) and all(math.isfinite(x) for x in q+t+s) and abs(sum(x*x for x in q)-1)<.001 and min(s)>0,'Invalid source bone pose')
            bones.append(dict(name=names[i],parent=parent,rotation=q,translation=t,scale=s))
        require(len({b['name'].casefold() for b in bones})==len(bones),'Duplicate bone names')
        values=attr('Vertices','SkinWeights',4,0,1)[0];weights={}
        for i in v:
            ws=[(x>>16,x&65535) for x in values[i]]
            require(ws and len(ws)==len(dict(ws)) and all(0<=b<len(bones) and w>0 for b,w in ws) and sum(w for b,w in ws)==65535,'Invalid source skin weights')
            weights[i]=dict(ws)
        data.update(bones=bones,weights=weights)
    return data


def read_static(path,decoder=None):
    meta,raw,imports,exports,ref,package=read_tables(path);names=meta['names']
    require(meta['ue5'] in (1016,1017),'UE5.6 editor static profile required')
    roots=[(i,e) for i,e in enumerate(exports,1) if e['kind']=='StaticMesh' and not e['outer']];require(len(roots)==1,'Expected one root StaticMesh')
    idx,e=roots[0]; tags=export_tags(raw,e,names)
    source=tags.get('SourceModels');require(source and source['type']==['ArrayProperty','StructProperty','StaticMeshSourceModel','/Script/Engine'] and len(source['data'])>=4,'Missing source models')
    count=struct.unpack_from('<i',source['data'])[0];require(count==1,'Only one editor source LOD validated')
    bulk=[v for v in exports if v['outer']==idx and v['kind']=='StaticMeshDescriptionBulkData' and v['name']=='StaticMeshDescriptionBulkData_0']; require(len(bulk)==1,'Missing explicit LOD0 bulk export')
    d=bulk[0];tail=raw[d['offset']+d['script_end']:d['offset']+d['size']]
    require(len(tail)==72 and tail[:8]==b'\0\0\0\0\0\x02\0\0','Unsupported editor MeshDescription bulk reference')
    digest=tail[24:44].hex(); size=struct.unpack_from('<Q',tail,44)[0]
    trailer=read_trailer(raw,max(x['offset']+x['size'] for x in exports)); payload,info=extract_payload(raw,trailer,digest,size,decoder)
    data=decode_mesh_description(payload)
    # Native tail: zero object GUID flag, strip flags, cooked marker, body/nav refs,
    # lighting GUID, socket array, SpeedTree flag, then FStaticMaterial records.
    r=PackageReader(raw[e['offset']+e['script_end']:e['offset']+e['size']]);require(r.i()==0 and r.take(2)==bytes(2) and r.i()==0,'Not unstripped editor static mesh')
    for _ in range(2):require(0<=r.i()<=len(exports),'Unsupported body/nav reference')
    r.take(16);n=r.count(1024)
    sockets=[r.i() for _ in range(n)];require(all(0<i<=len(exports) and ref(i)['kind']=='StaticMeshSocket' for i in sockets),'Invalid static sockets')
    require(r.i()==0,'SpeedTree editor static unsupported'); n=r.count(4096);materials=[]
    for _ in range(n):
        mi=r.i();display,slot=r.name(names),r.name(names); flags=r.unpack('ii');density=r.unpack('4f')
        require(all(v in (0,1) for v in flags) and all(math.isfinite(x) for x in density),'Invalid material metadata')
        require(mi==0 or mi<0 and ref(mi)['kind'] in ('Material','MaterialInstanceConstant') and package(mi),'Invalid static material package')
        materials.append((slot,package(mi) if mi else ''))
    require(r.take(4)==bytes(4) and r.pos==len(r.data),'Unexpected static native trailer')
    mapping={}
    for group,slot in data['slots'].items():
        matches=[i for i,m in enumerate(materials) if m[0]==slot]
        if len(matches)==1: mapping[group]=matches[0]
        elif len(materials)==len(data['slots'])==1: mapping[group]=0
        else: raise ValueError('Ambiguous imported material slot '+slot)
    data['group_to_slot']=mapping
    data.update(name=e['name'],source=str(path),materials=materials,source_hash=info['hash'],raw_size=info['raw_size'])
    return data


def build_static(data):
    import bpy,json
    from types import SimpleNamespace
    from umesh import BuildMeshDescription
    fake=SimpleNamespace(object_name=data['name'],asset=SimpleNamespace(f=SimpleNamespace(byte_stream=SimpleNamespace(name=data['source']))))
    mesh=BuildMeshDescription(fake,data); created=[]
    try:
        for slot,pkg in data['materials']:
            mat=bpy.data.materials.new(slot);created.append(mat);mat['UE_unresolved_material']=True
            if pkg:mat['UE_material_package']=pkg
            mesh.materials.append(mat)
        group_to_slot=data['group_to_slot']
        for p,(g,_) in zip(mesh.polygons,data['triangles']):p.material_index=group_to_slot[g]
        mesh['UE_material_bindings']=json.dumps(data['materials']);mesh['UE_source_format']='UE5 editor FMeshDescription';mesh['UE_source_payload_blake3']=data['source_hash'];mesh['UE_geometry_scope']='editor_source_LOD0'
        return mesh
    except Exception:
        bpy.data.meshes.remove(mesh)
        for mat in created:
            if not mat.users:bpy.data.materials.remove(mat)
        raise


def read_skeletal(path,decoder=None):
    """Recover explicit editor LOD0 source, including original skin weights."""
    meta,raw,imports,exports,ref,package=read_tables(path);names=meta['names']
    require(meta['ue5'] in (1016,1017),'UE5.6 editor skeletal profile required')
    roots=[(i,e) for i,e in enumerate(exports,1) if e['kind']=='SkeletalMesh' and not e['outer']];require(len(roots)==1,'Expected one root SkeletalMesh')
    idx,e=roots[0];tags=export_tags(raw,e,names)
    source=tags.get('SourceModels');require(source and source['type'][0]=='ArrayProperty' and len(source['data'])>=4,'Missing skeletal source models')
    count=struct.unpack_from('<i',source['data'])[0];require(1<=count<=16,'Invalid skeletal source model count')
    bulk=[v for v in exports if v['outer']==idx and v['kind']=='SkeletalMeshDescriptionBulkData' and v['name']=='SkeletalMeshDescriptionBulkData_0'];require(len(bulk)==1,'Missing explicit skeletal LOD0 bulk export')
    d=bulk[0];tail=raw[d['offset']+d['script_end']:d['offset']+d['size']]
    require(len(tail)==72 and tail[:8]==b'\0\0\0\0\0\x02\0\0','Unsupported skeletal bulk reference')
    digest=tail[24:44].hex();size=struct.unpack_from('<Q',tail,44)[0]
    payload,info=extract_payload(raw,read_trailer(raw,max(x['offset']+x['size'] for x in exports)),digest,size,decoder)
    data=decode_mesh_description(payload);require('bones' in data,'Missing source skin attributes')
    r=PackageReader(raw[e['offset']+e['script_end']:e['offset']+e['size']]);require(r.i()==0 and r.take(2)==bytes(2),'Unsupported skeletal native prefix')
    bounds=r.unpack('7d');require(all(math.isfinite(x) for x in bounds),'Non-finite skeletal bounds')
    materials=[]
    for _ in range(r.count(4096)):
        mi=r.i();display=r.name(names);require(r.i()==1,'Missing imported skeletal material name');slot=r.name(names)
        flags=r.unpack('ii');density=r.unpack('4f');require(all(v in (0,1) for v in flags) and all(math.isfinite(v) for v in density) and r.i()==0,'Invalid skeletal material metadata')
        require(mi==0 or mi<0 and ref(mi)['kind'] in ('Material','MaterialInstanceConstant') and package(mi),'Invalid skeletal material package')
        materials.append((slot,package(mi) if mi else ''))
    bones=data['bones'];require(r.count(8192)==len(bones),'Native skeletal bone count mismatch')
    for b in bones:
        require(r.name(names)==b['name'] and r.i()==b['parent'],'Native and source bone hierarchy differ');r.string()
    require(r.count(8192)==len(bones),'Native reference pose count mismatch')
    for b in bones:
        native=r.unpack('10d');source=b['rotation']+b['translation']+b['scale'];require(max(abs(x-y) for x,y in zip(native,source))<1e-5,'Native and source reference poses differ')
    mapping={}
    for group,slot in data['slots'].items():
        matches=[i for i,m in enumerate(materials) if m[0]==slot];require(len(matches)==1,'Ambiguous skeletal material slot '+slot);mapping[group]=matches[0]
    sk=tags.get('Skeleton');require(sk and sk['type']==['ObjectProperty'] and len(sk['data'])==4,'Missing skeletal asset reference')
    si=struct.unpack('<i',sk['data'])[0];require(si<0 and ref(si)['kind']=='Skeleton' and package(si),'Invalid skeleton package')
    data.update(name=e['name'],source=str(path),materials=materials,group_to_slot=mapping,source_hash=info['hash'],raw_size=info['raw_size'],skeleton_package=package(si),declared_lods=count)
    return data


def build_skeletal(data,collection=None):
    import bpy
    from skeleton_native import build_armature
    collection=collection or bpy.context.collection
    mesh=build_static(data);arm=None;obj=None
    try:
        require(all(max(abs(x-1) for x in b['scale'])<1e-5 for b in data['bones']),'Non-unit editor bone scale not supported')
        arm=build_armature(data['name']+'_Rig',data['bones'],collection)
        obj=bpy.data.objects.new(data['name'],mesh);collection.objects.link(obj);obj.parent=arm
        groups=[obj.vertex_groups.new(name=b['name']) for b in data['bones']]
        for i,v in enumerate(sorted(data['vertices'])):
            for j,w in data['weights'][v].items():groups[j].add([i],w/65535,'REPLACE')
        mod=obj.modifiers.new('UE skinning','ARMATURE');mod.object=arm;mod.use_deform_preserve_volume=False
        mesh['UE_source_lod_index']=0;mesh['UE_declared_source_models']=data['declared_lods'];mesh['UE_source_format']='UE5 editor skinned FMeshDescription'
        arm['UE_skeleton_package']=data['skeleton_package'];arm['UE_skeleton_status']='editor_source_skinning';return obj,arm
    except Exception:
        if obj:bpy.data.objects.remove(obj,do_unlink=True)
        if arm:
            a=arm.data;bpy.data.objects.remove(arm,do_unlink=True);bpy.data.armatures.remove(a)
        mats=list(mesh.materials);bpy.data.meshes.remove(mesh)
        for mat in mats:
            if not mat.users:bpy.data.materials.remove(mat)
        raise
