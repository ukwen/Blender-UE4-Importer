"""UE texture coordinates are top-left-origin; imported Blender UVs invert V."""
import math


def uv_source(tree, index=0):
    name = f'UE explicit UV{index}'
    node = tree.nodes.get(name)
    if node is None:
        node = tree.nodes.new('ShaderNodeUVMap'); node.name = name; node.label = name
        node.uv_map = f'UV{index}'
        node.location = (-1000, -900 - 150 * index)
    return node.outputs[0]


def transform_uv(tree, source, scale, offset, label):
    node = tree.nodes.new('ShaderNodeVectorMath'); node.operation = 'MULTIPLY_ADD'
    node.label = label; node.hide = True
    node.inputs[1].default_value = scale; node.inputs[2].default_value = offset
    tree.links.new(source, node.inputs[0])
    return node.outputs[0]


def unreal_coordinates(tree, node, params):
    index = params.TryGetValue('CoordinateIndex', 0)
    u, v = params.TryGetValue('UTiling', 1), params.TryGetValue('VTiling', 1)
    if type(index) is not int or not 0 <= index < 8 or not all(math.isfinite(x) for x in (u,v)):
        raise ValueError('Invalid texture coordinate settings')
    if params.TryGetValue('UnMirrorU', False) or params.TryGetValue('UnMirrorV', False):
        tree['Error'] = True
    node.uv_map = f'UV{index}'
    # (u_B, v_B) -> (u_B * UTile, (1 - v_B) * VTile) in Unreal space.
    return transform_uv(tree, node.outputs[0], (u, -v, 0), (0, v, 0), 'UE texture coordinate (top-left)')


def texture_coordinates(tree, node, params):
    coordinates = params.TryGetValue('Coordinates')
    if coordinates is None or (getattr(coordinates, 'node', None) is None and getattr(coordinates, 'node_index', 0) == 0):
        tree.links.new(uv_source(tree), node.inputs['Vector'])
    # Explicit expression links are converted at the texture sampling boundary.


def sample_coordinates(tree, source):
    return transform_uv(tree, source, (1, -1, 0), (0, 1, 0), 'UE sample UV (bottom-left)')


def address_helper(node):
    helper = node.id_data.nodes.get(node.get('UE_address_helper', ''))
    return helper if helper and helper.type == 'GROUP' and helper.get('UE_owned_address') == node.name else None


def connect_sample(tree, node, source):
    helper = address_helper(node)
    tree.links.new(source, helper.inputs[0] if helper else node.inputs['Vector'])


def remove_address(node):
    import bpy
    tree = node.id_data
    helper = address_helper(node)
    if helper is None: return
    source = helper.inputs[0].links[0].from_socket if helper.inputs[0].is_linked else None
    value = tuple(helper.inputs[0].default_value)
    group = helper.node_tree
    tree.nodes.remove(helper)
    if source is not None: tree.links.new(source, node.inputs['Vector'])
    else: node.inputs['Vector'].default_value = value
    if group.users == 0: bpy.data.node_groups.remove(group)
    del node['UE_address_helper']


def mixed_address(node, x, y, width, height):
    """Base-level nearest/linear sampling; mip and anisotropic fidelity unverified."""
    import bpy
    tree = node.id_data
    source = node.inputs['Vector'].links[0].from_socket if node.inputs['Vector'].is_linked else None
    value = tuple(node.inputs['Vector'].default_value)
    group = bpy.data.node_groups.new('UE mixed texture address', 'ShaderNodeTree')
    for direction in ('INPUT', 'OUTPUT'):
        group.interface.new_socket(name='UV', in_out=direction, socket_type='NodeSocketVector')
    inp = group.nodes.new('NodeGroupInput'); out = group.nodes.new('NodeGroupOutput')
    split = group.nodes.new('ShaderNodeSeparateXYZ'); combine = group.nodes.new('ShaderNodeCombineXYZ')
    group.links.new(inp.outputs[0], split.inputs[0])
    def operation(op, src, arg):
        n = group.nodes.new('ShaderNodeMath'); n.operation = op
        group.links.new(src, n.inputs[0]); n.inputs[1].default_value = arg
        return n.outputs[0]
    for i, (mode, size) in enumerate(((x,width),(y,height))):
        coord = split.outputs[i]
        if mode == 'TA_Mirror': coord = operation('PINGPONG', coord, 1)
        if mode != 'TA_Wrap':
            # A repeat sampler blends across an edge; constrain to texel centers.
            half = .5/size
            coord = operation('MAXIMUM', coord, half)
            coord = operation('MINIMUM', coord, 1-half)
        group.links.new(coord, combine.inputs[i])
    group.links.new(split.outputs[2], combine.inputs[2]); group.links.new(combine.outputs[0], out.inputs[0])
    helper = tree.nodes.new('ShaderNodeGroup'); helper.node_tree = group; helper.hide = True
    helper.label = 'UE independent U/V address'; helper.location = node.location.copy(); helper.location.x -= 170
    helper['UE_owned_address'] = node.name; node['UE_address_helper'] = helper.name
    helper.inputs[0].default_value = value
    if source is not None: tree.links.new(source, helper.inputs[0])
    tree.links.new(helper.outputs[0], node.inputs['Vector'])


def set_address(node, image):
    remove_address(node)
    fallback = 'TA_Clamp' if image.get('clamp', False) else 'TA_Wrap'
    x, y = image.get('UE_address_x', fallback), image.get('UE_address_y', fallback)
    sampler = node.get('UE_sampler_source', 'SSM_FromTextureAsset')
    if sampler == 'SSM_Wrap_WorldGroupSettings': x = y = 'TA_Wrap'
    elif sampler == 'SSM_Clamp_WorldGroupSettings': x = y = 'TA_Clamp'
    elif sampler != 'SSM_FromTextureAsset': node.id_data['Error'] = True
    modes = {'TA_Wrap':'REPEAT', 'TA_Clamp':'EXTEND', 'TA_Mirror':'MIRROR'}
    if 'UE_address_approximation' in node: del node['UE_address_approximation']
    if 'UE_address_unsupported' in node: del node['UE_address_unsupported']
    if x not in modes or y not in modes or min(image.size) <= 0:
        node.id_data['Error'] = True
        node['UE_address_unsupported'] = f'{x}/{y}'
        node.extension = 'REPEAT'
    elif x != y:
        mixed_address(node, x, y, *image.size)
        node.extension = 'REPEAT'
        node['UE_address_approximation'] = 'Base-level nearest/linear; mip and anisotropic fidelity unverified'
    else:
        node.extension = modes[x]
    node['UE_address_x'] = x; node['UE_address_y'] = y
