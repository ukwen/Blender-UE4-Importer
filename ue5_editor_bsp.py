"""Bounded UE5.6 saved compiled BSP render-buffer profile.
Read original Model/ModelComponent arrays, not recomputed brush Booleans.
Only inline PersistentLevel, zero surface flags, exact component memberships.
"""
import hashlib,json,math,struct
from pathlib import Path
from collections import Counter
from skeleton_native import Reader
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_editor_brushes import native_tail,dot,sub,cross


def bulk(r,fmt,limit=2_000_000):
    require(r.i()==struct.calcsize('<'+fmt),'Unsupported BSP bulk stride')
    n=r.count(limit)
    return [r.unpack(fmt) for _ in range(n)]


def decode_model(data):
    r=Reader(data)
    require(r.take(62)==bytes(62),'Unsupported compiled BSP bounds prefix')
    vectors=bulk(r,'3f');points=bulk(r,'3f');nodes=bulk(r,'4fiiiHHiiiii4Bii',65536)
    surfaces=[r.unpack('8i5fi') for _ in range(r.count(65536))]
    pool=bulk(r,'ii4f');shared,polys=r.unpack('ii');require(shared>=0 and polys>0,'Invalid BSP shared sides/Polys')
    bulk(r,'i');bulk(r,'i') # serialized leaf hulls/leaves, not render geometry
    outside,linked,unique,n=r.unpack('4i');require((outside,linked)==(1,0) and unique==len(points) and 0<n<=2_000_000,'Unsupported BSP render buffer header')
    render=[r.unpack('14f') for _ in range(n)]
    tail=r.take(56);require(r.pos==len(data),'Unexpected compiled BSP trailer')
    require(all(math.isfinite(v) for row in [*vectors,*points,*render] for v in row),'Nonfinite BSP values')
    faces={};used=set()
    for i,node in enumerate(nodes):
        start,si,rv,ci,cn=node[4:9];count=node[-4]
        require(0<=si<len(surfaces),'Invalid BSP surface index')
        if not count:continue
        require(3<=count<=64 and 0<=start<=len(pool)-count and 0<=rv<=len(render)-count,'Invalid BSP polygon range')
        require(not any(node[-6:-4]) and node[-3]==0,'Unsupported BSP node flags')
        s=surfaces[si];require(s[1]==0,'Unsupported BSP surface flags')
        require(0<=s[2]<len(points) and all(0<=k<len(vectors) for k in s[3:6]),'Invalid BSP texture basis indices')
        normal=node[:3];require(all(math.isfinite(x) for x in (*node[:4],*s[8:13])) and abs(dot(normal,normal)-1)<1e-4 and max(abs(a-b) for a,b in zip(normal,s[8:11]))<1e-4,'Invalid BSP plane normal')
        rows=render[rv:rv+count];p=[v[:3] for v in rows]
        require(len(set(p))==count,'Repeated BSP polygon point')
        for j,row in enumerate(rows):
            v=pool[start+j];require(0<=v[0]<len(points) and row[:3]==points[v[0]] and row[12:14]==v[2:4],'BSP render vertex/pool mismatch')
            require(max(abs(a-b) for a,b in zip(row[6:9],normal))<1e-4,'BSP render normal mismatch')
            require(rv+j not in used,'Overlapping BSP render vertex span');used.add(rv+j)
        extent=max(1.,max(math.sqrt(dot(sub(x,p[0]),sub(x,p[0]))) for x in p))
        require(max(abs(dot(sub(x,p[0]),normal)) for x in p)<=max(.003,extent*1e-5),'Nonplanar BSP polygon')
        area=tuple(sum(cross(sub(p[j],p[0]),sub(p[j+1],p[0]))[k] for j in range(1,count-1)) for k in range(3))
        require(dot(area,normal)>1e-6,'Invalid BSP winding/degenerate polygon')
        faces[i]=dict(node=i,surface=si,component=ci,component_node=cn,material=s[0],brush=s[7],normal=normal,vertices=p,uv=[v[10:12] for v in rows],lightmap_uv=[v[12:14] for v in rows],render_normals=[v[6:9] for v in rows])
    require(len(used)==len(render),'Unowned BSP render vertices')
    return dict(faces=faces,points=len(points),nodes=len(nodes),surfaces=len(surfaces),render_vertices=len(render),polys=polys,tail_sha256=hashlib.sha256(tail).hexdigest(),sha256=hashlib.sha256(data).hexdigest())


def decode_component(data,model_index,export_index,faces):
    r=Reader(data);require(r.take(8)==bytes(8) and r.i()==model_index,'Invalid BSP component model reference')
    elements=[];members=[]
    for _ in range(r.count(65536)):
        guid=r.take(16);owner,material,n=r.unpack('iii');require(owner==export_index and 0<n<=65536,'Invalid BSP element ownership/count')
        ids=r.unpack('H'*n)
        require(all(i in faces and faces[i]['material']==material for i in ids),'BSP element material/node mismatch')
        members.extend(ids);elements.append(dict(material=material,nodes=ids,guid=guid.hex()))
    ci=r.i();n=r.count(65536);ids=r.unpack('H'*n)
    require(r.pos==len(data) and len(set(ids))==len(ids)>0 and sorted(ids)==sorted(members),'Invalid BSP component node membership')
    require(all(faces[i]['component']==ci for i in ids),'BSP component index mismatch')
    return dict(component_index=ci,nodes=ids,elements=elements)


def records(content,path):
    content=Path(content).resolve();path=Path(path).resolve();require(path.is_relative_to(content),'Map outside Content')
    meta,raw,_,exports,ref,pkg=read_tables(path);require(meta['ue5'] in (1016,1017),'Unsupported compiled BSP editor version')
    require(any(e['kind']=='World' and not e['outer'] for e in exports),'Not a World package')
    levels=[i for i,e in enumerate(exports,1) if e['kind']=='Level' and e['name']=='PersistentLevel'];require(len(levels)==1,'Unsupported level ownership')
    level=levels[0];components=[(i,e) for i,e in enumerate(exports,1) if e['kind']=='ModelComponent' and e['outer']==level]
    if not components:return [],dict(status='no_inline_components',components=0,skipped=[])
    try:
        models={};rows=[];used={};indices=set()
        for i,e in components:
            tags=export_tags(raw,e,meta['names']);require(set(tags)<= {'ModelBodySetup'},'Unsupported BSP component properties')
            payload=native_tail(raw,e);require(len(payload)>=16,'Truncated BSP component');mi=struct.unpack_from('<i',payload,8)[0];require(0<mi<=len(exports),'Invalid compiled Model index')
            if mi not in models:
                mo=ref(mi);require(mo['kind']=='Model' and mo['outer']==level and not export_tags(raw,mo,meta['names']),'Invalid compiled Model ownership')
                models[mi]=decode_model(native_tail(raw,mo));used[mi]=set()
                pi=models[mi]['polys'];require(0<pi<=len(exports) and ref(pi)['kind']=='Polys' and ref(pi)['outer'] in (mi,level),'Invalid compiled Polys ownership')
            model=models[mi];c=decode_component(payload,mi,i,model['faces']);key=(mi,c['component_index']);require(key not in indices,'Duplicate BSP component index');indices.add(key)
            require(not used[mi].intersection(c['nodes']),'Duplicate BSP component polygon');used[mi].update(c['nodes'])
            fs=[]
            for node in c['nodes']:
                f=dict(model['faces'][node]);mat=f['material'];require(mat==0 or mat<0 and ref(mat)['kind'] in ('Material','MaterialInstanceConstant') and pkg(mat),'Invalid BSP material reference')
                f['material_package']=pkg(mat) if mat else '';fs.append(f)
            rows.append(dict(source=path.relative_to(content).as_posix(),actor=e['name'],model=mi,component=c['component_index'],faces=fs))
        require(all(used[k]==set(m['faces']) for k,m in models.items()),'Incomplete BSP component coverage')
        return rows,dict(status='reconstructed',components=len(rows),models=[dict(export=k,**{a:b for a,b in m.items() if a!='faces'}) for k,m in models.items()],skipped=[])
    except (ValueError,IndexError,struct.error,OverflowError) as exc:
        return [],dict(status='unsupported',components=0,skipped=[dict(detail=str(exc),source_components=len(components))])


def extend_bsp(content,path,parent,partial=False):
    import bpy
    from ue5_editor_material import bind_slots
    rows,report=records(content,path);counts=Counter();materials={};objs=[]
    if rows:
        collection=bpy.data.collections.new(Path(path).stem+' — compiled BSP');parent.children.link(collection)
        for r in rows:
            vertices=[];faces=[];uv=[];lightmap=[];normals=[];packages=[];point_indices={}
            for f in r['faces']:
                # Exchange X/Y and reverse winding. Preserve original corner UVs.
                face=[]
                for p,t,l,n in zip(reversed(f['vertices']),reversed(f['uv']),reversed(f['lightmap_uv']),reversed(f['render_normals'])):
                    if p not in point_indices:point_indices[p]=len(vertices);vertices.append((p[1]*.01,p[0]*.01,p[2]*.01))
                    face.append(point_indices[p]);uv.append((t[0],1-t[1]));lightmap.append((l[0],1-l[1]));normals.append((n[1],n[0],n[2]))
                faces.append(face);packages.append(f['material_package'])
            mesh=bpy.data.meshes.new(r['actor']+' compiled BSP');mesh.from_pydata(vertices,[],faces);mesh.update();require(not mesh.validate(),'Invalid BSP mesh')
            for name,values in [('UV0',uv),('LightmapUV',lightmap)]:
                layer=mesh.uv_layers.new(name=name)
                for loop,v in zip(layer.data,values):loop.uv=v
            mesh.uv_layers.active_index=0;mesh.uv_layers[0].active_render=True
            for poly in mesh.polygons:poly.use_smooth=True
            for edge in mesh.edges:edge.use_edge_sharp=True
            mesh.normals_split_custom_set(normals);mesh.update()
            source_normals=mesh.attributes.new('UE_saved_render_normal','FLOAT_VECTOR','CORNER')
            for item,n in zip(source_normals.data,normals):item.vector=n
            slots=list(dict.fromkeys(packages))
            for p in slots:
                if p not in materials:
                    mat=bpy.data.materials.new(p.rsplit('/',1)[-1] if p else 'BSP source material unspecified');mat['UE_material_package']=p;mat['UE_bsp_unresolved']=True;materials[p]=mat
                mesh.materials.append(materials[p])
            for poly,p in zip(mesh.polygons,packages):poly.material_index=slots.index(p)
            obj=bpy.data.objects.new(r['actor']+' — compiled BSP',mesh);collection.objects.link(obj);obj['UE_actor']=r['actor'];obj['UE_source_actor_package']=r['source'];obj['UE_compiled_bsp']=True;obj['UE_bsp_model_export']=r['model'];obj['UE_bsp_node_indices']=json.dumps([f['node'] for f in r['faces']]);obj['UE_bsp_surface_indices']=json.dumps([f['surface'] for f in r['faces']]);objs.append(obj)
            counts.update(vertices=len(vertices),faces=len(faces),corners=len(uv))
        material_report=bind_slots(objs,content,allow_partial=partial)
    else:material_report={}
    return dict(report,**{k:counts[k] for k in ('vertices','faces','corners')},material_report=material_report,unspecified_material_faces=sum(not f['material_package'] for r in rows for f in r['faces']),scope='Original saved compiled BSP render polygons and UVs; material dependencies may be absent; no runtime CSG, collision, lightmap baking or Unreal renderer parity')
