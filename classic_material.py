"""Independent basic UE4.14 surface material reader and Blender translator.

Native FExpressionInput layout follows the MIT UAssetAPI MaterialInputProperties
reference and original 508 editor packages. This intentionally supports only
explicit simple surfaces, not arbitrary material functions or runtime effects.
"""
from dataclasses import dataclass
import json
import math
import struct
from package_records import read_package, ExportRecord, ImportRecord
from skeleton_native import Reader
from ue4_property_records import read_records

SURFACE={'BaseColor':'Base Color','Metallic':'Metallic','Specular':'Specular IOR Level',
         'Roughness':'Roughness','EmissiveColor':'Emission Color','Opacity':'Alpha','OpacityMask':'Alpha'}
KINDS={'MaterialExpressionConstant','MaterialExpressionConstant3Vector','MaterialExpressionVectorParameter','MaterialExpressionTextureSample'}


def require(ok,message):
    if not ok:raise ValueError(message)


def unsupported(ok,message):
    if not ok:raise NotImplementedError(message)


def property_map(raw,entry,names):
    records=read_records(Reader(raw[entry.offset:entry.offset+entry.size]),names)
    unsupported(all(v.index==0 for v in records),'Indexed classic material properties')
    return {v.name:v for v in records}


def scalar(p,key,default=0.):
    if key not in p:return default
    v=p[key];require(v.kind=='FloatProperty' and len(v.data)==4,'Invalid material scalar '+key)
    x=struct.unpack('<f',v.data)[0];require(math.isfinite(x),'Nonfinite material scalar '+key);return x


def integer(p,key,default=0):
    if key not in p:return default
    v=p[key];require(v.kind=='IntProperty' and len(v.data)==4,'Invalid material integer '+key)
    return struct.unpack('<i',v.data)[0]


def name(p,key,names,default):
    if key not in p:return default
    v=p[key];require(v.kind in ('ByteProperty','NameProperty','EnumProperty') and len(v.data)==8,'Invalid material name '+key)
    return Reader(v.data).name(names)


def boolean(p,key,default=False):
    if key not in p:return default
    require(p[key].kind=='BoolProperty','Invalid material boolean '+key);return p[key].boolean


def linear_color(p,key):
    v=p.get(key)
    if v is None:return (0.,0.,0.,1.)
    require(v.kind=='StructProperty' and v.parameters==('LinearColor',) and len(v.data)==16,'Invalid material color '+key)
    values=struct.unpack('<4f',v.data);require(all(map(math.isfinite,values)),'Nonfinite material color');return values


def object_index(p,key):
    v=p.get(key)
    if v is None:return 0
    require(v.kind=='ObjectProperty' and len(v.data)==4,'Invalid material reference '+key)
    return struct.unpack('<i',v.data)[0]


def surface_input(record):
    unsupported(record.kind=='StructProperty' and record.parameters in (('ColorMaterialInput',),('ScalarMaterialInput',)),'Unsupported classic surface input type '+record.name)
    r=Reader(record.data);index,output=r.unpack('2i');n=r.i()
    require(abs(n)<=4096,'Material input name too large')
    if n:
        raw=r.take(n if n>0 else -2*n);term=bytes(1 if n>0 else 2)
        require(raw.endswith(term),'Invalid input name');raw[:-len(term)].decode('utf8' if n>0 else 'utf-16-le')
    mask=r.unpack('5i');use=r.i()
    require(index>=0 and (0<=output<=4 or index==0 and output==-1) and all(v in (0,1) for v in (*mask,use)),'Invalid material input')
    if record.parameters==('ColorMaterialInput',):
        b,g,red,a=r.unpack('4B')
        def linear(v):
            v=v/255;return v/12.92 if v<=.04045 else ((v+.055)/1.055)**2.4
        constant=(linear(red),linear(g),linear(b),a/255)
    else:constant=r.unpack('f')[0];require(math.isfinite(constant),'Nonfinite input constant')
    require(r.pos==len(record.data),'Unexpected material input trailer')
    return dict(index=index,output=output,mask=mask,use_constant=bool(use),constant=constant)


def read_material(path):
    meta,raw,table=read_package(path)
    unsupported(meta['ue4']==508 and meta['ue5'] is None and meta['licensee']==0,'Unsupported classic material package')
    roots=[(i,e) for i,e in enumerate(table.exports,1) if not e.outer and e.kind=='Material']
    unsupported(len(roots)==1,'Expected a simple classic material root')
    index,entry=roots[0];p=property_map(raw,entry,table.names)
    blend=name(p,'BlendMode',table.names,'BLEND_Opaque')
    unsupported(blend in ('BLEND_Opaque','BLEND_Translucent','BLEND_Masked') and name(p,'ShadingModel',table.names,'MSM_DefaultLit')=='MSM_DefaultLit' and name(p,'MaterialDomain',table.names,'MD_Surface')=='MD_Surface' and not boolean(p,'bUseMaterialAttributes'),'Unsupported classic surface semantics')
    allowed={'Expressions','StateId','ThumbnailInfo','LightingGuid','BaseColor','Roughness','Metallic','Specular','EmissiveColor','Opacity','OpacityMask','bCanMaskedBeAssumedOpaque','ReferencedTextureGuids','BlendMode','ShadingModel','MaterialDomain','bUseMaterialAttributes','TwoSided','OpacityMaskClipValue','EditorX','EditorY','EditorComments'}
    unsupported(all(k in allowed or k.startswith('bUsedWith') for k in p),'Unsupported classic material fields: '+', '.join(sorted(k for k in p if k not in allowed and not k.startswith('bUsedWith'))))
    expr=p.get('Expressions');require(expr is not None and expr.kind=='ArrayProperty' and expr.parameters==('ObjectProperty',),'Missing material expression array')
    r=Reader(expr.data);refs=[r.i() for _ in range(r.count(4096))];require(r.pos==len(expr.data) and len(set(refs))==len(refs),'Invalid expression array')
    nodes={}
    for i in refs:
        e=table.reference(i);require(isinstance(e,ExportRecord) and e.outer==index,'Material expression outside root')
        unsupported(e.kind in KINDS,'Unsupported classic expression '+e.kind)
        props=property_map(raw,e,table.names)
        common={'Material','MaterialExpressionEditorX','MaterialExpressionEditorY','MaterialExpressionGuid','ExpressionGUID','Desc'}
        node=dict(name=e.name,kind=e.kind,position=(integer(props,'MaterialExpressionEditorX'),-integer(props,'MaterialExpressionEditorY')))
        if e.kind=='MaterialExpressionConstant':
            unsupported(set(props)<=common|{'R'},'Unsupported scalar expression fields');node['value']=scalar(props,'R')
        elif e.kind in ('MaterialExpressionConstant3Vector','MaterialExpressionVectorParameter'):
            key='Constant' if e.kind.endswith('Constant3Vector') else 'DefaultValue'
            unsupported(set(props)<=common|{key,'ParameterName','Group','SortPriority'},'Unsupported color expression fields');node['value']=linear_color(props,key)
        else:
            unsupported(set(props)<=common|{'Texture','SamplerType','SamplerSource'},'Unsupported texture expression fields')
            tex=object_index(props,'Texture');ref=table.reference(tex);pkg=table.package(tex)
            require(isinstance(ref,ImportRecord) and ref.kind=='Texture2D' and pkg,'Invalid material texture reference')
            sampler=name(props,'SamplerType',table.names,'SAMPLERTYPE_Color')
            unsupported(sampler in ('SAMPLERTYPE_Color','SAMPLERTYPE_LinearColor','SAMPLERTYPE_Grayscale','SAMPLERTYPE_LinearGrayscale','SAMPLERTYPE_Masks'),'Unsupported texture sampler '+sampler)
            node.update(texture=pkg,sampler=sampler,sampler_source=name(props,'SamplerSource',table.names,'SSM_FromTextureAsset'))
        nodes[i]=node
    outputs={k:surface_input(p[k]) for k in SURFACE if k in p}
    require(all(not a['index'] or a['index'] in nodes for a in outputs.values()),'Material surface points outside expression list')
    unsupported(not ('Opacity' in outputs and 'OpacityMask' in outputs),'Ambiguous opacity bindings')
    return dict(name=entry.name,blend=blend,two_sided=boolean(p,'TwoSided'),clip=scalar(p,'OpacityMaskClipValue',.333333),clip_serialized='OpacityMaskClipValue' in p,nodes=nodes,outputs=outputs,position=(integer(p,'EditorX'),-integer(p,'EditorY')))


def build_material(project,path,data):
    import bpy
    from texture_blender import load_editor_texture
    from uv_semantics import uv_source,set_address
    from surface_semantics import set_opacity_clip
    material=bpy.data.materials.new(data['name']);material.use_nodes=True;material['UAsset']=str(path)
    tree=material.node_tree;bs=next(n for n in tree.nodes if n.type=='BSDF_PRINCIPLED');bs.location=data['position'];bs.inputs['Base Color'].default_value=(0,0,0,1)
    material.use_backface_culling=not data['two_sided'];material.surface_render_method='BLENDED' if data['blend']=='BLEND_Translucent' else 'DITHERED'
    if data['blend']=='BLEND_Translucent':
        bs.inputs['Transmission Weight'].default_value=1.;material['UE_BlendModeApproximation']='Principled alpha/transmission preview; no Unreal blend parity'
    sockets={}
    for index,d in data['nodes'].items():
        kind=d['kind'];value=d.get('value')
        if kind=='MaterialExpressionConstant':
            n=tree.nodes.new('ShaderNodeValue');n.outputs[0].default_value=value;sockets[index]=(n.outputs[0],)
        elif kind in ('MaterialExpressionConstant3Vector','MaterialExpressionVectorParameter'):
            n=tree.nodes.new('ShaderNodeRGB');n.outputs[0].default_value=value
            rgb=tree.nodes.new('ShaderNodeSeparateColor');rgb.mode='RGB';rgb.hide=True;tree.links.new(n.outputs[0],rgb.inputs[0]);a=tree.nodes.new('ShaderNodeValue');a.outputs[0].default_value=value[3];a.hide=True
            sockets[index]=(n.outputs[0],*rgb.outputs[:3],a.outputs[0])
        else:
            n=tree.nodes.new('ShaderNodeTexImage');n.name=d['name'];n.image=load_editor_texture(project.resolve_package(d['texture']));n['UE_texture_package']=d['texture'];n['UE_sampler_source']=d['sampler_source'];n.interpolation='Closest' if n.image.get('nearest') else 'Linear';tree.links.new(uv_source(tree),n.inputs['Vector']);set_address(n,n.image)
            rgb=tree.nodes.new('ShaderNodeSeparateColor');rgb.mode='RGB';rgb.hide=True;tree.links.new(n.outputs['Color'],rgb.inputs[0]);sockets[index]=(n.outputs['Color'],*rgb.outputs[:3],n.outputs['Alpha'])
        n.name=d['name'];n.label=kind.removeprefix('MaterialExpression');n.location=d['position'];n['UE_expression_index']=index
    for field,a in data['outputs'].items():
        dst=bs.inputs[SURFACE[field]]
        if a['use_constant']:
            dst.default_value=a['constant']
            if field=='EmissiveColor':bs.inputs['Emission Strength'].default_value=1.
            continue
        if not a['index']:continue
        available=sockets[a['index']];out=a['output'];require(0<=out<len(available),'Invalid expression output');src=available[out]
        if a['mask'][0]:
            mask=a['mask'][1:]
            if sum(mask)==1:
                channel=mask.index(1)+1
                require(out in (0,channel) and channel<len(available),'Inconsistent material channel mask');src=available[channel]
            else:require(mask in ((1,1,1,0),(1,1,1,1)) and out==0 and src.type=='RGBA','Unsupported material channel mask')
        tree.links.new(src,dst)
        if field=='EmissiveColor':bs.inputs['Emission Strength'].default_value=1.
    if data['blend']=='BLEND_Masked':
        set_opacity_clip(material,data['clip']);material['UE_mask_clip_source']='serialized' if data['clip_serialized'] else 'preview_default_not_serialized'
    material['UE_classic_material_profile']='typed_508_basic_surface'
    material['UE_classic_material_graph']=json.dumps(data,sort_keys=True)
    return material
