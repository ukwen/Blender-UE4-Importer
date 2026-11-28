"""Bounded UE4.27 editor source LOD0 skeletal mesh reader."""
import math
from pathlib import Path
from skeleton_native import Reader
from skeletal_mesh_native import require, assemble


def read_editor_mesh(path):
    import struct
    from package_records import read_editor522, root_export, classic_custom_versions
    from ue4_property_records import read_tagged_properties
    _, raw, table = read_editor522(path)
    versions = {'004a8ad7974658e8b519a8bab4467d48':18,
                'ed68b0e4e94294f40bda31a241bb462e':40,
                '86f879551f4c3a937b08ba832fb96163':2,
                '9f8bf812fc4a75880cd97ca629bd3a38':44}
    actual = classic_custom_versions(raw)
    require(all(actual.get(bytes.fromhex(k)) == v for k,v in versions.items()), 'Unsupported skeletal custom versions')
    e = root_export(table, 'SkeletalMesh')
    names = table.names
    r = Reader(raw[e.offset:e.offset+e.size])
    tags, kinds = read_tagged_properties(r, names)
    tag = tags.get('Skeleton', b'')
    require(kinds.get('Skeleton') == ('ObjectProperty',None) and len(tag)==4, 'Invalid skeleton reference')
    ref = struct.unpack('<i',tag)[0]
    require(ref < 0 and table.reference(ref).kind == 'Skeleton', 'Invalid skeleton class')
    skeleton_package = table.package(ref)
    require(bool(skeleton_package), 'Unresolved skeleton package')
    # Preserve native-tail-relative offsets used by the existing geometry contract.
    r = Reader(r.data[r.pos:])
    require(r.unpack('iBB')==(0,0,0),'Unsupported editor skeletal header')
    require(all(math.isfinite(x) for x in r.unpack('7f')),'Invalid bounds')
    materials=[]
    for _ in range(r.count(4096)):
        ref=r.i(); slot=r.name(names); require(r.i()==1,'Missing editor slot name'); r.name(names)
        flags=r.unpack('ii'); require(all(x in (0,1) for x in flags),'Invalid UV channel flags'); require(all(math.isfinite(x) for x in r.unpack('4f')),'Invalid UV density')
        materials.append((slot,table.package(ref) if ref else ''))
    n=r.count(8192); require(n>0,'Empty reference skeleton'); bones=[]; seen=set()
    for i in range(n):
        name,parent=r.name(names),r.i(); r.string()
        require(name.casefold() not in seen and len(name.encode())<=63 and parent in ([-1] if i==0 else range(i)),'Invalid reference bone'); seen.add(name.casefold()); bones.append(dict(name=name,parent=parent))
    require(r.i()==n,'Reference pose count mismatch')
    for b in bones:
        q,t,s=r.unpack('4f'),r.unpack('3f'),r.unpack('3f')
        require(all(math.isfinite(v) for v in q+t+s) and abs(sum(v*v for v in q)-1)<.001 and min(s)>0,'Invalid reference pose')
        b.update(rotation=q,translation=t,scale=s)
    require(r.i()==n,'Bone map count mismatch'); seen=set()
    for _ in range(n):
        name,i=r.name(names),r.i(); require(0<=i<n and i not in seen and name==bones[i]['name'],'Invalid bone map'); seen.add(i)
    require(r.unpack('H')==(0,),'Unsupported imported model flags'); lod_count=r.count(64); require(lod_count>=1,'No source LODs')
    require(r.unpack('H')==(0,),'Unsupported LOD flags'); section_count=r.count(4096); require(section_count>0,'No sections')
    positions=[]; normals=[]; tangents=[]; signs=[]; uvs=[]; weights=[]; colors=[]; sections=[]
    for _ in range(section_count):
        strip,mat,start,tri,recompute,mask,shadow,base=r.unpack('HHIIIBII'); require(strip==0 and mat<len(materials) and recompute in (0,1) and mask<=4 and shadow in (0,1) and base==len(positions),'Unsupported editor section header')
        count=r.count(1000000); require(0<count and base+count<=1000000,'Invalid section vertex count')
        for i in range(count):
            v=r.unpack('21f4B12H12B'); require(all(math.isfinite(x) for x in v[:21]),'Nonfinite vertex')
            positions.append(v[:3]); tangents.append(v[3:6]); normals.append(v[9:12]); signs.append(v[12]); uvs.append(v[13:21]); colors.append((v[23],v[22],v[21],v[24]))
            require(max(v[25:37])<256,'Wide palette index unsupported'); weights.append(bytes(v[25:49]))
        require(r.i()==0,'Unsupported section cloth/extra data'); palette=r.unpack(str(r.count(256))+'H'); vc,maximum,cloth=r.unpack('iii')
        require(vc==count and 1<=maximum<=12 and cloth==0 and palette and len(set(palette))==len(palette) and max(palette)<n,'Invalid section palette')
        require(r.take(22)==b'\xff\xff'+bytes(16)+b'\xff'*4,'Cloth section unsupported')
        seen=set()
        for i in range(r.count(count)):
            k=r.i(); require(0<=k<count and k not in seen,'Invalid overlap vertex'); seen.add(k)
            overlaps=r.unpack(str(r.count(count))+'i'); require(all(0<=x<count for x in overlaps),'Invalid overlap reference')
        disabled,reduce,original,chunk=r.unpack('4i'); require(disabled==0 and reduce>=-1 and original>=0 and chunk==-1,'Unsupported section flags')
        sections.append((mat,start,tri,base,count,palette,maximum))
    # 4.27 serialized section user settings (key and 41-byte fixed non-cloth record).
    user_count=r.count(4096); require(user_count==section_count,'Section user record count mismatch')
    seen=set()
    for _ in range(user_count):
        key=r.i(); require(0<=key<section_count and key not in seen,'Invalid section user key'); seen.add(key); r.take(41)
    idx=r.unpack(str(r.count(12000000))+'I'); active=r.unpack(str(r.count(8192))+'H'); legacy,vc=r.unpack('ii'); required=r.unpack(str(r.count(8192))+'H')
    require(vc==len(positions) and all(i<n for i in active+required),'Invalid source vertex or bone count')
    data=assemble(r,e.name,bones,materials,sections,idx,positions,normals,tangents,signs,uvs,weights,None,'editor_4.27')
    # Blender rejects duplicate polygon vertex sets. Only identical ordered
    # triangles with identical material assignments may be collapsed.
    faces=[]; slots=[]; source_faces=[]; seen={}; duplicates=[]
    for i,(face,slot) in enumerate(zip(data['faces'],data['slots'])):
        key=tuple(sorted(face))
        if key in seen:
            require(seen[key]==(face,slot),'Conflicting duplicate source triangle'); duplicates.append(i); continue
        seen[key]=(face,slot); faces.append(face); slots.append(slot); source_faces.append(i)
    data.update(skeleton_package=skeleton_package,colors=colors,lod_count=lod_count,faces=faces,slots=slots,source_faces=source_faces,duplicate_faces=duplicates)
    return data
