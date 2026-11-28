"""Bounded UE5.6 editor brush operand reader. Never treats operands as compiled BSP.
Observed monolithic model with no compiled nodes (158-byte native tail) and
FPolys float32 vectors, variable vertex array and 76-byte post-array fields.
Reject any other profile rather than searching arbitrary bytes for polygons.
"""
import json, math, struct, hashlib
from pathlib import Path
from collections import Counter
from ue5_blueprint import read_tables, require
from ue5_editor_tags import export_tags
from ue5_editor_scene import index_value
from ue5_editor_decals import vector
from skeleton_native import Reader


def native_tail(raw,e):
    return raw[e['offset']+e['script_end']:e['offset']+e['size']]


def dot(a,b):return sum(x*y for x,y in zip(a,b))
def sub(a,b):return tuple(x-y for x,y in zip(a,b))
def cross(a,b):return (a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0])


def decode_polys(data):
    r=Reader(data);require(r.i()==0,'Unsupported Polys prefix');n=r.count(4096);require(n>0,'Empty brush polygons')
    rows=[]
    for _ in range(n):
        base,normal,u,v=(r.unpack('3f') for _ in range(4));count=r.count(1024);require(count>=3,'Invalid polygon vertex count')
        verts=[r.unpack('3f') for _ in range(count)];tail=r.take(76)
        require(all(math.isfinite(x) and abs(x)<=1e9 for a in [base,normal,u,v,*verts] for x in a),'Invalid polygon coordinate')
        require(abs(dot(normal,normal)-1)<1e-4,'Invalid source plane normal')
        require(len(set(verts))==count,'Repeated polygon vertex')
        extent=max(1.,max(math.sqrt(dot(sub(x,verts[0]),sub(x,verts[0]))) for x in verts))
        require(max(abs(dot(sub(x,verts[0]),normal)) for x in verts)<=max(.002,extent*1e-5),'Nonplanar source polygon')
        area=tuple(sum(cross(sub(verts[j],verts[0]),sub(verts[j+1],verts[0]))[i] for j in range(1,count-1)) for i in range(3))
        require(abs(dot(area,normal))>1e-6,'Degenerate source polygon')
        rows.append(dict(base=base,base_plane_offset=dot(sub(verts[0],base),normal),normal=normal,texture_u=u,texture_v=v,vertices=verts,winding_sign=1 if dot(area,normal)>0 else -1,opaque_post_vertex_hex=tail.hex()))
    require(r.pos==len(data),'Unexpected Polys native trailer');return rows


def records(content,path):
    content=Path(content).resolve();path=Path(path).resolve();require(path.is_relative_to(content),'Map outside Content')
    meta,raw,_,exports,ref,pkg=read_tables(path);require(meta['ue5'] in (1016,1017),'Unsupported brush editor version')
    require(any(e['kind']=='World' and not e['outer'] for e in exports),'Not a World package')
    names=meta['names'];rows=[];skipped=[];builders=[]
    for i,e in enumerate(exports,1):
        if e['kind']!='Brush':continue
        try:
            outer=e['outer'];require(outer>0 and ref(outer)['kind']=='Level' and ref(outer)['name']=='PersistentLevel','Brush not owned by inline PersistentLevel')
            at=export_tags(raw,e,names);bt=at.get('BrushType')
            if bt is None:
                builders.append(e['name']);continue # no explicit CSG role, including builder brush
            require(bt['type']==['ByteProperty','EBrushType','/Script/Engine'] and len(bt['data'])==8 and not bt['flags']&0x28,'Unsupported brush type')
            role=Reader(bt['data']).name(names);require(role in ('Brush_Add','Brush_Subtract'),'Unsupported explicit CSG role')
            ci=index_value(at,'BrushComponent');mi=index_value(at,'Brush');require(ci>0 and mi>0 and index_value(at,'RootComponent')==ci,'Invalid brush root/model reference')
            co=ref(ci);mo=ref(mi);require(co['outer']==i and co['kind']=='BrushComponent' and mo['kind']=='Model' and mo['outer']==i,'Invalid brush component/model ownership')
            ct=export_tags(raw,co,names);require(index_value(ct,'Brush')==mi,'Component/model reference differs')
            require(not index_value(ct,'AttachParent') and not any(k in ct for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')),'Attached/absolute brush unsupported')
            fields={k:vector(ct,k,typ,default) for k,typ,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]}
            require(all(abs(x)>1e-12 for x in fields['RelativeScale3D']),'Degenerate brush scale')
            model=native_tail(raw,mo);require(len(model)==158 and not export_tags(raw,mo,names),'Unsupported noncompiled brush Model profile')
            pi=struct.unpack_from('<i',model,102)[0];require(pi>0,'Missing Polys reference');pe=ref(pi);require(pe['kind']=='Polys' and pe['outer']==mi and not export_tags(raw,pe,names),'Invalid Polys ownership')
            payload=native_tail(raw,pe);polys=decode_polys(payload)
            rows.append(dict(source=path.relative_to(content).as_posix(),actor=e['name'],role=role,fields=fields,model_export=mi,polys_export=pi,polys_sha256=hashlib.sha256(payload).hexdigest(),polygons=polys))
        except (ValueError,IndexError,struct.error,OverflowError) as exc:skipped.append(dict(actor=e['name'],detail=str(exc)))
    return dict(records=rows,skipped=skipped,untyped_brushes=builders,compiled_model_components=sum(e['kind']=='ModelComponent' for e in exports),scope='Inline explicit CSG operands only; compiled BSP, volumes, external brushes and material projection not reconstructed')


def mesh_arrays(polys):
    vertices=[];indices={};faces=[]
    for p in polys:
        face=[]
        for v in p['vertices']:
            v=tuple(v)
            if v not in indices:indices[v]=len(vertices);vertices.append((v[1]*.01,v[0]*.01,v[2]*.01))
            face.append(indices[v])
        # Axis exchange reverses handedness. Align face winding to saved plane normal.
        faces.append(tuple(reversed(face)) if p['winding_sign']>0 else tuple(face))
    return vertices,faces


def extend_brushes(content,path,parent):
    import bpy
    from blueprint_placement import apply_fields
    data=records(content,path);rows=data.pop('records');counts=Counter();nv=nf=0
    if rows:
        collection=bpy.data.collections.new(Path(path).stem+' — BSP operands (non-rendering)');parent.children.link(collection);collection.hide_render=True
        for r in rows:
            verts,faces=mesh_arrays(r['polygons']);mesh=bpy.data.meshes.new(r['actor']+' — source brush');mesh.from_pydata(verts,[],faces);mesh.update()
            require(not mesh.validate(verbose=False),'Invalid reconstructed brush mesh')
            obj=bpy.data.objects.new(r['actor']+' — '+r['role'],mesh);collection.objects.link(obj);apply_fields(obj,r['fields']);obj.display_type='WIRE';obj.hide_render=True
            obj['UE_actor']=r['actor'];obj['UE_source_actor_package']=r['source'];obj['UE_brush_operand']=True;obj['UE_brush_role']=r['role'];obj['UE_brush_record']=json.dumps(r);obj['UE_preview_only']=True
            counts[r['role']]+=1;nv+=len(verts);nf+=len(faces)
    return dict(data,operands=sum(counts.values()),roles=dict(counts),vertices=nv,faces=nf,rendered_bsp=False)
