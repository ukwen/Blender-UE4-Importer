"""Opt-in direct UV0 surface preview for positively identified UE4.18 edges.

This is a Blender approximation, not an Unreal shading-model emulator.
Raw dependency images remain unchanged; color/normal variants are separate.
"""
from pathlib import Path
from cooked_material_dependencies import inspect_asset
from project_geometry import read_ue4_split_tables
from skeleton_native import Reader
from ue4_property_records import read_records


def texture_srgb(path, expected):
    cls,_=inspect_asset(path,'4.18',expected)
    if cls!='Texture2D': raise ValueError('Expected Texture2D')
    _,_,names,_,exports=read_ue4_split_tables(path)
    root,=[e for e in exports if not e[2]]
    payload=Path(path).with_suffix('.uexp').read_bytes()
    rows=[r for r in read_records(Reader(payload[root[3]:root[3]+root[4]]),names) if r.name=='SRGB']
    if not rows: return True # UE4 Texture default
    if len(rows)!=1 or rows[0].index or rows[0].kind!='BoolProperty': raise ValueError('Invalid SRGB property')
    return rows[0].boolean


def validate_preview(graph, nodes, project):
    """Fail closed before allocating preview nodes or derived images."""
    edges=graph['edges']
    expected={'BaseColor':('SAMPLERTYPE_Color','PF_DXT1',True),
              'Normal':('SAMPLERTYPE_Normal','PF_BC5',False),
              'Opacity':('SAMPLERTYPE_Color','PF_BC4',False)}
    if graph['blend']!='BLEND_Translucent' or set(edges)!=set(expected) or not graph.get('direct_uv0_preview_eligible'):
        raise NotImplementedError('Only direct UV0 translucent RGB/BC5/BC4 source edges are supported')
    result={}
    for field,(sampler,fmt,srgb) in expected.items():
        edge=edges[field]; ref=edge['texture']; matches=[n for n in nodes if n.type=='TEX_IMAGE' and n.get('UE_texture_package')==ref]
        if edge['sampler']!=sampler or edge['mask']!=[1,1,1,1,0] or edge['output']!=0 or len(matches)!=1:
            raise NotImplementedError('Unsupported or ambiguous source input: '+field)
        raw=matches[0].image
        if raw is None or not raw.packed_file or raw.get('UE_texture_format')!=fmt:
            raise NotImplementedError('Missing or unsupported source texture: '+field)
        path=Path(project.resolve_package(ref))
        if texture_srgb(path,ref)!=srgb:
            raise NotImplementedError('Unexpected source color space: '+field)
        result[field]=(matches[0],path)
    return result


def build_preview(material, project, graph):
    import bpy
    from texture_blender import load_native_texture
    from project_session import digest
    tree=material.node_tree; nodes=tree.nodes; links=tree.links
    try: inputs=validate_preview(graph,nodes,project)
    except (ValueError,NotImplementedError,OSError) as exc:
        material['UE_cooked_preview_issue']=str(exc);return False
    def node(kind,label,x,y):
        n=nodes.new(kind);n.label=label;n.location=(x,y);return n
    def variant(field,srgb,normal,y):
        raw,path=inputs[field];key=digest([raw.image['UE_raw_texture_key'],srgb,normal,'direct_uv0_preview_v1'])
        im=next((i for i in bpy.data.images if i.get('UE_cooked_preview_key')==key and i.packed_file and i.colorspace_settings.name==('sRGB' if srgb else 'Non-Color')),None)
        if im is None:
            im=load_native_texture(path,'4.18',srgb=srgb,normal=normal);im['UE_cooked_preview_key']=key;im['UE_texture_package']=raw['UE_texture_package']
        n=node('ShaderNodeTexImage',field+' — interpreted preview',-630,y);n.image=im;n['UE_preview_input']=field
        return n
    uv=node('ShaderNodeUVMap','Source UV0',-900,300);uv.uv_map='UV0'
    base=variant('BaseColor',True,False,300);normal=variant('Normal',False,True,-30)
    opacity=node('ShaderNodeTexImage','Opacity — linear BC4',-630,-420);opacity.image=inputs['Opacity'][0].image;opacity['UE_preview_input']='Opacity'
    for n in (base,normal,opacity):links.new(uv.outputs['UV'],n.inputs['Vector'])
    sep=node('ShaderNodeSeparateColor','BC4 red channel',-300,-420);links.new(opacity.outputs['Color'],sep.inputs['Color'])
    split=node('ShaderNodeSeparateColor','BC5 reconstructed RGB',-360,-30);links.new(normal.outputs['Color'],split.inputs['Color'])
    flip=node('ShaderNodeMath','DirectX green convention preview',-140,-85);flip.operation='SUBTRACT';flip.inputs[0].default_value=1;links.new(split.outputs['Green'],flip.inputs[1])
    combine=node('ShaderNodeCombineColor','Tangent normal RGB',60,-30)
    for a,b in ((split.outputs['Red'],'Red'),(flip.outputs[0],'Green'),(split.outputs['Blue'],'Blue')):links.new(a,combine.inputs[b])
    nm=node('ShaderNodeNormalMap','Tangent basis preview',260,-30);nm.uv_map='UV0';links.new(combine.outputs['Color'],nm.inputs['Color'])
    bsdf=node('ShaderNodeBsdfPrincipled','Approximate translucent surface',480,300)
    links.new(base.outputs['Color'],bsdf.inputs['Base Color']);links.new(sep.outputs['Red'],bsdf.inputs['Alpha']);links.new(nm.outputs['Normal'],bsdf.inputs['Normal'])
    output=node('ShaderNodeOutputMaterial','Blender preview',830,300);links.new(bsdf.outputs['BSDF'],output.inputs['Surface'])
    material.surface_render_method='DITHERED'
    material['UE_material_status']='partial_surface_preview';material['UE_editor_material_status']='cooked_partial_surface_preview'
    material['UE_cooked_preview_issue']='Unreal translucency lighting, default surface terms, tangent basis and render equivalence unresolved; green inversion is a preview convention.'
    return True
