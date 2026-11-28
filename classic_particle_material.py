"""Typed classic 508 particle surface graphs; no particle runtime evaluation.

FExpressionInput layout: original 508 editor assets and MIT UAssetAPI
MaterialInputProperties reference (see third_party/UAssetAPI-LICENSE.txt).
The renderer consumes the same graph contract as the modern preview reader.
"""
import math
import struct
from classic_material import (require, unsupported, property_map, name, integer,
                              scalar, boolean, linear_color, object_index)
from package_records import read_package, ExportRecord, ImportRecord
from skeleton_native import Reader

PROFILE = 'ue4_508_particle_graph'


def read_edge(reader):
    index, output = reader.unpack('2i')
    count = reader.i()
    require(abs(count) <= 4096, 'Expression input name exceeds limit')
    nm = ''
    if count:
        width = 1 if count > 0 else 2
        raw = reader.take(abs(count)*width)
        require(raw.endswith(bytes(width)), 'Missing expression input name terminator')
        nm = raw[:-width].decode('utf-8' if width == 1 else 'utf-16-le')
    mask = list(reader.unpack('5i'))
    require(index >= 0 and (0 <= output <= 4 or index == 0 and output == -1)
            and all(v in (0,1) for v in mask), 'Invalid particle expression link')
    return dict(index=index, output=output, mask=mask, input_name=nm)


def surface(record):
    require(record.kind == 'StructProperty', 'Invalid surface property')
    unsupported(record.parameters in (('ColorMaterialInput',), ('ScalarMaterialInput',)),
                'Unsupported particle surface input')
    r = Reader(record.data)
    edge = read_edge(r)
    use = r.i()
    require(use in (0,1), 'Invalid surface constant flag')
    if record.parameters == ('ColorMaterialInput',):
        b,g,red,a = r.unpack('4B')
        def linear(v):
            v /= 255
            return v/12.92 if v <= .04045 else ((v+.055)/1.055)**2.4
        value = [linear(red),linear(g),linear(b),a/255]
    else:
        value = [r.unpack('f')[0]]
    require(r.pos == len(record.data) and all(map(math.isfinite,value)), 'Invalid surface extent or value')
    return dict(edge,use_constant=use,constant=value)


def read_graph(path):
    meta, raw, table = read_package(path)
    unsupported(meta['ue4']==508 and meta['ue5'] is None and meta['licensee']==0,
                'Unsupported particle material package profile')
    names = table.names
    roots = [(i,e) for i,e in enumerate(table.exports,1) if e.kind=='Material' and not e.outer]
    unsupported(len(roots)==1,'Expected one classic particle material')
    owner, entry = roots[0]
    p = property_map(raw,entry,names)
    shading = name(p,'ShadingModel',names,'MSM_DefaultLit')
    blend = name(p,'BlendMode',names,'BLEND_Opaque')
    surface_keys = {'BaseColor','EmissiveColor','Opacity'}
    metadata = {'Expressions','StateId','ThumbnailInfo','LightingGuid','bCanMaskedBeAssumedOpaque',
                'ReferencedTextureGuids','BlendMode','ShadingModel','MaterialDomain','TwoSided',
                'EditorX','EditorY','EditorComments','bUseMaterialAttributes'}
    unsupported(blend=='BLEND_Translucent' and shading in ('MSM_Unlit','MSM_DefaultLit')
                and name(p,'MaterialDomain',names,'MD_Surface')=='MD_Surface'
                and not boolean(p,'bUseMaterialAttributes'), 'Unsupported classic particle surface semantics')
    unsupported(all(k in surface_keys|metadata or k.startswith('bUsedWith') for k in p),
                'Unsupported particle material properties')
    expr = p.get('Expressions')
    require(expr is not None and expr.kind=='ArrayProperty' and expr.parameters==('ObjectProperty',),
            'Missing expression array')
    r = Reader(expr.data)
    refs = [r.i() for _ in range(r.count(4096))]
    require(r.pos==len(expr.data) and len(set(refs))==len(refs),'Invalid expression list')
    nodes = {}
    common = {'Material','MaterialExpressionEditorX','MaterialExpressionEditorY','MaterialExpressionGuid','Desc'}
    for i in refs:
        e = table.reference(i)
        require(isinstance(e,ExportRecord) and e.outer==owner and e.kind.startswith('MaterialExpression'), 'Invalid particle expression ownership')
        kind = e.kind.removeprefix('MaterialExpression')
        q = property_map(raw,e,names)
        node = dict(kind=kind,name=e.name,parameter='',position=[integer(q,'MaterialExpressionEditorX'),integer(q,'MaterialExpressionEditorY')],inputs={})
        if kind=='ParticleColor':
            allowed=set()
        elif kind=='Constant3Vector':
            allowed={'Constant'};node['value']=list(linear_color(q,'Constant'))
        elif kind=='Multiply':
            allowed={'A','B','ConstA','ConstB'};node['defaults']={k:scalar(q,'Const'+k,1.) for k in ('A','B')}
            for key in ('A','B'):
                if key not in q:continue
                v=q[key];require(v.kind=='StructProperty' and v.parameters==('ExpressionInput',),'Invalid multiply input')
                rd=Reader(v.data);node['inputs'][key]=read_edge(rd);require(rd.pos==len(v.data),'Trailing expression input data')
        elif kind=='TextureSample':
            allowed={'Texture','SamplerType','SamplerSource'}
            j=object_index(q,'Texture');ref=table.reference(j);pkg=table.package(j)
            require(isinstance(ref,ImportRecord) and ref.kind=='Texture2D' and pkg,'Invalid particle texture binding')
            node.update(texture=pkg,sampler_type=name(q,'SamplerType',names,'SAMPLERTYPE_Color'),sampler_source=name(q,'SamplerSource',names,'SSM_FromTextureAsset'))
        else:
            raise NotImplementedError('Unsupported classic particle expression '+kind)
        unsupported(set(q)<=common|allowed,'Unsupported classic particle expression properties')
        nodes[i]=node
    unsupported(any(n['kind']=='ParticleColor' for n in nodes.values()),'Expected particle color graph')
    outputs={k:surface(p[k]) for k in sorted(surface_keys) if k in p}
    require(all(not a['index'] or a['index'] in nodes for a in outputs.values()),'Surface link outside particle graph')
    require(all(not a['index'] or a['index'] in nodes for n in nodes.values() for a in n['inputs'].values()),'Expression link outside particle graph')
    unsupported({'Opacity','EmissiveColor' if shading=='MSM_Unlit' else 'BaseColor'}<=outputs.keys(), 'Missing particle surface branches')
    return dict(name=entry.name,kind='material',source_profile=PROFILE,blend=blend,
                shading_model=shading,shading_model_field=1 if shading=='MSM_Unlit' else 2,
                material_domain='MD_Surface',two_sided=boolean(p,'TwoSided'),tangent_space_normal=True,
                nodes=nodes,outputs=outputs,unsupported=[])
