"""Bounded UE5.5 cooked BC1 texture profile with ordinal mip data.
The native source has a contiguous external mip prefix, inline smaller mips,
and serialized dimensions/ordinals. No virtual textures or arbitrary bulk maps.
"""
from pathlib import Path
from ue5_modern_static import package
from skeletal_mesh_native import require


def read_texture55(path):
    _,_,names,_,r,_=package(path,'Texture2D')
    require(r.take(2)==bytes.fromhex('0405'),'Unsupported UE5.5 texture property fragments')
    imported_w,imported_h=r.unpack('ii'); r.take(16)
    require(r.unpack('iHHII')==(0,5,5,1,1),'Unsupported UE5.5 texture flags')
    require(r.name(names)=='PF_DXT1','Unsupported UE5.5 platform format')
    size=r.unpack('q')[0]; require(size==len(r.data)-r.pos,'Invalid UE5.5 platform extent')
    require(r.take(16)==bytes(16),'Unsupported UE5.5 derived texture metadata')
    w,h,slices=r.unpack('iii'); fmt=r.string()
    require(fmt=='PF_DXT1' and 1<=w<=4096 and 1<=h<=4096 and slices==1 and (w,h)==(imported_w,imported_h),'Unsupported UE5.5 texture dimensions')
    first,count=r.unpack('ii');require(first==0 and 1<=count<=13 and count==max(w,h).bit_length(),'Unsupported UE5.5 mip chain')
    bulkpath=Path(path).with_suffix('.ubulk'); require(bulkpath.is_file() and bulkpath.stat().st_size<=128*1024*1024,'Missing or oversized UE5.5 texture bulk')
    bulk=bulkpath.read_bytes(); dims=[(max(1,w>>i),max(1,h>>i)) for i in range(count)]
    lengths=[((a+3)//4)*((b+3)//4)*8 for a,b in dims]
    # The tested streamed layout stores the largest mips contiguously in
    # .ubulk. Identify the unique boundary by exact total byte coverage.
    candidates=[i for i in range(1,count) if sum(lengths[:i])==len(bulk)]
    require(len(candidates)==1,'Invalid UE5.5 external mip coverage'); external=candidates[0]
    off=0; mips=[]
    for i,((mw,mh),length) in enumerate(zip(dims,lengths)):
        require(r.i()==i,'Invalid UE5.5 mip ordinal')
        if i<external: raw=bulk[off:off+length];off+=length
        else: raw=r.take(length)
        require(r.unpack('iii')==(mw,mh,1),'Invalid UE5.5 mip dimensions');mips.append(raw)
    require(off==len(bulk) and r.i()==0 and r.name(names)=='None' and r.pos==len(r.data),'Invalid UE5.5 platform terminator')
    return w,h,fmt,mips
