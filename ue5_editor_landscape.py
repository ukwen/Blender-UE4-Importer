"""Saved UE5.6 monolithic Landscape heightfield, bounded local BGRA8 profile.
Source atlas preserves all finest-mip channels and duplicate border texels.
No inferred painted layers, holes or runtime LOD parity.
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


def source_atlas(tiles,q,s,n):
    """Lossless RGBA tile atlas; rows follow serialized source order, not Blender V."""
    import numpy as np
    side=(s+1)*n
    require(n in (1,2) and s>0 and q==s*n,'Invalid source atlas layout')
    xs=sorted({x for x,y in tiles});ys=sorted({y for x,y in tiles})
    require(xs and ys and xs==list(range(xs[0],xs[-1]+1,q)) and ys==list(range(ys[0],ys[-1]+1,q)) and len(tiles)==len(xs)*len(ys),'Invalid source atlas grid')
    w,h=len(xs)*side,len(ys)*side
    require(w*h<=16_000_000 and max(w,h)<=8192,'Oversized source atlas')
    atlas=np.empty((h,w,4),dtype=np.uint8);rows=[]
    for y in ys:
        for x in xs:
            a=tiles[x,y];require(a.dtype==np.uint8 and a.shape==(side,side,4),'Invalid source atlas tile')
            u,v=(x-xs[0])//q*side,(y-ys[0])//q*side
            rgba=a[:,:,[2,1,0,3]];atlas[v:v+side,u:u+side]=rgba
            rows.append(dict(section=[x,y],atlas_offset=[u,v],rgba_sha256=hashlib.sha256(rgba.tobytes()).hexdigest()))
    return atlas,dict(width=w,height=h,component_quads=q,subsection_quads=s,subsections=n,tiles=rows,rgba_sha256=hashlib.sha256(atlas.tobytes()).hexdigest(),scope='Exact finest source mip RGBA; auxiliary channels retained without assuming runtime normal decoding; no painted layer data')


def source_corner_uv(meta,grid_shape):
    """Derived atlas texel-center UVs: preserve BOTH copies of subsection borders."""
    import numpy as np
    q,s,n=(meta[k] for k in ('component_quads','subsection_quads','subsections'));side=(s+1)*n
    h,w=grid_shape;require((w-1)%q==0 and (h-1)%q==0 and meta['width']==(w-1)//q*side and meta['height']==(h-1)//q*side,'Source UV grid mismatch')
    # Source coordinates are separable. Keep only one-dimensional index
    # vectors and broadcast into the final contiguous corner buffer.
    xx=np.arange(w-1,dtype=np.int32);yy=np.arange(h-1,dtype=np.int32)
    tx,lx=xx//q,xx%q;ty,ly=yy//q,yy%q
    u=tx*side+lx+lx//s;v=ty*side+ly+ly//s
    uv=np.empty((h-1,w-1,4,2),dtype=np.float32)
    for k,(dx,dy) in enumerate(((0,0),(0,1),(1,1),(1,0))):
        uv[:,:,k,0]=(u+dx+.5)/meta['width']
        uv[:,:,k,1]=(1-(v+dy+.5)/meta['height'])[:,None]
    return uv.reshape(-1,2),(ty[:,None]*((w-1)//q)+tx).ravel()


def mesh_coordinates(grid,origin):
    """Contiguous float32 coordinates, same arithmetic/order as saved heightfield."""
    import numpy as np
    h,w=grid.shape;x,y=origin
    co=np.empty((h,w,3),dtype=np.float32)
    co[:,:,0]=((np.arange(h,dtype=np.float32)+y)*.01)[:,None]
    co[:,:,1]=(np.arange(w,dtype=np.float32)+x)*.01
    co[:,:,2]=grid
    co[:,:,2]/=128;co[:,:,2]*=.01
    return co.ravel()


def mesh_corner_indices(shape):
    """Generate row-major quad corners without a full vertex-ID grid."""
    import numpy as np
    h,w=shape
    rows=np.arange(h-1,dtype=np.int32)*w;cols=np.arange(w-1,dtype=np.int32)
    faces=np.empty((h-1,w-1,4),dtype=np.int32)
    faces[:,:,0]=rows[:,None]+cols
    for i,offset in enumerate((w,w+1,1),1):
        np.add(faces[:,:,0],offset,out=faces[:,:,i])
    return faces.ravel()


def texture_bindings(tags,actor,ref,pkg,names):
    t=tags.get('TextureParameterValues')
    if t is None:return []
    require(t['type']==['ArrayProperty','StructProperty','TextureParameterValue','/Script/Engine'],'Invalid landscape texture parameter array')
    r=Reader(t['data']);out=[]
    for _ in range(r.count(4096)):
        p=read_tag_stream(r,names);info=p['ParameterInfo'];require(info['type']==['StructProperty','MaterialParameterInfo','/Script/Engine'],'Invalid landscape parameter info');a=read_tags(info['data'],names)
        name=a['Name'];association=a['Association'];require(name['type']==['NameProperty'] and len(name['data'])==8 and association['type']==['ByteProperty','EMaterialParameterAssociation','/Script/Engine'] and len(association['data'])==8,'Invalid landscape parameter identity')
        nm=Reader(name['data']).name(names);assoc=Reader(association['data']).name(names);require(nm and assoc=='GlobalParameter' and integer(a,'Index')==-1,'Unsupported landscape parameter association')
        idx=index_value(p,'ParameterValue');target=ref(idx) if idx else None;value=None
        if idx>0:
            require(target['kind']=='Texture2D' and target['outer']==actor,'Invalid embedded landscape texture binding');value=dict(export=idx,name=target['name'])
        elif idx<0:
            require(target['kind']=='Texture2D' and pkg(idx),'Invalid imported landscape texture binding');value=dict(package=pkg(idx))
        out.append(dict(name=nm,association=assoc,value=value,guid=p.get('ExpressionGUID',{}).get('data',b'').hex()))
    require(r.pos==len(r.data) and len({x['name'] for x in out})==len(out),'Invalid landscape texture parameter extent/duplicates');return out


def material_bindings(tags,actor,ref,pkg,raw,names):
    """Read exact component instance ancestry; not a material translator."""
    from ue5_editor_components import array
    bindings=[]
    for idx in array(tags,'MaterialInstances'):
        chain=[];seen=set();parent=idx
        while parent>0:
            require(parent not in seen and len(seen)<32,'Landscape material cycle/depth')
            seen.add(parent);e=ref(parent);require(e['kind']=='LandscapeMaterialInstanceConstant' and e['outer']==actor,'Unexpected landscape material ownership')
            t=export_tags(raw,e,names);chain.append(dict(export=parent,name=e['name'],tag_names=sorted(t),texture_parameters=texture_bindings(t,actor,ref,pkg,names),texture_parameter_sha256=hashlib.sha256(t['TextureParameterValues']['data']).hexdigest() if 'TextureParameterValues' in t else None));parent=index_value(t,'Parent')
        require(parent<0 and ref(parent)['kind'] in ('Material','MaterialInstanceConstant') and pkg(parent),'Unresolved landscape material parent')
        bindings.append(dict(chain=chain,parent_package=pkg(parent)))
    lod=tags.get('LODIndexToMaterialIndex');lod_indices=None
    if lod is not None:
        require(lod['type']==['ArrayProperty','Int8Property'] and len(lod['data'])>=4,'Invalid landscape LOD material index array')
        count=struct.unpack_from('<i',lod['data'])[0];require(0<=count<=256 and len(lod['data'])==4+count,'Invalid landscape LOD material index extent')
        lod_indices=list(struct.unpack_from('<'+'b'*count,lod['data'],4));require(all(0<=i<len(bindings) for i in lod_indices),'Invalid landscape LOD material binding')
    return dict(instances=bindings,lod_indices=lod_indices)


def records(content,map_path,decoder=None,surface_data=None):
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
                    trailer=read_trailer(b,max(e['offset']+e['size'] for e in ex));tiles={};sources=[];texids=set();pixels={}
                    for i in indices:
                        e=ref(i);require(i>0 and e['outer']==ai and e['kind']=='LandscapeComponent','Invalid landscape component ownership');t=export_tags(b,e,names)
                        require([integer(t,k) for k in ('ComponentSizeQuads','SubsectionSizeQuads','NumSubsections')]==[q,s,n] and index_value(t,'AttachParent')==ri,'Landscape component layout mismatch')
                        require(not any(k in t for k in ('WeightmapTextures','WeightmapLayerAllocations','VisibilityLayer','XYOffsetmapTexture')),'Landscape layers, holes or XY offset not supported')
                        x,y=integer(t,'SectionBaseX',0),integer(t,'SectionBaseY',0);cf=fields(t);require(cf==dict(RelativeLocation=(x,y,0),RelativeRotation=(0,0,0),RelativeScale3D=(1,1,1)),'Component transform differs from section base')
                        side=(s+1)*n;require(typed(t,'HeightmapScaleBias',['StructProperty','Vector4','/Script/CoreUObject'],'<4d')==(1/side,1/side,0.,0.),'Shared or offset heightmap unsupported')
                        ti=index_value(t,'HeightmapTexture');texture=ref(ti);require(ti>0 and ti not in texids and texture['outer']==ai and texture['kind']=='Texture2D','Invalid heightmap identity');texids.add(ti)
                        aimg,digest=height_texture(b,texture,names,trailer,side,decoder);h=collapse_heightmap(aimg,s,n)
                        box=typed(t,'CachedLocalBox',['StructProperty','Box','/Script/CoreUObject'],'<6dB');require(box==(0.,0.,float(h.min())/128,q,q,float(h.max())/128,1),'Height bounds disagree with serialized component box')
                        require((x,y) not in tiles,'Duplicate landscape tile');tiles[x,y]=h;pixels[x,y]=aimg
                        try:binding=material_bindings(t,ai,ref,pkg,b,names)
                        except Exception as exc:binding=dict(status='unresolved',detail=str(exc))
                        sources.append(dict(component=e['name'],texture=texture['name'],section=[x,y],payload_hash=digest,local_box=box,material_bindings=binding))
                    grid,origin,seams=weld_tiles(tiles,q);mi=index_value(at,'LandscapeMaterial');require(not mi or mi<0 and ref(mi)['kind'] in ('Material','MaterialInstanceConstant') and pkg(mi),'Invalid landscape material reference')
                    record=dict(source=rel,actor=a['name'],fields=f,components=sources,grid_origin=origin,grid_size=[grid.shape[1],grid.shape[0]],seams=seams,height_min=int(grid.min()),height_max=int(grid.max()),height_sha256=hashlib.sha256(grid.astype('<i4').tobytes()).hexdigest(),material_package=pkg(mi) if mi else '',status='geometry_only',scope='Welded LOD0 heightfield quads; layer material, holes, collision and runtime triangulation not reconstructed')
                    record['weight_layers_status']='not_serialized_in_supported_profile'
                    try:
                        atlas,meta=source_atlas(pixels,q,s,n);record['source_atlas']=meta;record['source_atlas_status']='validated'
                        if surface_data is not None:surface_data[rel,a['name']]=atlas
                    except Exception as exc:
                        record['source_atlas_status']='unresolved';record['source_atlas_detail']=str(exc)
                    out.append((record,grid))
                except Exception as exc:skips.append(dict(source=rel,actor=a['name'],detail=str(exc)))
        except Exception as exc:skips.append(dict(source=rel,detail=str(exc)))
    return out,skips


def build(collection,record,grid,atlas=None):
    import bpy,numpy as np
    from blueprint_placement import apply_fields
    h,w=grid.shape;count=(h-1)*(w-1)
    mesh=bpy.data.meshes.new(record['actor']+' heightfield');obj=None;image=None
    try:
        # Do not retain coordinate, index and atlas buffers simultaneously.
        mesh.vertices.add(h*w);mesh.vertices.foreach_set('co',mesh_coordinates(grid,record['grid_origin']))
        mesh.loops.add(count*4);mesh.loops.foreach_set('vertex_index',mesh_corner_indices(grid.shape))
        mesh.polygons.add(count);mesh.polygons.foreach_set('loop_start',np.arange(count,dtype=np.int32)*4);mesh.polygons.foreach_set('loop_total',np.full(count,4,dtype=np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(count,dtype=np.bool_));mesh.update(calc_edges=True)
        require(not mesh.validate(),'Invalid generated landscape mesh')
        obj=bpy.data.objects.new(record['actor'],mesh);collection.objects.link(obj);apply_fields(obj,record['fields']);obj['UE_actor']=record['actor'];obj['UE_source_actor_package']=record['source'];obj['UE_geometry_status']='reconstructed';obj['UE_landscape_record']=__import__('json').dumps(record);obj['UE_landscape_material_package']=record['material_package'];obj['UE_unresolved_material']=True
        if atlas is not None:
            import tempfile
            from native_texture import png_bytes
            meta=record['source_atlas'];require(atlas.shape==(meta['height'],meta['width'],4) and hashlib.sha256(atlas.tobytes()).hexdigest()==meta['rgba_sha256'],'Invalid landscape atlas identity')
            uv,component=source_corner_uv(meta,grid.shape)
            layer=mesh.uv_layers.new(name='UE_SourceHeightmapAtlas',do_init=False);layer.data.foreach_set('uv',uv.ravel())
            attr=mesh.attributes.new('UE_landscape_component_index','INT','FACE');attr.data.foreach_set('value',component)
            del uv,component
            png=png_bytes(meta['width'],meta['height'],atlas.tobytes())
            with tempfile.TemporaryDirectory() as d:
                p=Path(d)/'source.png';p.write_bytes(png);image=bpy.data.images.load(str(p),check_existing=False);image.name=record['actor']+' — source heightmap RGBA';image.colorspace_settings.name='Non-Color';image.alpha_mode='CHANNEL_PACKED';image.pack();image.filepath='//'+image.name+'.png'
            image.use_fake_user=True;image['UE_landscape_source_atlas']=meta['rgba_sha256'];image['UE_source_actor_package']=record['source'];image['UE_source_png_sha256']=hashlib.sha256(png).hexdigest();obj['UE_landscape_source_atlas']=image.name;obj['UE_landscape_source_atlas_sha256']=meta['rgba_sha256'];obj['UE_landscape_source_uv']=layer.name
        return obj
    except Exception:
        if obj:bpy.data.objects.remove(obj,do_unlink=True)
        if mesh.users==0:bpy.data.meshes.remove(mesh)
        if image is not None:bpy.data.images.remove(image)
        raise


def extend_landscapes(content,path,collection):
    pixels={};plans,skipped=records(content,path,surface_data=pixels);result=[]
    for r,h in plans:
        try:
            atlas=pixels.get((r['source'],r['actor']))
            try:obj=build(collection,r,h,atlas)
            except Exception as exc:
                if atlas is None:raise
                r['source_atlas_status']='build_failed';r['source_atlas_detail']=str(exc);obj=build(collection,r,h)
            result.append(dict(r,vertices=len(obj.data.vertices),quads=len(obj.data.polygons),source_atlas_image=obj.get('UE_landscape_source_atlas')))
        except Exception as exc:skipped.append(dict(source=r['source'],actor=r['actor'],detail=str(exc)))
    return dict(records=result,skipped=skipped,actors=len(result),components=sum(len(r['components']) for r in result),vertices=sum(r['vertices'] for r in result),quads=sum(r['quads'] for r in result),scope='Saved landscape geometry and lossless source heightmap atlas; unresolved surface material, weight layers and runtime LOD')
