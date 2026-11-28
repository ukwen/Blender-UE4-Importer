"""Bounded UE4.14 editor skeletal source LOD0, not runtime GPU or cloth buffers."""
import math,uuid
from pathlib import Path
from skeleton_native import Reader
from skeletal_mesh_native import require,assemble

VERSIONS={'d78a4a00-4697-e858-b519-a8bab4467d48':5,'e4b068ed-42e9-f494-0bda-31a241bb462e':8,'5579f886-4c1f-933a-7b08-ba832fb96163':1,'12f88b9f-4afc-8875-0cd9-7ca629bd3a38':12}

def read_legacy_skeletal(path):
    from package_records import read_package, root_export, classic_custom_versions
    from ue4_property_records import read_records
    from classic_actor_layout import object_index
    from package_inspector import inspect_package
    path=Path(path); meta=inspect_package(path)
    if not (meta.get('status')=='tables_inspected' and meta.get('ue4')==508 and meta.get('legacy')==-7 and not meta['sidecars'] and not meta['flags']&0x80002000 and meta['size']<=128*1024*1024):
        raise NotImplementedError('Expected monolithic UE4.14 editor skeletal asset')
    meta,raw,table=read_package(path)
    versions=classic_custom_versions(raw)
    require(meta['licensee']==0 and all(versions.get(uuid.UUID(k).bytes_le)==v for k,v in VERSIONS.items()),'Unsupported UE4.14 skeletal custom versions')
    e=root_export(table,'SkeletalMesh'); end=e.offset+e.size
    r=Reader(raw[e.offset:end]); props={p.name:p for p in read_records(r,table.names) if p.index==0}
    skeleton=table.package(object_index(props,'Skeleton')); names=table.names
    r=Reader(r.take(len(r.data)-r.pos))
    require(r.unpack('iBB')==(0,0,0),'Unsupported legacy skeletal header');require(all(math.isfinite(v) for v in r.unpack('7f')),'Invalid bounds')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i();slot=r.name(names);r.name(names);flags=r.unpack('ii');density=r.unpack('4f')
        require(all(v in (0,1) for v in flags) and all(math.isfinite(v) for v in density),'Invalid material metadata');materials.append((slot,table.package(ref) if ref else ''))
    n=r.count(8192);require(n>0,'Empty skeleton');bones=[];seen=set()
    for i in range(n):
        name,parent=r.name(names),r.i();r.string();require(name.casefold() not in seen and len(name.encode())<=63 and parent in ([-1] if i==0 else range(i)),'Invalid reference bone');seen.add(name.casefold());bones.append(dict(name=name,parent=parent))
    require(r.i()==n,'Reference pose count mismatch')
    for b in bones:
        q,t,s=r.unpack('4f'),r.unpack('3f'),r.unpack('3f');require(all(math.isfinite(v) for v in q+t+s) and abs(sum(v*v for v in q)-1)<.001 and min(s)>0,'Invalid reference pose');b.update(rotation=q,translation=t,scale=s)
    require(r.i()==n,'Bone name map count mismatch');seen=set()
    for _ in range(n):
        name,i=r.name(names),r.i();require(0<=i<n and i not in seen and name==bones[i]['name'],'Invalid bone map');seen.add(i)
    lods=r.count(64);require(lods==1 and r.unpack('H')==(0,),'Only unstripped single source LOD supported');sections=[];positions=[];normals=[];tangents=[];signs=[];uvs=[];colors=[];weights=[]
    for _ in range(r.count(4096)):
        strip,mat,start,tri,sorting,disabled,cloth,cloth_enable,recompute,shadow,base=r.unpack('HHIIBihBiii')
        require(strip==sorting==disabled==0 and cloth==-1 and recompute in (0,1) and shadow in (0,1) and 0<=mat<len(materials) and base==len(positions),'Unsupported legacy section header')
        count=r.count(1000000);require(count>0 and base+count<=1000000,'Invalid source vertex count')
        for _ in range(count):
            v=r.unpack('3f12B8f4B16B');require(all(math.isfinite(x) for x in v[:3]+v[15:23]),'Nonfinite source vertex')
            positions.append(v[:3]);tangents.append(tuple(x/127.5-1 for x in v[3:6]));normals.append(tuple(x/127.5-1 for x in v[11:14]));signs.append(v[14]/127.5-1);uvs.append(v[15:23]);b,g,red,alpha=v[23:27];colors.append((red,g,b,alpha));weights.append(bytes(v[27:43]))
        palette=r.unpack(str(r.count(256))+'H');vc,maximum=r.unpack('ii');require(vc==count and 1<=maximum<=8 and palette and len(set(palette))==len(palette) and max(palette)<n,'Invalid source bone palette')
        require(r.unpack('iiihh')==(0,0,0,-1,-1),'Cloth data unsupported');sections.append((mat,start,tri,base,count,palette,maximum))
    require(sections and positions,'Empty source mesh');width,element=r.unpack('Bi');require(width==element and width in (2,4),'Invalid index width');idx=r.unpack(str(r.count(12000000))+('H' if width==2 else 'I'))
    active=r.unpack(str(r.count(8192))+'H');size,vc=r.unpack('ii');required=r.unpack(str(r.count(8192))+'H');require(vc==len(positions) and all(v<n for v in active+required),'Invalid LOD bone or vertex count')
    # RawPointIndices bulk header. Only uncompressed external-at-end source bulk.
    flags,count,size,offset=r.unpack('IIIq');require(flags==1 and count==vc and size==4*vc,'Unsupported raw point index bulk')
    offset+=meta['bulk_data_offset'];require(end<=offset and offset+size<=meta['size'],'Invalid raw point bulk extent')
    vertex_map=r.unpack(str(r.count(1000000))+'i');maximum=r.i();uv_count=r.i();require(len(vertex_map)==vc and all(0<=i<=maximum for i in vertex_map) and 1<=uv_count<=4,'Invalid import vertex map or UV count')
    uvs=[v[:2*uv_count] for v in uvs]
    data=assemble(r,e.name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,vertex_map,'editor_4.14')
    # Preserve duplicate triangles with duplicated vertices and identical skin/corner attributes.
    seen=set();faces=[];duplicates=[]
    for i,face in enumerate(data['faces']):
        key=tuple(sorted(face))
        if key in seen:
            duplicates.append(i);start=len(positions)
            for v in face:
                for arr in (positions,normals,tangents,signs,uvs,colors,data['weights']):arr.append(arr[v])
            vertex_map+=tuple(vertex_map[v] for v in face);face=(start,start+1,start+2)
        seen.add(key);faces.append(face)
    data.update(skeleton_package=skeleton,colors=colors,lod_count=lods,faces=faces,vertex_map=vertex_map,source_faces=list(range(len(faces))),duplicate_faces=[],split_source_faces=duplicates)
    return data
