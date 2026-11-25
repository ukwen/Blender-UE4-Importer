"""Conservative width inference for static switch expressions (UE float1/2/3)."""


def input_width(inp, stack=()):
    if inp is None or getattr(inp, 'node', None) is None:
        return None
    if getattr(inp, 'mask', 0):
        mask = tuple(bool(v) for v in inp.mask_rgba)
        # Match supported expression-link masks. Do not infer unsupported swizzles.
        if sum(mask) == 1: return 1
        if mask == (True, True, True, False): return 3
        return None
    return expression_width(inp.node, inp.node_output_i, stack)


def expression_width(exp, output=0, stack=()):
    if id(exp) in stack or len(stack) >= 32: return None
    stack = stack + (id(exp),)
    kind = exp.export_class_type
    props = exp.properties
    if kind in ('MaterialExpressionConstant', 'MaterialExpressionScalarParameter', 'MaterialExpressionStaticBool'):
        return 1 if output == 0 else None
    if kind in ('MaterialExpressionConstant2Vector', 'MaterialExpressionTextureCoordinate'):
        return 2 if output == 0 else None
    if kind == 'MaterialExpressionConstant3Vector': return 3 if output == 0 else None
    if kind in ('MaterialExpressionVectorParameter', 'MaterialExpressionTextureSample', 'MaterialExpressionTextureSampleParameter2D', 'MaterialExpressionVertexColor'):
        return 3 if output == 0 else 1 if 1 <= output <= 4 else None
    if kind == 'MaterialExpressionFunctionInput' and output == 0:
        return {'FunctionInput_Scalar':1,'FunctionInput_StaticBool':1,'FunctionInput_Vector2':2,'FunctionInput_Vector3':3}.get(props.TryGetValue('InputType'))
    if kind in ('MaterialExpressionStaticSwitchParameter','MaterialExpressionStaticSwitch') and output == 0:
        return branch_width(props, stack)
    return None


def branch_width(props, stack=()):
    a,b = (input_width(props.TryGetValue(k),stack) for k in ('A','B'))
    if a is None or b is None: return None
    if a == b: return a
    if 1 in (a,b): return max(a,b)
    return None


def layout(props, parameter):
    width = branch_width(props)
    if width is None: return None
    if not parameter:
        selector = props.TryGetValue('Value')
        # A static bool is a compile-time selector; arbitrary float selectors
        # would produce interpolation rather than a branch and are unsupported.
        if selector is not None and (getattr(selector,'node',None) is None or selector.node.export_class_type != 'MaterialExpressionStaticBool' or selector.node_output_i != 0):
            return None
    # Blender Mix uses B for factor 1; UE uses A when true.
    indices = {'A':3, 'B':2} if width == 1 else {'A':5, 'B':4}
    if not parameter: indices['Value'] = 0
    return width, indices


def configure(node, width, default):
    node.data_type = 'FLOAT' if width == 1 else 'VECTOR'
    node.factor_mode = 'UNIFORM'
    node.clamp_factor = True
    node.clamp_result = False
    node.inputs[0].default_value = float(bool(default))
    node['UE_switch_width'] = width
    return node.outputs[0 if width == 1 else 1]
