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


def set_address(node, image):
    fallback = 'TA_Clamp' if image.get('clamp', False) else 'TA_Wrap'
    x, y = image.get('UE_address_x', fallback), image.get('UE_address_y', fallback)
    sampler = node.get('UE_sampler_source', 'SSM_FromTextureAsset')
    if sampler == 'SSM_Wrap_WorldGroupSettings': x = y = 'TA_Wrap'
    elif sampler == 'SSM_Clamp_WorldGroupSettings': x = y = 'TA_Clamp'
    elif sampler != 'SSM_FromTextureAsset': node.id_data['Error'] = True
    modes = {'TA_Wrap':'REPEAT', 'TA_Clamp':'EXTEND', 'TA_Mirror':'MIRROR'}
    if x != y or x not in modes:
        node.id_data['Error'] = True
        node['UE_address_unsupported'] = f'{x}/{y}'
        node.extension = 'REPEAT'
    else:
        if 'UE_address_unsupported' in node: del node['UE_address_unsupported']
        node.extension = modes[x]
    node['UE_address_x'] = x; node['UE_address_y'] = y
