"""Bounded tagged UE4.27 editor PhysicsAsset reader; no native simulation."""
import struct, math
from pathlib import Path

def require(ok,msg):
    if not ok: raise ValueError(msg)

class Tags:
    def __init__(self, data, names): self.data=memoryview(data); self.pos=0; self.names=names
    def take(self,n):
        require(0<=n<=len(self.data)-self.pos,'Physics tag exceeds payload'); p=self.pos; self.pos+=n; return self.data[p:self.pos]
    def unpack(self,fmt): return struct.unpack('<'+fmt,self.take(struct.calcsize('<'+fmt)))
    def i(self): return self.unpack('i')[0]
    def name(self):
        i,n=self.unpack('ii'); require(0<=i<len(self.names) and 0<=n<1000000,'Invalid FName'); return self.names[i]+('_'+str(n-1) if n else '')
    def guid(self):
        f=self.unpack('B')[0]; require(f in (0,1),'Invalid property GUID flag'); self.take(16 if f else 0)
    def header(self):
        name=self.name()
        if name=='None': return None
        typ=self.name(); size,index=self.unpack('ii'); require(size>=0 and index>=0,'Invalid tag size/index'); sub=None; flag=None
        if typ=='StructProperty': sub=self.name(); self.take(16)
        elif typ in ('ArrayProperty','SetProperty','ByteProperty','EnumProperty'): sub=self.name()
        elif typ=='MapProperty': sub=(self.name(),self.name())
        elif typ=='BoolProperty': flag=self.unpack('B')[0]; require(flag in (0,1),'Invalid bool')
        self.guid(); return name,typ,size,index,sub,flag
    def tags(self):
        result={}
        for _ in range(10000):
            h=self.header()
            if h is None: return result
            name,typ,size,index,sub,flag=h; require((name,index) not in result,'Duplicate tagged property'); result[name,index]=(typ,sub,bytes(self.take(size)),flag)
        raise ValueError('Too many properties')

def get(tags,name): return tags.get((name,0))

def sub_tags(tag,names,typ=None):
    require(tag is not None and tag[0]=='StructProperty' and (typ is None or tag[1]==typ),'Missing tagged structure '+str(typ)); r=Tags(tag[2],names); t=r.tags(); require(r.pos==len(r.data),'Unexpected struct trailer'); return t

def struct_array(tag,names):
    require(tag and tag[:2]==('ArrayProperty','StructProperty'),'Expected struct array');r=Tags(tag[2],names); n=r.i(); require(0<=n<=100000,'Invalid array count'); h=r.header(); require(h and h[1]=='StructProperty' and h[2]==len(r.data)-r.pos,'Invalid struct array header'); entries=[r.tags() for _ in range(n)];require(r.pos==len(r.data),'Unexpected array trailer');return h[4],entries

def value(tag,names,kind,default=None):
    if tag is None: return default
    t,s,p,f=tag; r=Tags(p,names)
    if kind in ('Vector','Rotator'):
        require(t=='StructProperty' and s==kind and len(p)==12,'Invalid vector tag'); out=r.unpack('3f')
    elif kind=='FloatProperty':
        require(t==kind and len(p)==4,'Invalid float tag');out=r.unpack('f')[0]
    elif kind=='NameProperty':
        require(t==kind and len(p)==8,'Invalid name tag');out=r.name()
    elif kind=='ByteProperty':
        require(t==kind and len(p)==8,'Invalid enum tag');out=r.name()
    elif kind=='BoolProperty':
        require(t==kind and not p,'Invalid bool tag');return bool(f)
    else: raise ValueError('Unsupported value type')
    require(not isinstance(out,(float,tuple)) or all(math.isfinite(x) for x in (out if isinstance(out,tuple) else [out])),'Nonfinite physics value');return out

def export_tags(a,e):
    require(0<e.serial_desc.count<=64*1024*1024,'Invalid export size');a.f.Seek(e.serial_desc.offset);r=Tags(a.f.ReadBytes(e.serial_desc.count),a.names);return r.tags(),bytes(r.data[r.pos:])

def references(tag,names,kind):
    require(tag and tag[:2]==('ArrayProperty',kind),'Missing reference array');r=Tags(tag[2],names);n=r.i();require(0<=n<=10000 and len(r.data)==4+4*n,'Invalid reference array');return [r.i() for _ in range(n)]

def convex_record(tags,names):
    # UE4.27 editor KConvexElem stores support points, not necessarily face indices.
    v=get(tags,'VertexData');require(v and v[:2]==('ArrayProperty','StructProperty'),'Missing convex vertices')
    r=Tags(v[2],names);n=r.i();require(4<=n<=4096,'Invalid convex vertex count');h=r.header()
    require(h and h[1]=='StructProperty' and h[4]=='Vector' and h[2]==12*n and len(r.data)-r.pos==12*n,'Invalid convex vector array')
    points=[r.unpack('3f') for _ in range(n)];require(all(math.isfinite(x) and abs(x)<=1e7 for pt in points for x in pt),'Invalid convex vertex')
    idx=get(tags,'IndexData');require(idx and idx[:2]==('ArrayProperty','IntProperty'),'Missing convex indices');r=Tags(idx[2],names);k=r.i();require(k==0 and r.pos==len(r.data),'Only unindexed editor convex supported')
    box=get(tags,'ElemBox');require(box and box[:2]==('StructProperty','Box') and len(box[2])==25,'Invalid convex bounds');bounds=struct.unpack('<6fB',box[2]);require(bounds[-1]==1 and all(math.isfinite(x) for x in bounds[:-1]),'Invalid convex bounds')
    require(all(abs(bounds[i]-min(pt[i] for pt in points))<.01 and abs(bounds[i+3]-max(pt[i] for pt in points))<.01 for i in range(3)),'Convex bounds mismatch')
    tr=sub_tags(get(tags,'Transform'),names,'Transform');q=get(tr,'Rotation');require(q and q[:2]==('StructProperty','Quat') and len(q[2])==16,'Invalid convex rotation');rot=struct.unpack('<4f',q[2]);loc=value(get(tr,'Translation'),names,'Vector');scale=value(get(tr,'Scale3D'),names,'Vector');require(rot==(0.,0.,0.,1.) and loc==(0.,0.,0.) and scale==(1.,1.,1.),'Only identity convex transforms supported')
    return dict(kind='convex',vertices_cm=points,bounds_cm=bounds[:6],rotation_xyzw=rot,translation_cm=loc,scale=scale,index_data=[],topology='convex hull derived from source support points')


def read_physics(path):
    import uasset
    from package_inspector import inspect_package
    p=Path(path);m=inspect_package(p);require(m.get('status')=='tables_inspected' and m['ue4']==522 and m['ue5'] is None and not m['sidecars'] and not m['flags']&0x80002000,'Only versioned UE4.27 editor physics supported')
    with uasset.UAsset(str(p)) as a:
        assets=[e for e in a.exports if e.export_class_type=='PhysicsAsset'];require(len(assets)==1,'Expected one physics export');e=assets[0];t,tail=export_tags(a,e)
        preview=get(t,'PreviewSkeletalMesh');require(preview and preview[0]=='SoftObjectProperty' and len(preview[2])==12,'Unsupported preview reference');r=Tags(preview[2],a.names);mesh=r.name();require(r.i()==0 and mesh.startswith('/Game/'),'Unsupported preview subpath')
        mesh=mesh.split('.')[0];bodies=[];joints=[]
        def refs(field,cls):
            ids=references(get(t,field),a.names,'ObjectProperty');require(len(set(ids))==len(ids) and all(0<i<=len(a.exports) for i in ids),'Invalid physics export references');out=[a.GetExport(i) for i in ids];require(all(x.export_class_type==cls for x in out),'Unexpected referenced export class');return out
        for b in refs('SkeletalBodySetups','SkeletalBodySetup'):
            bt,extra=export_tags(a,b);bone=value(get(bt,'BoneName'),a.names,'NameProperty');require(bone and bone!='None','Missing physics bone');shapes=[]
            for k,v in sub_tags(get(bt,'AggGeom'),a.names,'KAggregateGeom').items():
                typ,entries=struct_array(v,a.names);require((k,typ) in ((('SphylElems',0),'KSphylElem'),(('ConvexElems',0),'KConvexElem')),'Unsupported collision shape '+typ)
                for s in entries:
                    val=lambda key,kind,default=None:value(get(s,key),a.names,kind,default)
                    if typ=='KSphylElem':
                        radius=val('Radius','FloatProperty');length=val('Length','FloatProperty');require(radius is not None and length is not None and 0<radius<=100000 and 0<=length<=100000,'Invalid capsule dimensions')
                        shape=dict(kind='capsule',center_cm=val('Center','Vector',(0,0,0)),rotation_pyr=val('Rotation','Rotator',(0,0,0)),radius_cm=radius,length_cm=length)
                    else: shape=convex_record(s,a.names)
                    shape.update(name=val('Name','NameProperty','None'),collision=val('CollisionEnabled','ByteProperty'),rest_offset_cm=val('RestOffset','FloatProperty',0),generated=val('bIsGenerated','BoolProperty'),mass=val('bContributeToMass','BoolProperty'));shapes.append(shape)
            bodies.append(dict(bone=bone,shapes=shapes,export=b.object_name,trace= value(get(bt,'CollisionTraceFlag'),a.names,'ByteProperty'),native_tail_bytes=len(extra)))
        names={b['bone'] for b in bodies};require(len(names)==len(bodies),'Duplicate physics body bones')
        for j in refs('ConstraintSetup','PhysicsConstraintTemplate'):
            jt,extra=export_tags(a,j);st=sub_tags(get(jt,'DefaultInstance'),a.names,'ConstraintInstance');val=lambda key,kind,default=None:value(get(st,key),a.names,kind,default)
            b1,b2=val('ConstraintBone1','NameProperty'),val('ConstraintBone2','NameProperty');require(b1 in names and b2 in names and b1!=b2,'Invalid joint bones')
            frames=[]
            for i in (1,2):
                pos=val('Pos'+str(i),'Vector',(0,0,0));x=val('PriAxis'+str(i),'Vector',(1,0,0));y=val('SecAxis'+str(i),'Vector',(0,1,0));require(abs(sum(v*v for v in x)-1)<.001 and abs(sum(v*v for v in y)-1)<.001 and abs(sum(v*w for v,w in zip(x,y)))<.001,'Invalid joint axes');frames.append(dict(position_cm=pos,primary=x,secondary=y))
            profile={};pr=get(st,'ProfileInstance')
            if pr:
                for (key,idx),v in sub_tags(pr,a.names).items():
                    require(idx==0 and v[0]=='StructProperty','Unsupported joint profile');record={}
                    for (field,ix),w in sub_tags(v,a.names).items():
                        require(ix==0,'Unsupported profile index');record[field]=value(w,a.names,w[0]) if w[0] in ('ByteProperty','FloatProperty','BoolProperty','NameProperty') else dict(type=w[0],subtype=w[1],raw_hex=w[2].hex())
                    profile[key]=record
            joints.append(dict(name=val('JointName','NameProperty'),bones=[b1,b2],frames=frames,profile=profile,native_tail_bytes=len(extra)))
        return dict(name=e.object_name,source=str(p),preview_mesh=mesh,bodies=bodies,joints=joints,native_tail_bytes=len(tail))

def mesh_physics_reference(path):
    import uasset
    from blueprint_placement import package4
    with uasset.UAsset(str(path)) as a:
        ex=[e for e in a.exports if e.export_class_type=='SkeletalMesh'];require(len(ex)==1,'Expected one skeletal mesh');t,_=export_tags(a,ex[0]);tag=get(t,'PhysicsAsset');require(tag and tag[0]=='ObjectProperty' and len(tag[2])==4,'Missing physics reference');i=struct.unpack('<i',tag[2])[0];require(i<0,'Unsupported local physics reference');ref=package4(a,i);require(ref.startswith('/Game/'),'Unresolved physics package');return ref

def capsule_geometry(radius,length,segments=24,hemi=8):
    # Capsule along source Z; length is the cylindrical segment, not full height.
    require(radius>0 and length>=0,'Invalid capsule size'); verts=[(0,0,-length/2-radius)]; rings=[]
    for side in (-1,1):
        for j in range(1,hemi+1) if side<0 else range(hemi,0,-1):
            a=j*math.pi/(2*hemi);z=side*(length/2+radius*math.cos(a));rr=radius*math.sin(a)
            if side==1 and j==hemi and length==0:continue
            rings.append(len(verts));verts.extend((rr*math.cos(2*math.pi*k/segments),rr*math.sin(2*math.pi*k/segments),z) for k in range(segments))
    top=len(verts);verts.append((0,0,length/2+radius));faces=[]
    for k in range(segments):faces.append((0,rings[0]+(k+1)%segments,rings[0]+k))
    for a,b in zip(rings,rings[1:]):
        for k in range(segments):faces.append((a+k,a+(k+1)%segments,b+(k+1)%segments,b+k))
    for k in range(segments):faces.append((rings[-1]+k,rings[-1]+(k+1)%segments,top))
    return verts,faces

def joint_local(frame):
    from mathutils import Matrix,Vector
    def swap(v):return Vector((v[1],v[0],v[2]))
    # Convert the source primary/secondary axes to Blender; use a right-handed display basis.
    x,y=swap(frame['primary']).normalized(),swap(frame['secondary']).normalized();z=x.cross(y).normalized();m=Matrix((x,y,z)).transposed().to_4x4();m.translation=swap(frame['position_cm'])*.01;return m

def build_physics(arm,data,mesh_path,collection=None):
    import bpy,json
    from mathutils import Matrix
    from native_sockets import socket_local
    require(arm.type=='ARMATURE' and arm.mode=='OBJECT','Select armature in Object mode')
    require(arm.get('UE_source_mesh_path') and Path(arm['UE_source_mesh_path']).resolve()==Path(mesh_path).resolve(),'Target rig source identity mismatch; reimport the native skeletal mesh')
    ref=mesh_physics_reference(mesh_path);require(ref.rsplit('/',1)[-1]==data['name'] and Path(mesh_path).stem==data['preview_mesh'].rsplit('/',1)[-1],'Physics asset and mesh identity mismatch')
    require(not any(o.get('UE_physics_asset')==data['name'] for o in arm.children),'Physics asset already attached')
    plan=[]
    def prepare(bone,local):
        b=arm.data.bones.get(bone);require(b is not None,'Missing target bone '+bone);m=b.get('UE_world_matrix_m');require(m and len(m)==16,'Missing native reference matrix');rest=Matrix([m[i:i+4] for i in range(0,16,4)]);return Matrix.Translation((0,-b.length,0))@b.matrix_local.inverted()@rest@local
    for body in data['bodies']:
        for i,s in enumerate(body['shapes']):
            kind=s.get('kind','capsule');local=socket_local(dict(location_cm=s['center_cm'],rotation_pyr=s['rotation_pyr'],scale=(1,1,1))) if kind=='capsule' else Matrix.Identity(4);plan.append((kind,body['bone'],str(i),s,prepare(body['bone'],local)))
    for j in data['joints']:
        for i,(bone,frame) in enumerate(zip(j['bones'],j['frames'])):plan.append(('joint',bone,j['name']+'_'+str(i+1),j,prepare(bone,joint_local(frame))))
    created=[];meshes=[];coll=collection or arm.users_collection[0]
    try:
        for kind,bone,name,record,correction in plan:
            m=None
            if kind=='capsule':
                verts,faces=capsule_geometry(record['radius_cm']*.01,record['length_cm']*.01);m=bpy.data.meshes.new('UE collision capsule');meshes.append(m);m.from_pydata(verts,[],faces);require(not m.validate(),'Invalid capsule mesh');m.update()
            elif kind=='convex':
                m=bpy.data.meshes.new('UE collision convex');meshes.append(m);build_convex_mesh(m,record['vertices_cm'])
            o=bpy.data.objects.new('UE '+kind+' / '+bone+' / '+name,m);created.append(o);coll.objects.link(o);o.parent=arm;o.parent_type='BONE';o.parent_bone=bone;o.matrix_parent_inverse=correction;o.matrix_basis=Matrix.Identity(4);o.hide_render=True;o.show_in_front=True;o.display_type='WIRE';o.empty_display_type='ARROWS';o.empty_display_size=.05;o['UE_physics_asset']=data['name'];o['UE_physics_kind']=kind;o['UE_physics_record']=json.dumps(record);o['UE_physics_bone']=bone
        return created
    except Exception:
        for o in created:bpy.data.objects.remove(o,do_unlink=True)
        for m in meshes:
            if not m.users:bpy.data.meshes.remove(m)
        raise


def build_convex_mesh(mesh,points):
    # Incremental hull with double-precision plane predicates; avoids float32
    # hull construction dropping nearly coplanar support points.
    pts=list(dict.fromkeys((y*.01,x*.01,z*.01) for x,y,z in points));require(4<=len(pts)<=4096,'Invalid convex point count')
    def sub(a,b):return tuple(x-y for x,y in zip(a,b))
    def dot(a,b):return sum(x*y for x,y in zip(a,b))
    def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])
    def norm(a):return math.sqrt(dot(a,a))
    def normal(f):return cross(sub(pts[f[1]],pts[f[0]]),sub(pts[f[2]],pts[f[0]]))
    def distance(f,p):
        n=normal(f);return dot(n,sub(p,pts[f[0]]))/norm(n)
    i=0;j=max(range(len(pts)),key=lambda k:norm(sub(pts[k],pts[i])));span=norm(sub(pts[j],pts[i]));require(span>1e-9,'Degenerate convex hull')
    k=max(range(len(pts)),key=lambda k:norm(cross(sub(pts[j],pts[i]),sub(pts[k],pts[i]))));require(norm(normal((i,j,k)))/span>1e-9,'Degenerate convex hull')
    l=max(range(len(pts)),key=lambda l:abs(distance((i,j,k),pts[l])));require(abs(distance((i,j,k),pts[l]))>1e-9,'Degenerate convex hull')
    seed=(i,j,k,l);inside=tuple(sum(pts[a][axis] for a in seed)/4 for axis in range(3))
    def orient(f):return (f[0],f[2],f[1]) if distance(f,inside)>0 else f
    faces=[orient(f) for f in ((i,j,k),(i,j,l),(i,k,l),(j,k,l))]
    for q,p in enumerate(pts):
        if q in seed:continue
        visible=[f for f in faces if distance(f,p)>1e-9]
        if not visible:continue
        edges={}
        for a,b,c in visible:
            for e in ((a,b),(b,c),(c,a)):
                key=tuple(sorted(e));edges[key]=edges.get(key,0)+1
        faces=[f for f in faces if f not in visible]
        for (a,b),n in edges.items():
            if n==1:
                f=(a,b,q);require(norm(normal(f))>1e-18,'Degenerate convex horizon');faces.append(orient(f))
    edgecounts={}
    for a,b,c in faces:
        for e in ((a,b),(b,c),(c,a)):
            key=tuple(sorted(e));edgecounts[key]=edgecounts.get(key,0)+1
    require(all(n==2 for n in edgecounts.values()) and all(distance(f,p)<1e-7 for f in faces for p in pts),'Invalid convex topology')
    used=sorted({i for f in faces for i in f});remap={v:i for i,v in enumerate(used)}
    mesh.from_pydata([pts[i] for i in used],[],[tuple(remap[i] for i in f) for f in faces]);require(not mesh.validate(),'Invalid convex mesh');mesh.update()


def associate_physics(arm,mesh_path,content_root):
    """Resolve an exact /Game package against Content; never search by basename."""
    root=Path(content_root).resolve();source=Path(mesh_path).resolve()
    require(source.is_relative_to(root),'Source mesh outside project Content')
    ref=mesh_physics_reference(source);require(ref.startswith('/Game/'),'Unsupported physics package')
    parts=ref[6:].split('/');require(all(p and p not in ('.','..') and '\\' not in p and ':' not in p for p in parts),'Invalid physics package path')
    target=(root/(ref[6:]+'.uasset')).resolve();require(target.is_relative_to(root),'Physics path escapes Content')
    if not target.is_file(): return dict(status='missing',package=ref,path=str(target))
    data=read_physics(target);expected='/Game/'+source.relative_to(root).with_suffix('').as_posix()
    require(data['preview_mesh']==expected,'Physics preview package does not match mesh package')
    created=build_physics(arm,data,source)
    return dict(status='reconstructed',package=ref,objects=len(created),capsules=sum(o['UE_physics_kind']=='capsule' for o in created),convex=sum(o['UE_physics_kind']=='convex' for o in created),joint_anchors=sum(o['UE_physics_kind']=='joint' for o in created))
