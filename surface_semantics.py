"""Material surface input helpers for Blender 4.2; do not silently change channels."""


def constant_value(inp):
    v = inp.constant
    if hasattr(v, 'b') and hasattr(v, 'a'):
        # FColor uses sRGB bytes; convert RGB to linear, leave alpha linear.
        def linear(x):
            x = x / 255
            return x / 12.92 if x <= .04045 else ((x + .055) / 1.055) ** 2.4
        return (linear(v.r), linear(v.g), linear(v.b), v.a / 255)
    if hasattr(v, 'ToVector'):
        return tuple(v.ToVector())
    if hasattr(v, 'ToTuple'):
        return tuple(v.ToTuple())
    return v


def masked_socket(tree, src, inp, indirect):
    if not getattr(inp, 'mask', 0):
        return src
    mask = tuple(bool(x) for x in inp.mask_rgba)
    if mask == (True, True, True, False):
        if src.type in ('RGBA', 'VECTOR'): return src
        raise ValueError('RGB mask on scalar output')
    if mask == (True, True, True, True) and src.type == 'RGBA': return src
    if sum(mask) != 1:
        raise NotImplementedError('Unsupported multi-channel swizzle')
    channel = mask.index(True)
    # The RGBA helper exposes explicit named channels. A mask on an already
    # scalar channel must not be interpreted as a second channel extraction.
    if src.type == 'VALUE':
        if src.name in ('R', 'G', 'B', 'A') and src.name != 'RGBA'[channel]:
            raise ValueError('Mask conflicts with selected output')
        if src.name in ('R', 'G', 'B', 'A') or channel == 0: return src
        raise ValueError('Mask requires a channel absent from scalar output')
    if indirect:
        expected = 'RGBA'[channel]
        matches = [s for s in indirect if s.name == expected and s.type == 'VALUE']
        if len(matches) == 1: return matches[0]
    if channel == 3 and src.type != 'RGBA': raise ValueError('No alpha channel in source')
    if channel == 3: raise NotImplementedError('RGBA output has no explicit alpha socket')
    split = tree.nodes.new('ShaderNodeSeparateXYZ')
    split.label = 'UE channel mask ' + 'RGB'[channel]
    tree.links.new(src, split.inputs[0])
    return split.outputs[channel]


def set_opacity_clip(mat, threshold):
    """Exact binary opacity test for the supported surface mask; no engine render equivalence claim."""
    import math
    if not isinstance(threshold, (float, int)) or not math.isfinite(threshold) or not 0 <= threshold <= 1:
        raise ValueError('Invalid opacity clip threshold')
    tree = mat.node_tree
    shader = tree.nodes['Principled BSDF']
    alpha = shader.inputs['Alpha']
    clip = tree.nodes.get('UE_OpacityClip')
    if clip is None:
        source = alpha.links[0].from_socket if alpha.is_linked else None
        value = alpha.default_value
        clip = tree.nodes.new('ShaderNodeMath')
        clip.name = 'UE_OpacityClip'
        clip.label = 'Unreal opacity mask (>= clip)'
        # LESS_THAN followed by SUBTRACT implements >=, including equality.
        clip.operation = 'LESS_THAN'
        clip.inputs[0].default_value = value
        if source is not None: tree.links.new(source, clip.inputs[0])
        invert = tree.nodes.new('ShaderNodeMath')
        invert.name = 'UE_OpacityVisible'
        invert.operation = 'SUBTRACT'
        invert.inputs[0].default_value = 1
        tree.links.new(clip.outputs[0], invert.inputs[1])
        tree.links.new(invert.outputs[0], alpha)
    clip.inputs[1].default_value = threshold
    mat['UE_opacity_mask_clip'] = threshold
    mat.surface_render_method = 'DITHERED'


def clear_opacity_clip(mat):
    tree = mat.node_tree
    clip = tree.nodes.get('UE_OpacityClip')
    invert = tree.nodes.get('UE_OpacityVisible')
    if clip is None or invert is None: return
    src = clip.inputs[0].links[0].from_socket if clip.inputs[0].is_linked else None
    val = clip.inputs[0].default_value
    tree.nodes.remove(invert)
    tree.nodes.remove(clip)
    alpha = tree.nodes['Principled BSDF'].inputs['Alpha']
    alpha.default_value = val
    if src is not None: tree.links.new(src, alpha)
    if 'UE_opacity_mask_clip' in mat: del mat['UE_opacity_mask_clip']
