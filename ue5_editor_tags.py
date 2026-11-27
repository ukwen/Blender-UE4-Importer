"""Bounded complete-type-name tagged properties for tested UE5 editor exports.
Preserve payload bytes; consumers interpret only explicit types and fields.
"""
from skeleton_native import Reader
from ue5_blueprint import require


def read_tags(data,names,control=False):
    r=Reader(data); out={}
    if control: require(r.take(1)==b'\0','Unsupported class serialization control')
    while True:
        key=r.name(names)
        if key=='None':
            require(r.pos==len(data),'Unexpected tagged property trailer');return out
        require(len(out)<10000,'Too many property tags')
        nodes=[];remaining=1
        while remaining:
            typ,n=r.name(names),r.count(64);nodes.append(typ);remaining+=n-1
            require(len(nodes)+remaining<=128,'Oversized property type tree')
        size=r.i();flags=r.take(1)[0];require(size>=0 and not flags&~0x3f,'Invalid property tag')
        idx=r.i() if flags&1 else 0
        if flags&2:r.take(16)
        if flags&4:
            ext=r.take(1)[0];require(not ext&~2,'Unsupported tag extension')
            if ext&2:r.take(5)
        require(idx==0 and key not in out,'Repeated property unsupported')
        out[key]={'type':nodes,'flags':flags,'data':r.take(size)}


def export_tags(raw,e,names):
    return read_tags(raw[e['offset']+e['script_start']:e['offset']+e['script_end']],names,control=True)
