"""Bounded UE5 object-version 1004 editor material-instance and PNG source profile.
No modern tagged-property or package-trailer assumptions are applied to this format.
"""
import hashlib
import math
import struct
from pathlib import Path
from package_inspector import inspect_package
from skeleton_native import Reader
from ue5_blueprint import require


def read_tables(path):
    path=Path(path); m=inspect_package(path)
    require(m.get('status')=='tables_inspected' and m['ue4']==522 and m['ue5']==1004 and not m['sidecars'] and not m['flags']&0x80002000 and m['size']<=128*1024*1024,'Expected tagged UE5 1004 monolithic editor package')
    b=path.read_bytes(); names=m['names']; ic,ec=m['import_count'],m['export_count'];io,eo=m['import_offset'],m['export_offset']
    require(0<ic<=100000 and 0<ec<=100000 and io+40*ic==eo and eo+108*ec<=m['header_end'],'Invalid legacy table extent')
    r=Reader(b,io); im=[]; ex=[]
    for _ in range(ic):
        cp,cls,outer,name,pkg,opt=r.name(names),r.name(names),r.i(),r.name(names),r.name(names),r.i()
        require(-ic<=outer<=ec and opt in (0,1),'Invalid legacy import')
        im.append(dict(class_package=cp,kind=cls,outer=outer,name=name,package_name=pkg,optional=bool(opt)))
    for _ in range(ec):
        ci,si,ti,outer=r.unpack('4i');name=r.name(names);flags=r.unpack('I')[0];size,off=r.unpack('qq');bits=r.unpack('3i');r.take(16);pkg=r.unpack('I')[0];more=r.unpack('3i');deps=r.unpack('5i')
        require(all(-ic<=x<=ec for x in (ci,si,ti,outer)) and all(x in (0,1) for x in bits+more),'Invalid legacy export')
        require(m['header_end']<=off<=len(b) and 0<=size<=len(b)-off,'Invalid legacy export extent')
        ex.append(dict(name=name,class_index=ci,super_index=si,template=ti,outer=outer,offset=off,size=size))
    spans=sorted((x['offset'],x['offset']+x['size']) for x in ex if x['size'])
    require(all(a[1]<=c[0] for a,c in zip(spans,spans[1:])),'Overlapping legacy exports')
    def ref(i):
        require(-ic<=i<=ec,'Invalid package index');return im[-i-1] if i<0 else ex[i-1] if i>0 else None
    def package(i):
        seen=set()
        while i:
            require(i not in seen,'Package index cycle');seen.add(i);x=ref(i)
            if i<0 and x['kind']=='Package' and x['name'].startswith(('/Game/','/Engine/')):return x['name']
            i=x['outer']
        return ''
    for x in ex:x['kind']=ref(x['class_index'])['name'] if x['class_index'] else ''
    return m,b,im,ex,ref,package


def tags(r,names):
    out={}
    while True:
        k=r.name(names)
        if k=='None':return out
        ty=r.name(names);size,idx=r.unpack('2i');extra=None
        require(idx==0 and k not in out and len(out)<4096,'Repeated or oversized legacy properties')
        if ty=='StructProperty':extra=r.name(names);r.take(16)
        elif ty in ('ArrayProperty','ByteProperty','EnumProperty','SetProperty'):extra=r.name(names)
        elif ty=='MapProperty':raise NotImplementedError('Legacy map property')
        elif ty=='BoolProperty':
            extra=r.unpack('B')[0];require(extra in (0,1) and size==0,'Invalid legacy Boolean')
        flag=r.unpack('B')[0];require(flag in (0,1),'Invalid legacy property GUID flag')
        if flag:r.take(16)
        out[k]=(ty,extra,r.take(size))


def nested(x,names,sub):
    require(x[:2]==('StructProperty',sub),'Unexpected legacy struct '+str(x[:2]));r=Reader(x[2]);t=tags(r,names);require(r.pos==len(r.data),'Unexpected legacy struct tail');return t


def array(x,names,key,sub):
    require(x[:2]==('ArrayProperty','StructProperty'),'Expected legacy struct array');r=Reader(x[2]);count=r.count(4096)
    require(r.name(names)==key and r.name(names)=='StructProperty','Invalid legacy array tag');size=r.unpack('q')[0];require(r.name(names)==sub,'Unexpected legacy array element type');r.take(16);flag=r.unpack('B')[0];require(flag in (0,1),'Invalid array GUID flag')
    if flag:r.take(16)
    require(size==len(r.data)-r.pos,'Invalid legacy array extent');items=[tags(r,names) for _ in range(count)];require(r.pos==len(r.data),'Unexpected legacy array tail');return items


def value(x,ty,sub,fmt):
    require(x[:2]==(ty,sub) and len(x[2])==struct.calcsize('<'+fmt),'Invalid legacy value '+str(x[:2]));v=struct.unpack('<'+fmt,x[2]);require(all(math.isfinite(f) for f in v),'Nonfinite value');return v[0] if len(v)==1 else list(v)


def name(x,names,ty,sub=None):
    require(x[:2]==(ty,sub) and len(x[2])==8,'Invalid legacy name');return Reader(x[2]).name(names)


def boolean(t,k,default=False):
    if k not in t:return default
    x=t[k];require(x[0]=='BoolProperty' and x[1] in (0,1) and x[2]==b'','Invalid legacy Boolean');return bool(x[1])


def root(path,kind):
    m,b,im,ex,ref,pkg=read_tables(path); roots=[e for e in ex if not e['outer'] and e['kind']==kind];require(len(roots)==1,'Expected one legacy '+kind);e=roots[0];r=Reader(b[e['offset']:e['offset']+e['size']]);t=tags(r,m['names']);return m,b,ex,ref,pkg,e,t,r.take(len(r.data)-r.pos)


def read_material(path):
    m,b,ex,ref,pkg,e,t,tail=root(path,'MaterialInstanceConstant');names=m['names'];require(tail==bytes(16),'Unsupported legacy material native tail')
    i=value(t['Parent'],'ObjectProperty',None,'i');require(i<0 and ref(i)['kind'] in ('Material','MaterialInstanceConstant') and pkg(i),'Invalid legacy parent')
    out=dict(name=e['name'],kind='instance',parent=pkg(i),parameters=[],unsupported=[])
    def add(p,kind,v):
        info=nested(p['ParameterInfo'],names,'MaterialParameterInfo');nm=name(info['Name'],names,'NameProperty');require(name(info['Association'],names,'ByteProperty','EMaterialParameterAssociation')=='GlobalParameter' and value(info['Index'],'IntProperty',None,'i')==-1,'Unsupported legacy parameter association')
        g=p['ExpressionGUID'];require(g[:2]==('StructProperty','Guid') and len(g[2])==16,'Invalid expression GUID');out['parameters'].append(dict(name=nm,kind=kind,value=v,guid=g[2].hex()))
    for key,kind,sub,ty,vsub,fmt in [('ScalarParameterValues','scalar','ScalarParameterValue','FloatProperty',None,'f'),('VectorParameterValues','vector','VectorParameterValue','StructProperty','LinearColor','4f')]:
        if key not in t:continue
        for p in array(t[key],names,key,sub):
            if set(p)-{'ParameterInfo','ParameterValue','ExpressionGUID','AtlasData'}:out['unsupported'].append('Unknown legacy parameter fields')
            if 'AtlasData' in p:
                a=nested(p['AtlasData'],names,'ScalarParameterAtlasInstanceData')
                if any(v[0] not in ('SoftObjectProperty','BoolProperty') or (v[0]=='BoolProperty' and v[1]) or (v[0]=='SoftObjectProperty' and v[2]!=struct.pack('<ii',names.index('None'),0)+struct.pack('<i',0)) for v in a.values()):out['unsupported'].append('Legacy scalar atlas metadata not evaluated')
            add(p,kind,value(p['ParameterValue'],ty,vsub,fmt))
    if 'StaticParameters' in t:
        s=nested(t['StaticParameters'],names,'StaticParameterSet')
        if set(s)-{'StaticSwitchParameters'}:out['unsupported'].append('Unsupported legacy static parameter fields')
        if 'StaticSwitchParameters' in s:
            for p in array(s['StaticSwitchParameters'],names,'StaticSwitchParameters','StaticSwitchParameter'):
                if boolean(p,'bOverride'):add(p,'switch',boolean(p,'Value'))
    if 'BasePropertyOverrides' in t:
        a=nested(t['BasePropertyOverrides'],names,'MaterialInstanceBasePropertyOverrides');out['base_overrides']={k:dict(type=v[0],subtype=v[1],data=v[2].hex()) for k,v in a.items()}
        if any(k.startswith('bOverride') and boolean(a,k) for k in a):out['unsupported'].append('BasePropertyOverrides')
    if set(t)-{'ParameterStateId','Parent','bHasStaticPermutationResource','ScalarParameterValues','VectorParameterValues','BasePropertyOverrides','ReferencedTextureGuids','StaticParameters','ThumbnailInfo','LightingGuid'}:out['unsupported'].append('Unknown legacy instance fields')
    require(len({(p['kind'],p['name']) for p in out['parameters']})==len(out['parameters']),'Duplicate legacy parameter');return out


def read_texture(path,decoder=None):
    from editor_texture import source_png
    from ue5_editor_payload import extract_payload
    m,b,ex,ref,pkg,e,t,tail=root(path,'Texture2D');names=m['names'];s=nested(t['Source'],names,'TextureSource')
    w,h,n,sl=[value(s[k],'IntProperty',None,'i') for k in ('SizeX','SizeY','NumMips','NumSlices')];require(n==sl==1 and boolean(s,'bPNGCompressed'),'Unsupported legacy PNG source')
    fmt=name(s['Format'],names,'ByteProperty','ETextureSourceFormat');require(fmt=='TSF_BGRA8' and name(s['CompressionFormat'],names,'ByteProperty','ETextureSourceCompressionFormat')=='TSCF_PNG','Unsupported legacy source format')
    r=Reader(s['LayerFormat'][2]);require(s['LayerFormat'][:2]==('ArrayProperty','ByteProperty') and r.i()==1 and r.name(names)==fmt and r.pos==len(r.data),'Unsupported legacy layers');require(s['BlockDataOffsets']==('ArrayProperty','Int64Property',struct.pack('<iq',1,0)),'Unsupported legacy source blocks')
    require(len(tail)==68 and tail[:10]==bytes(6)+struct.pack('<I',64) and tail[-6:]==bytes(6),'Unsupported legacy bulk reference')
    digest=tail[26:46].hex();size,off=struct.unpack_from('<QQ',tail,46);require(off==max(x['offset']+x['size'] for x in ex) and off<len(b)-4 and b[-4:]==b'\xc1\x83\x2a\x9e','Invalid legacy payload extent')
    data,info=extract_payload(b,{digest:dict(offset=off,stored=len(b)-4-off,decoded=size)},digest,size,decoder);png=source_png(data,w,h,fmt,n,True)
    addr=lambda k:name(t[k],names,'ByteProperty','TextureAddress') if k in t else 'TA_Wrap'
    meta=dict(width=w,height=h,format=fmt,mips=1,source_png=True,srgb=boolean(t,'SRGB',True),flip_y=boolean(t,'bFlipGreenChannel'),address_x=addr('AddressX'),address_y=addr('AddressY'),nearest=name(t['Filter'],names,'ByteProperty','TextureFilter')=='TF_Nearest' if 'Filter' in t else False,profile='UE5 1004 editor PNG',source_hash=info['hash'],png_sha256=hashlib.sha256(png).hexdigest());meta['clamp']=meta['address_x']==meta['address_y']=='TA_Clamp';return png,meta
