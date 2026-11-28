"""Original saved box-shaped volume brush bounds, never renderable scenery.
Bounded UE5.6 inline and owned external actor profiles; no gameplay or postprocess simulation.
"""
import hashlib,json,struct
from pathlib import Path
from collections import Counter
from skeleton_native import Reader
from ue5_blueprint import read_tables,require
from ue5_editor_tags import export_tags
from ue5_editor_scene import index_value,external_packages
from ue5_editor_brushes import native_tail,decode_polys,mesh_arrays
from ue5_editor_decals import vector

KINDS={'LightmassImportanceVolume','NavMeshBoundsVolume','PostProcessVolume','BlockingVolume'}


def decode_volume_model(data):
    r=Reader(data);r.take(62)
    def array(stride,n):
        require(r.unpack('ii')==(stride,n),'Unsupported volume model array extent');return r.take(stride*n)
    array(12,6);pts=array(12,8);points=set(struct.iter_unpack('<3f',pts));require(len(points)==8,'Invalid volume points')
    array(64,6);require(r.i()==6,'Unsupported volume surfaces');r.take(56*6);array(24,24)
    shared,pi=r.unpack('ii');require(shared==4 and pi>0,'Invalid volume Polys reference');array(4,13);array(4,0)
    outside,linked,unique,n=r.unpack('4i');require(outside==1 and linked in (0,1) and unique==8 and n in (0,24),'Unsupported volume render buffer')
    r.take(n*56);r.take(56);require(r.pos==len(data),'Unexpected volume model tail')
    return pi,points


def records(content,path):
    content=Path(content).resolve();path=Path(path).resolve();require(path.is_relative_to(content),'Map outside Content')
    level='/Game/'+path.relative_to(content).with_suffix('').as_posix();rows=[];skips=[]
    for source in [path,*external_packages(content,path)]:
        rel=source.relative_to(content).as_posix()
        try:m,raw,_,exports,ref,pkg=read_tables(source)
        except ValueError as exc:skips.append(dict(source=rel,detail=str(exc)));continue
        for i,e in enumerate(exports,1):
            if e['kind'] not in KINDS:continue
            try:
                outer=e['outer'];parent=ref(outer);require(parent and parent['kind']=='Level' and parent['name']=='PersistentLevel' and ((source==path and outer>0) or (source!=path and outer<0 and pkg(outer)==level)),'Invalid volume level ownership')
                require(m['ue5'] in (1016,1017),'Unsupported volume editor version');at=export_tags(raw,e,m['names']);ci=index_value(at,'BrushComponent');mi=index_value(at,'Brush');require(ci>0 and mi>0 and index_value(at,'RootComponent')==ci,'Invalid volume component/model reference');co,mo=ref(ci),ref(mi);require(co['outer']==i and co['kind']=='BrushComponent' and mo['outer']==i and mo['kind']=='Model','Invalid volume model ownership')
                ct=export_tags(raw,co,m['names']);require(index_value(ct,'Brush')==mi and not index_value(ct,'AttachParent') and not any(k in ct for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale','AttachSocketName')),'Unsupported volume attachment');require(not export_tags(raw,mo,m['names']),'Unsupported volume model properties')
                fields={k:vector(ct,k,typ,default) for k,typ,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]};require(all(abs(x)>1e-12 for x in fields['RelativeScale3D']),'Degenerate volume scale')
                pi,points=decode_volume_model(native_tail(raw,mo));pe=ref(pi);require(pe['kind']=='Polys' and pe['outer']==mi and not export_tags(raw,pe,m['names']),'Invalid volume Polys ownership');payload=native_tail(raw,pe);polys=decode_polys(payload);require(len(polys)==6 and all(len(p['vertices'])==4 for p in polys) and set(v for p in polys for v in p['vertices'])==points,'Volume model/Polys mismatch')
                # Preserve tagged actor settings as source evidence without applying them as Blender effects.
                props={k:dict(type=v['type'],flags=v['flags'],data_hex=v['data'].hex()) for k,v in at.items() if k not in ('Brush','BrushComponent','RootComponent')}
                rows.append(dict(source=rel,actor=e['name'],kind=e['kind'],fields=fields,model_export=mi,polys_export=pi,polys_sha256=hashlib.sha256(payload).hexdigest(),polygons=polys,saved_actor_properties=props))
            except (ValueError,IndexError,struct.error,OverflowError) as exc:skips.append(dict(source=rel,actor=e['name'],detail=str(exc)))
    return rows,skips


def extend_volumes(content,path,parent):
    import bpy
    from blueprint_placement import apply_fields
    rows,skips=records(content,path);kinds=Counter()
    if rows:
        collection=bpy.data.collections.new(Path(path).stem+' — volume guides (non-rendering)');parent.children.link(collection);collection.hide_render=True
        for r in rows:
            vertices,faces=mesh_arrays(r['polygons']);mesh=bpy.data.meshes.new(r['actor']+' — volume bounds');mesh.from_pydata(vertices,[],faces);mesh.update();require(not mesh.validate(),'Invalid volume mesh');o=bpy.data.objects.new(r['actor'],mesh);collection.objects.link(o);apply_fields(o,r['fields']);o.display_type='WIRE';o.hide_render=True;o['UE_actor']=r['actor'];o['UE_source_actor_package']=r['source'];o['UE_volume_guide']=True;o['UE_volume_kind']=r['kind'];o['UE_volume_record']=json.dumps(r);kinds[r['kind']]+=1
    return dict(volumes=len(rows),kinds=dict(kinds),vertices=8*len(rows),faces=6*len(rows),skipped=skips,scope='Non-rendering editable saved brush bounds and raw tagged metadata; no runtime collision/navigation/lightmass or postprocess equivalence')
