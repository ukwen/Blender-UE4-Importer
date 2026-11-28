"""Bounded source-edge recovery for tagged UE4.18 filtered material exports.

Serialization reference: MIT UAssetAPI MaterialInputProperties.cs. Filtered
FExpressionInput records identify a source expression by FName, not index.
This preserves exact source bindings without asserting a rendered shader.
"""
from pathlib import Path
from project_geometry import read_ue4_split_tables
from skeleton_native import Reader
from ue4_property_records import read_records
from classic_material import require, unsupported, name, object_index


def read_source_edges(path):
    cls,_,names,imports,exports=read_ue4_split_tables(path)
    unsupported(cls=='Material','Expected cooked Material')
    payload=Path(path).with_suffix('.uexp').read_bytes()
    root,= [(i,e) for i,e in enumerate(exports,1) if not e[2]]
    def properties(e):
        rows=read_records(Reader(payload[e[3]:e[3]+e[4]]),names)
        require(all(x.index==0 for x in rows) and len({x.name for x in rows})==len(rows),'Invalid material property identities')
        return {x.name:x for x in rows}
    p=properties(root[1]);expr=p.get('Expressions')
    unsupported(expr is not None and expr.kind=='ArrayProperty' and expr.parameters==('ObjectProperty',),'Cooked expression records unavailable')
    r=Reader(expr.data);indices=[r.i() for _ in range(r.count(4096))]
    require(r.pos==len(r.data) and len(set(indices))==len(indices),'Invalid expression array')
    expressions={}
    for i in indices:
        require(1<=i<=len(exports),'Invalid expression export index')
        e=exports[i-1];unsupported(e[0]=='MaterialExpressionTextureSample' and e[2]==root[0],'Unsupported cooked expression class or owner')
        q=properties(e);require(object_index(q,'Material')==root[0],'Invalid expression owner')
        tex=object_index(q,'Texture');require(-len(imports)<=tex<0,'Invalid texture import index')
        imp=imports[-tex-1];outer=imp[2]
        require(imp[1]=='Texture2D' and -len(imports)<=outer<0,'Invalid texture import')
        parent=imports[-outer-1];pkg=parent[3]
        require(parent[1]=='Package' and pkg.startswith(('/Game/','/Engine/')) and pkg.rsplit('/',1)[-1]==imp[3],'Invalid texture package identity')
        require(e[1] not in expressions,'Duplicate source expression name')
        expressions[e[1]]=dict(texture=pkg,sampler=name(q,'SamplerType',names,'SAMPLERTYPE_Color'))
    fields={'BaseColor':'ColorMaterialInput','Normal':'VectorMaterialInput','Opacity':'ScalarMaterialInput'}
    result={}
    for field,kind in fields.items():
        if field not in p: continue
        tag=p[field];unsupported(tag.kind=='StructProperty' and tag.parameters==(kind,),'Unsupported filtered material input type')
        r=Reader(tag.data);output=r.i();unsupported(r.i()==0,'Nonempty input name unsupported')
        mask=r.unpack('5i');source=r.name(names);use_constant=r.i();constant=r.take(12 if kind=='VectorMaterialInput' else 4)
        require(r.pos==len(r.data) and all(x in (0,1) for x in (*mask,use_constant)),'Invalid filtered material input extent or mask')
        unsupported(output==0 and mask==(1,1,1,1,0) and not use_constant,'Unsupported filtered output selection or constant')
        require(source in expressions,'Unknown source expression name')
        result[field]=dict(expression=source,output=output,mask=list(mask),**expressions[source])
    unsupported(bool(result),'No supported filtered surface edges')
    return dict(blend=name(p,'BlendMode',names,'BLEND_Opaque'),edges=result,shader_status='source_edges_only')
