"""Explicit, conservative binding of a native skeletal accessory to a body rig."""
from mathutils import Matrix


def bind_compatible_accessory(mesh, target, tolerance=1e-6):
    """Reparent in reference mesh space; retain original rig for manual recovery.

    This is an explicit user action, not automatic Blueprint placement or retargeting.
    """
    source=mesh.parent
    if mesh.type!='MESH' or not source or source.type!='ARMATURE' or target.type!='ARMATURE' or source==target:
        raise ValueError('Select a native accessory mesh and a different target armature')
    if any(o.mode!='OBJECT' for o in (mesh,source,target)):
        raise ValueError('Use Object mode')
    package=source.get('UE_skeleton_package')
    if not package or target.get('UE_skeleton_package')!=package or mesh.get('UE_skeleton_package')!=package:
        raise ValueError('Original skeleton package identity must match')
    if mesh.constraints or mesh.animation_data or len(mesh.modifiers)!=1 or mesh.modifiers[0].type!='ARMATURE' or mesh.modifiers[0].object!=source:
        raise ValueError('Expected an unmodified native accessory mesh')
    if any(abs(mesh.matrix_basis[i][j]-float(i==j))>tolerance or abs(mesh.matrix_parent_inverse[i][j]-float(i==j))>tolerance for i in range(4) for j in range(4)):
        raise ValueError('Accessory has a nonidentity local transform')
    for bone in source.data.bones:
        other=target.data.bones.get(bone.name)
        if other is None or (bone.parent.name if bone.parent else None)!=(other.parent.name if other.parent else None):
            raise ValueError('Missing or incompatible bone hierarchy: '+bone.name)
        a=bone.get('UE_world_matrix_m'); b=other.get('UE_world_matrix_m')
        if a is None or b is None or len(a)!=16 or len(b)!=16 or max(abs(x-y) for x,y in zip(a,b))>tolerance or max(abs(bone.matrix_local[i][j]-other.matrix_local[i][j]) for i in range(4) for j in range(4))>tolerance:
            raise ValueError('Incompatible reference transform: '+bone.name)
    if any(g.name not in source.data.bones for g in mesh.vertex_groups):
        raise ValueError('Unexpected accessory vertex group')
    mesh.parent=target; mesh.matrix_parent_inverse=Matrix.Identity(4); mesh.matrix_basis=Matrix.Identity(4)
    mesh.modifiers[0].object=target
    mesh['UE_accessory_binding']='explicit_compatible_reference_space'
    mesh['UE_accessory_original_armature']=source.name
    return source
