"""Bind an image to an editable Blender texture node and owned normal preview."""
from uv_semantics import set_address
from generated_shader_groups import get, SCHEMA


def assign_image(node,image):
    if node.bl_idname!='ShaderNodeTexImage':raise ValueError('Expected image texture node')
    node.image=image
    node.interpolation='Closest' if image.get('nearest',False) else 'Linear'
    set_address(node,image)
    # Only our marked normal conversion groups are eligible for replacement.
    # A foreign group with a similar name is left untouched.
    for link in list(node.outputs['Color'].links):
        dst=link.to_node;group=dst.node_tree if dst.type=='GROUP' else None
        if group and group.get('UI_generated_schema')==SCHEMA and group.get('UI_group_key') in ('RGBtoNormal','RGBtoNormalY-'):
            dst.node_tree=get('RGBtoNormal' if image.get('flip_y',False) else 'RGBtoNormalY-')
