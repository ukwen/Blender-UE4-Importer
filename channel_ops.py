"""Typed channel operations, preserving numeric channels (float1/2/3).
Four-channel append results carry separate scalar outputs and may only feed
another typed channel operation; never coerce them to a Blender vector.
"""


def mask_indices(props):
    return tuple(i for i,k in enumerate('RGBA') if props.TryGetValue(k, False))


def plan(exp, stack=()):
    from typed_switch import input_width
    p=exp.properties
    if exp.export_class_type == 'MaterialExpressionAppendVector':
        a,b=(input_width(p.TryGetValue(k),stack) for k in ('A','B'))
        if a is None or b is None or a+b>4: return None
        return (a+b, [('A',i) for i in range(a)]+[('B',i) for i in range(b)])
    width=input_width(p.TryGetValue('Input'),stack)
    indices=mask_indices(p)
    if width is None or not indices or max(indices)>=width: return None
    return len(indices), [('Input',i) for i in indices]


def build(tree, data, spec):
    import bpy
    width, channels=spec
    group=bpy.data.node_groups.new('UE '+data.classname.removeprefix('MaterialExpression'), 'ShaderNodeTree')
    for name,index in channels:
        group.interface.new_socket(name=name+'.'+'RGBA'[index],in_out='INPUT',socket_type='NodeSocketFloat')
    if width<4:
        group.interface.new_socket(name='Result',in_out='OUTPUT',socket_type='NodeSocketFloat' if width==1 else 'NodeSocketVector')
    for i in range(width): group.interface.new_socket(name='RGBA'[i],in_out='OUTPUT',socket_type='NodeSocketFloat')
    inp=group.nodes.new('NodeGroupInput'); out=group.nodes.new('NodeGroupOutput')
    for i in range(width): group.links.new(inp.outputs[i],out.inputs[i+(width<4)])
    if width==1: group.links.new(inp.outputs[0],out.inputs[0])
    elif width<4:
        combine=group.nodes.new('ShaderNodeCombineXYZ')
        for i in range(width): group.links.new(inp.outputs[i],combine.inputs[i])
        group.links.new(combine.outputs[0],out.inputs[0])
    node=tree.nodes.new('ShaderNodeGroup'); node.node_tree=group; node.name=data.export.object_name
    node.label='UE '+data.classname.removeprefix('MaterialExpression'); node['UE_channel_width']=width
    data.node=node; data.channel_spec=spec; data.channel_sockets=list(node.outputs)[int(width<4):]
    data.link_indirect=[node.outputs[0]] if width<4 else []
    return node


def source_channels(tree, nodes, inp):
    from typed_switch import expression_width
    data=nodes[inp.node.object_name]; width=expression_width(inp.node,inp.node_output_i)
    if width is None: raise ValueError('Unknown channel source width')
    if hasattr(data,'channel_sockets'):
        result=data.channel_sockets
    else:
        outputs=data.link_indirect or data.node.outputs
        if inp.node_output_i>=len(outputs): raise ValueError('Missing channel output')
        src=outputs[inp.node_output_i]
        if width==1:
            if src.type!='VALUE': raise ValueError('Expected numeric scalar')
            result=[src]
        elif width<=3:
            split=tree.nodes.new('ShaderNodeSeparateXYZ'); split.hide=True
            tree.links.new(src,split.inputs[0]); result=list(split.outputs)[:width]
        else: raise ValueError('Unknown float4 representation')
    if getattr(inp,'mask',0):
        ids=[i for i,v in enumerate(inp.mask_rgba) if v]
        # UE individual output socket already selects its component.
        if width==1 and len(ids)==1: return result
        if not ids or max(ids)>=width: raise ValueError('Invalid source mask')
        result=[result[i] for i in ids]
    return result


def connect(tree,nodes,data):
    try:
        inputs={}
        for i,(name,index) in enumerate(data.channel_spec[1]):
            if name not in inputs: inputs[name]=source_channels(tree,nodes,data.export.properties.TryGetValue(name))
            tree.links.new(inputs[name][index],data.node.inputs[i])
    except (KeyError,IndexError,AttributeError,ValueError) as exc:
        tree['Error']=True; data.node['UE_channel_error']=str(exc)
