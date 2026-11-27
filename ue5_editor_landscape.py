"""Saved UE5.6 monolithic Landscape heightfield, bounded local BGRA8 profile.
No inferred heights, generated foliage, weight layers, holes or runtime LOD parity.
"""
import struct, hashlib, math
from pathlib import Path
from ue5_blueprint import read_tables, require
from ue5_editor_tags import export_tags, read_tags, read_tag_stream
from ue5_editor_payload import read_trailer, extract_payload
from ue5_editor_texture import decode_delta
from ue5_editor_scene import index_value, external_packages
from skeleton_native import Reader


def typed(tags, key, types, fmt):
    t=tags[key]; require(t['type']==types and len(t['data'])==struct.calcsize(fmt) and not t['flags']&0x20,'Invalid '+key)
    return struct.unpack(fmt,t['data'])


def integer(tags,key,default=None):
    return default if key not in tags and default is not None else typed(tags,key,['IntProperty'],'<i')[0]


def fields(tags):
    require(not any(k in tags for k in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale','AttachSocketName')),'Unsupported landscape transform')
    out={k:typed(tags,k,['StructProperty',typ,'/Script/CoreUObject'],'<3d') if k in tags else default for k,typ,default in [('RelativeLocation','Vector',(0.,0.,0.)),('RelativeRotation','Rotator',(0.,0.,0.)),('RelativeScale3D','Vector',(1.,1.,1.))]}
    require(all(math.isfinite(x) for v in out.values() for x in v) and min(out['RelativeScale3D'])>0,'Invalid landscape transform');return out


def collapse_heightmap(bgra,subquads,subsections):
    import numpy as np
    side=(subquads+1)*subsections
    require(bgra.shape==(side,side,4),'Heightmap extent mismatch')
    h=bgra[:,:,2].astype(np.int32)*256+bgra[:,:,1].astype(np.int32)-32768
    drops=[]
    for i in range(1,subsections):
        j=i*(subquads+1);require(np.array_equal(h[:,j-1],h[:,j]) and np.array_equal(h[j-1,:],h[j,:]),'Subsection height seam mismatch');drops.append(j)
    return np.delete(np.delete(h,drops,axis=0),drops,axis=1)


def weld_tiles(tiles,q):
    import numpy as np
    require(tiles and 1<=q<=255 and len(tiles)<=1024,'Unsupported landscape grid size')
    xs=sorted({x for x,y in tiles});ys=sorted({y for x,y in tiles});w=xs[-1]-xs[0]+q+1;h=ys[-1]-ys[0]+q+1
    require(w*h<=4_000_000 and xs==list(range(xs[0],xs[-1]+1,q)) and ys==list(range(ys[0],ys[-1]+1,q)) and len(tiles)==len(xs)*len(ys),'Sparse or oversized landscape grid unsupported')
    grid=np.empty((h,w),dtype=np.int32);seams=0
    for (x,y),a in tiles.items():
        require(a.shape==(q+1,q+1) and np.issubdtype(a.dtype,np.integer) and a.min()>=-32768 and a.max()<=32767,'Invalid height tile')
        if (x+q,y) in tiles:require(np.array_equal(a[:,-1],tiles[x+q,y][:,0]),'Landscape X seam mismatch');seams+=1
        if (x,y+q) in tiles:require(np.array_equal(a[-1,:],tiles[x,y+q][0,:]),'Landscape Y seam mismatch');seams+=1
        u,v=x-xs[0],y-ys[0];grid[v:v+q+1,u:u+q+1]=a
    return grid,(xs[0],ys[0]),seams


def height_texture(raw,texture,names,trailer,side,decoder=None):
    import numpy as np
    tags=export_tags(raw,texture,names);src=tags['Source'];require(src['type']==['StructProperty','TextureSource','/Script/Engine'],'Invalid height texture source');s=read_tags(src['data'],names)
    w,h,n,sl=[integer(s,k) for k in ('SizeX','SizeY','NumMips','NumSlices')]
    require(w==h==side and side in (64,128,256) and sl==1 and n==side.bit_length(),'Unsupported heightmap mip extent')
    for key,kind,value in [('Format','ETextureSourceFormat','TSF_BGRA8'),('CompressionFormat','ETextureSourceCompressionFormat','TSCF_UEDELTA')]:
        t=s[key];require(t['type']==['ByteProperty',kind,'/Script/Engine'] and len(t['data'])==8 and Reader(t['data']).name(names)==value,'Unsupported heightmap format')
    require('LayerFormat' not in s and s['BlockDataOffsets']['type']==['ArrayProperty','Int64Property'] and s['BlockDataOffsets']['data']==struct.pack('<iq',1,0),'Unsupported heightmap layers/blocks')
    require(tags.get('SRGB',{}).get('type')==['BoolProperty'] and tags['SRGB']['flags']==0 and not tags['SRGB']['data'],'Heightmap must be non-sRGB')
    tail=raw[texture['offset']+texture['script_end']:texture['offset']+texture['size']];require(len(tail)==60 and tail[:10]==bytes.fromhex('00000000000000020000') and tail[-6:]==bytes(6),'Unsupported heightmap payload reference')
    size=sum((side>>i)**2*4 for i in range(n));require(struct.unpack_from('<Q',tail,46)[0]==size,'Heightmap mip byte count mismatch')
    digest=tail[26:46].hex();data,info=extract_payload(raw,trailer,digest,size,decoder);a=decode_delta(data[:side*side*4],side,side)
    color=s['LayerColorInfo_LockProtected'];require(color['type']==['ArrayProperty','StructProperty','TextureSourceLayerColorInfo','/Script/Engine'],'Missing height color extrema');r=Reader(color['data']);require(r.i()==1,'Unsupported color layers');c=read_tag_stream(r,names);require(r.pos==len(r.data),'Invalid color metadata extent')
    rgba=a[:,:,[2,1,0,3]]
    for k,v in [('ColorMin',rgba.min(axis=(0,1))),('ColorMax',rgba.max(axis=(0,1)))]:
        expected=typed(c,k,['StructProperty','LinearColor','/Script/CoreUObject'],'<4f');require(np.max(np.abs(v/255.-expected))<1e-6,'Heightmap color extrema mismatch')
    return a,info['hash']


def records(content,map_path,decoder=None):
    content=Path(content).resolve();path=Path(map_path).resolve();level='/Game/'+path.relative_to(content).with_suffix('').as_posix();out=[];skips=[]
    # External LandscapeStreamingProxy uses a different association profile; inventory it but do not guess.
    for source in [path,*external_packages(content,path)]:
        rel=source.relative_to(content).as_posix()
        try:
            m,b,im,ex,ref,pkg=read_tables(source);names=m['names']
            for ai,a in enumerate(ex,1):
                if a['kind'] not in ('Landscape','LandscapeStreamingProxy'):continue
                try:
                    require(m['ue5'] in (1016,1017) and a['kind']=='Landscape' and source==path,'Unsupported external landscape/proxy profile')
                    parent=ref(a['outer']);require(a['outer']>0 and parent['kind']=='Level' and parent['name']=='PersistentLevel','Invalid landscape level ownership')
                    at=export_tags(b,a,names);q,s,n=[integer(at,k) for k in ('ComponentSizeQuads','SubsectionSizeQuads','NumSubsections')];require(n in (1,2) and q==s*n and (s+1)*n in (64,128,256),'Unsupported landscape subsection layout')
                    ri=index_value(at,'RootComponent');root=ref(ri);require(ri>0 and root['outer']==ai and root['kind']=='SceneComponent','Invalid landscape root');rt=export_tags(b,root,names);require(not index_value(rt,'AttachParent'),'Unsupported landscape root parent');f=fields(rt)
                    from ue5_editor_components import array
                    indices=array(at,'LandscapeComponents');require(indices and len(indices)==len(set(indices))<=1024,'Invalid landscape component list')
                    trailer=read_trailer(b,max(e['offset']+e['size'] for e in ex));tiles={};sources=[];texids=set()
                    for i in indices:
                        e=ref(i);require(i>0 and e['outer']==ai and e['kind']=='LandscapeComponent','Invalid landscape component ownership');t=export_tags(b,e,names)
                        require([integer(t,k) for k in ('ComponentSizeQuads','SubsectionSizeQuads','NumSubsections')]==[q,s,n] and index_value(t,'AttachParent')==ri,'Landscape component layout mismatch')
                        require(not any(k in t for k in ('WeightmapTextures','WeightmapLayerAllocations','VisibilityLayer','XYOffsetmapTexture')),'Landscape layers, holes or XY offset not supported')
                        x,y=integer(t,'SectionBaseX',0),integer(t,'SectionBaseY',0);cf=fields(t);require(cf==dict(RelativeLocation=(x,y,0),RelativeRotation=(0,0,0),RelativeScale3D=(1,1,1)),'Component transform differs from section base')
                        side=(s+1)*n;require(typed(t,'HeightmapScaleBias',['StructProperty','Vector4','/Script/CoreUObject'],'<4d')==(1/side,1/side,0.,0.),'Shared or offset heightmap unsupported')
                        ti=index_value(t,'HeightmapTexture');texture=ref(ti);require(ti>0 and ti not in texids and texture['outer']==ai and texture['kind']=='Texture2D','Invalid heightmap identity');texids.add(ti)
                        aimg,digest=height_texture(b,texture,names,trailer,side,decoder);h=collapse_heightmap(aimg,s,n)
                        box=typed(t,'CachedLocalBox',['StructProperty','Box','/Script/CoreUObject'],'<6dB');require(box==(0.,0.,float(h.min())/128,q,q,float(h.max())/128,1),'Height bounds disagree with serialized component box')
                        require((x,y) not in tiles,'Duplicate landscape tile');tiles[x,y]=h;sources.append(dict(component=e['name'],texture=texture['name'],section=[x,y],payload_hash=digest,local_box=box))
                    grid,origin,seams=weld_tiles(tiles,q);mi=index_value(at,'LandscapeMaterial');require(not mi or mi<0 and ref(mi)['kind'] in ('Material','MaterialInstanceConstant') and pkg(mi),'Invalid landscape material reference')
                    record=dict(source=rel,actor=a['name'],fields=f,components=sources,grid_origin=origin,grid_size=[grid.shape[1],grid.shape[0]],seams=seams,height_min=int(grid.min()),height_max=int(grid.max()),height_sha256=hashlib.sha256(grid.astype('<i4').tobytes()).hexdigest(),material_package=pkg(mi) if mi else '',status='geometry_only',scope='Welded LOD0 heightfield quads; layer material, holes, collision and runtime triangulation not reconstructed')
                    out.append((record,grid))
                except Exception as exc:skips.append(dict(source=rel,actor=a['name'],detail=str(exc)))
        except Exception as exc:skips.append(dict(source=rel,detail=str(exc)))
    return out,skips


def build(collection,record,grid):
    import bpy,numpy as np
    from blueprint_placement import apply_fields
    h,w=grid.shape;x,y=record['grid_origin'];yy,xx=np.indices((h,w),dtype=np.float32)
    co=np.stack(((yy+y)*.01,(xx+x)*.01,grid.astype(np.float32)/128*.01),axis=-1).reshape(-1,3)
    ids=np.arange(h*w,dtype=np.int32).reshape(h,w);a=ids[:-1,:-1].ravel();faces=np.stack((a,a+w,a+w+1,a+1),axis=1).ravel();count=len(a)
    mesh=bpy.data.meshes.new(record['actor']+' heightfield');obj=None
    try:
        mesh.vertices.add(h*w);mesh.vertices.foreach_set('co',co.ravel());mesh.loops.add(count*4);mesh.loops.foreach_set('vertex_index',faces);mesh.polygons.add(count);mesh.polygons.foreach_set('loop_start',np.arange(count,dtype=np.int32)*4);mesh.polygons.foreach_set('loop_total',np.full(count,4,dtype=np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(count,dtype=np.bool_));mesh.update(calc_edges=True)
        require(not mesh.validate(),'Invalid generated landscape mesh')
        obj=bpy.data.objects.new(record['actor'],mesh);collection.objects.link(obj);apply_fields(obj,record['fields']);obj['UE_actor']=record['actor'];obj['UE_source_actor_package']=record['source'];obj['UE_geometry_status']='reconstructed';obj['UE_landscape_record']=__import__('json').dumps(record);obj['UE_landscape_material_package']=record['material_package'];obj['UE_unresolved_material']=True
        return obj
    except Exception:
        if obj:bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
        raise


def extend_landscapes(content,path,collection):
    plans,skipped=records(content,path);result=[]
    for r,h in plans:
        try:
            obj=build(collection,r,h);result.append(dict(r,vertices=len(obj.data.vertices),quads=len(obj.data.polygons)))
        except Exception as exc:skipped.append(dict(source=r['source'],actor=r['actor'],detail=str(exc)))
    return dict(records=result,skipped=skipped,actors=len(result),components=sum(len(r['components']) for r in result),vertices=sum(r['vertices'] for r in result),quads=sum(r['quads'] for r in result),scope='Saved landscape geometry only; unresolved surface material and runtime LOD')
