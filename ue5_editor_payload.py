"""UE5 editor package trailer v2 / FCompressedBuffer, explicit local payloads only.
External decoder is separately built and explicitly configured. No magic scanning.
"""
import os
import struct
import subprocess
import zlib
from pathlib import Path
from ue5_blueprint import require

MAX_PAYLOAD=256*1024*1024
TRAILER_MAGIC=0xd1c43b2e80a5f697
FOOTER_MAGIC=0x29bfca045138de76


def read_trailer(raw, minimum=0):
    require(len(raw)>=48 and raw[-4:]==b'\xc1\x83\x2a\x9e','Invalid package footer')
    magic,size=struct.unpack_from('<QQ',raw,len(raw)-20)
    require(magic==FOOTER_MAGIC and 48<=size<=len(raw)-minimum,'Invalid package trailer footer')
    start=len(raw)-size
    magic,version,header_size,data_size,count=struct.unpack_from('<QIIQI',raw,start)
    require(magic==TRAILER_MAGIC and version==2 and count<=4096 and header_size==28+49*count and header_size+data_size+20==size,'Unsupported trailer header')
    records={}; spans=[]
    for i in range(count):
        pos=start+28+49*i
        digest=raw[pos:pos+20]; offset,stored,decoded,flags,filter_reason,access=struct.unpack_from('<qQQHHB',raw,pos+20)
        require(any(digest) and digest not in records,'Duplicate or null payload identity')
        if access!=0:
            raise NotImplementedError('Referenced or virtualized editor payload unsupported')
        require(0<=offset<=data_size and 64<=stored<=min(MAX_PAYLOAD,data_size-offset) and 0<decoded<=MAX_PAYLOAD,'Invalid local payload extent')
        begin=start+header_size+offset; spans.append((offset,offset+stored)); records[digest.hex()]=dict(offset=begin,stored=stored,decoded=decoded,flags=flags,filter_reason=filter_reason)
    expected=0
    for lo,hi in sorted(spans):
        require(lo==expected,'Overlapping or gapped local payloads'); expected=hi
    require(expected==data_size,'Unaccounted trailer data')
    return records


def compressed_header(buffer):
    require(len(buffer)>=64,'Truncated compressed buffer')
    magic,crc,method,compressor,level,exp,count,raw_size,stored=struct.unpack_from('>II4BIQQ',buffer)
    require(magic==0xb7756362 and stored==len(buffer) and 0<raw_size<=MAX_PAYLOAD and stored<=MAX_PAYLOAD,'Invalid compressed buffer sizes')
    if method==0:
        require((compressor,level,exp,count)==(0,0,0,1) and stored==64+raw_size,'Invalid uncompressed buffer')
        header_size=64
    elif method==3:
        require((compressor,level,exp)==(3,3,18) and count==(raw_size+262143)//262144,'Unsupported Oodle profile')
        header_size=64+4*count; require(header_size<=stored,'Truncated Oodle block table')
        sizes=struct.unpack_from('>'+str(count)+'I',buffer,64)
        require(sum(sizes)==stored-header_size and all(0<s<=min(262144,raw_size-i*262144) for i,s in enumerate(sizes)),'Invalid Oodle block extents')
    else: raise NotImplementedError('Unsupported compressed buffer method '+str(method))
    require(zlib.crc32(buffer[8:header_size])&0xffffffff==crc,'Compressed buffer header CRC mismatch')
    return dict(method=method,raw_size=raw_size,stored=stored,hash=buffer[32:64].hex(),blocks=count)


def extract_payload(raw,records,digest,declared_size=None,decoder=None):
    require(digest in records,'Source payload missing from local trailer'); entry=records[digest]
    data=raw[entry['offset']:entry['offset']+entry['stored']]; info=compressed_header(data)
    require(info['hash'][:40]==digest and info['raw_size']==entry['decoded'] and (declared_size is None or declared_size==entry['decoded']),'Payload hash identity or size mismatch')
    decoder=decoder or os.environ.get('UE_EDITOR_PAYLOAD_DECODER')
    if not decoder or not Path(decoder).is_file():
        raise NotImplementedError('Configure the separately built UE_EDITOR_PAYLOAD_DECODER executable')
    try:
        result=subprocess.run([str(Path(decoder).resolve())],input=data,stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=120,check=False)
    except subprocess.TimeoutExpired as exc: raise ValueError('Editor payload decoder timed out') from exc
    require(result.returncode==0 and len(result.stdout)==info['raw_size'],'Editor payload decode or BLAKE3 verification failed (status %s)'%result.returncode)
    return result.stdout,info
