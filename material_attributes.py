"""Editable UE4 surface-attribute bundles; not a generic shader closure or layer stack."""
PREFIX = 'MaterialExpression'
KINDS = tuple(PREFIX+n for n in ('MakeMaterialAttributes','BreakMaterialAttributes','BlendMaterialAttributes'))
# UE4 BreakMaterialAttributes first eight output indices. Keep both opacity fields distinct.
FIELDS = {'BaseColor': (0.,0.,0.), 'Metallic':0., 'Specular':.5, 'Roughness':.5,
          'EmissiveColor':(0.,0.,0.), 'Opacity':1., 'OpacityMask':1., 'Normal':(0.,0.,1.)}
UNSUPPORTED = ('WorldPositionOffset','WorldDisplacement','TessellationMultiplier','SubsurfaceColor',
               'ClearCoat','ClearCoatRoughness','AmbientOcclusion','Refraction','PixelDepthOffset',
               'CustomizedUVs','CustomData0','CustomData1','ShadingModel','Tangent','Anisotropy')


def fail(tree,node,message):
    tree['Error']=True
    node['UE_attribute_error']=message


def build(tree,data):
    import bpy
    kind=data.classname.removeprefix(PREFIX)
    p=data.export.properties
    group=bpy.data.node_groups.new('UE '+kind,'ShaderNodeTree')
    blend=kind=='BlendMaterialAttributes'
    make=kind=='MakeMaterialAttributes'
    def socket(name,direction,default):
        s=group.interface.new_socket(name=name,in_out=direction,socket_type='NodeSocketVector' if isinstance(default,tuple) else 'NodeSocketFloat')
        s.default_value=default
    for prefix in ('A.','B.') if blend else ('',):
        for key,value in FIELDS.items(): socket(prefix+key,'INPUT',value)
    if blend: socket('Alpha','INPUT',0.)
    for key,value in FIELDS.items(): socket(key,'OUTPUT',value)
    inp=group.nodes.new('NodeGroupInput'); out=group.nodes.new('NodeGroupOutput')
    mode=p.TryGetValue('PixelAttributeBlendType','Blend') if blend else 'Blend'
    mode={0:'Blend',1:'UseA',2:'UseB'}.get(mode,mode)
    mode=str(mode).split('::')[-1]
    for key,value in FIELDS.items():
        if not blend: src=inp.outputs[key]
        elif mode in ('UseA','UseB'): src=inp.outputs[mode[-1]+'.'+key]
        else:
            mix=group.nodes.new('ShaderNodeMix'); mix.data_type='VECTOR' if isinstance(value,tuple) else 'FLOAT'
            mix.factor_mode='UNIFORM'; mix.clamp_factor=False; mix.clamp_result=False
            vector=isinstance(value,tuple)
            group.links.new(inp.outputs['Alpha'],mix.inputs[0])
            group.links.new(inp.outputs['A.'+key],mix.inputs[4 if vector else 2])
            group.links.new(inp.outputs['B.'+key],mix.inputs[5 if vector else 3])
            src=mix.outputs[1 if vector else 0]
        group.links.new(src,out.inputs[key])
    node=tree.nodes.new('ShaderNodeGroup'); node.node_tree=group; node.name=data.export.object_name; node.label='UE '+kind
    data.node=node; data.attribute_kind=kind
    if kind!='BreakMaterialAttributes': data.attribute_bundle=True
    else: data.link_indirect=list(node.outputs)
    if blend and mode not in ('Blend','UseA','UseB'): fail(tree,node,'Unsupported pixel blend mode '+mode)
    if make:
        for key in set(UNSUPPORTED) | {k for k,v in p.items() if getattr(v,'struct_type',None)=='ExpressionInput' and k not in FIELDS}:
            prop=p.get(key)
            if prop is not None:
                val=getattr(prop,'material_input',None) or prop.value
                if getattr(val,'node',None) is not None or getattr(val,'node_index',0) or getattr(val,'use_constant',False):
                    fail(tree,node,'Unsupported connected attribute: '+key)
    return node


def bundle_source(nodes,prop):
    inp=prop.value if prop else None
    if inp is None or getattr(inp,'node',None) is None or inp.node_output_i!=0 or getattr(inp,'mask',0):
        raise ValueError('Expected unmasked material attribute bundle')
    src=nodes.get(inp.node.object_name)
    if src is None or not getattr(src,'attribute_bundle',False): raise ValueError('Unsupported material attribute source')
    return src.node.outputs


def connect(tree,nodes,data,link_socket):
    p=data.export.properties; node=data.node
    try:
        if data.attribute_kind=='MakeMaterialAttributes':
            for key in FIELDS:
                prop=p.get(key)
                if prop is not None: link_socket(tree,nodes,data,prop,key,key)
        elif data.attribute_kind=='BreakMaterialAttributes':
            src=bundle_source(nodes,p.get('MaterialAttributes'))
            for key in FIELDS: tree.links.new(src[key],node.inputs[key])
        else:
            for branch in ('A','B'):
                src=bundle_source(nodes,p.get(branch))
                for key in FIELDS: tree.links.new(src[key],node.inputs[branch+'.'+key])
            if p.get('Alpha'): link_socket(tree,nodes,data,p['Alpha'],'Alpha','Alpha')
    except (KeyError,AttributeError,ValueError,IndexError) as exc: fail(tree,node,str(exc))


def connect_surface(tree,nodes,data):
    p=data.export.properties; shader=data.node
    try:
        src=bundle_source(nodes,p.get('MaterialAttributes'))
        mapping={'BaseColor':'Base Color','Metallic':'Metallic','Specular':'Specular IOR Level',
                 'Roughness':'Roughness','EmissiveColor':'Emission Color','Normal':'Normal'}
        mode=p.TryGetValue('BlendMode','BLEND_Opaque')
        if mode=='BLEND_Masked': mapping['OpacityMask']='Alpha'
        elif mode=='BLEND_Translucent': mapping['Opacity']='Alpha'
        elif mode!='BLEND_Opaque': fail(tree,shader,'Unsupported attribute blend mode '+mode)
        for key,dst in mapping.items():
            target=(data.input_remap or {}).get(key,shader.inputs[dst])
            tree.links.new(src[key],target)
        shader.inputs['Emission Strength'].default_value=1
    except (KeyError,AttributeError,ValueError,IndexError) as exc: fail(tree,shader,str(exc))
