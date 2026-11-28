"""Bounded UE SerializeCompressed zlib chunk reader for validated editor bulk."""
import struct
import zlib

MAX_OUTPUT=256*1024*1024

def decompress_chunks(payload, expected):
    if not 0<expected<=MAX_OUTPUT or len(payload)<32:
        raise ValueError('Invalid compressed source extent')
    signature,unit,packed_total,total=struct.unpack_from('<4Q',payload)
    if signature!=0x9e2a83c1 or not 0<unit<=MAX_OUTPUT or total!=expected:
        raise ValueError('Invalid compressed source header')
    count=(total+unit-1)//unit
    start=32+count*16
    if start>len(payload) or len(payload)-start!=packed_total:
        raise ValueError('Invalid compressed source table extent')
    result=bytearray()
    for number,(packed,expanded) in enumerate(struct.iter_unpack('<2Q',payload[32:start])):
        if expanded!=min(unit,total-number*unit) or not 0<packed<=len(payload)-start:
            raise ValueError('Invalid compressed source chunk extent')
        decoder=zlib.decompressobj()
        part=decoder.decompress(payload[start:start+packed],expanded+1)
        if len(part)!=expanded or not decoder.eof or decoder.unused_data or decoder.unconsumed_tail:
            raise ValueError('Invalid compressed source chunk')
        result.extend(part);start+=packed
    if start!=len(payload) or len(result)!=total:
        raise ValueError('Invalid compressed source total')
    return bytes(result)
