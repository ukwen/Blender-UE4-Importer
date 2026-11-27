"""Create live socket anchors from native Unreal reference-space metadata."""
import json
import math
import bpy
from mathutils import Matrix, Euler, Vector
from bpy.props import BoolProperty


def socket_local(record):
    t=record['location_cm']; p,y,r=record['rotation_pyr']; s=record['scale']
    if len(t)!=3 or len(s)!=3 or not all(math.isfinite(v) for v in (*t,p,y,r,*s)) or any(v==0 for v in s):
        raise ValueError('Invalid socket transform')
    # UE pitch/yaw/roll -> Blender YXZ after reflecting X/Y; retain negative scales.
    q=Euler(tuple(math.radians(v) for v in (p,r,-y)),'YXZ').to_quaternion()
    return Matrix.LocRotScale(Vector((t[1],t[0],t[2]))*.01,q,Vector((s[1],s[0],s[2])))


def create_socket_anchors(arm, records, collection=None):
    if arm.type!='ARMATURE' or arm.mode!='OBJECT': raise ValueError('Select a native armature in Object mode')
    existing={o.get('UE_socket_name') for o in arm.children if o.get('UE_socket_name')}
    plans=[]; names=set()
    for rec in records:
        name=rec['name']; bone=arm.data.bones.get(rec['bone'])
        if not isinstance(name,str) or not name or name in names or name in existing: raise ValueError('Duplicate or existing socket: '+str(name))
        names.add(name)
        if bone is None: raise ValueError('Missing socket bone: '+rec['bone'])
        m=bone.get('UE_world_matrix_m')
        if m is None or len(m)!=16 or not all(math.isfinite(v) for v in m): raise ValueError('Native bone reference metadata required')
        rest=Matrix([m[i:i+4] for i in range(0,16,4)])
        if abs(rest.to_3x3().determinant())<1e-12: raise ValueError('Singular source reference transform')
        # Bone parenting uses the tail, whereas Unreal sockets use the bone origin.
        correction=Matrix.Translation((0,-bone.length,0))@bone.matrix_local.inverted()@rest@socket_local(rec)
        plans.append((rec,correction))
    if not plans: raise ValueError('No socket definitions')
    collection=collection or (arm.users_collection[0] if arm.users_collection else bpy.context.collection)
    created=[]
    try:
        for rec,correction in plans:
            obj=bpy.data.objects.new(arm.name+' / '+rec['name'],None); created.append(obj); collection.objects.link(obj)
            obj.empty_display_type='ARROWS'; obj.empty_display_size=.08
            obj.parent=arm; obj.parent_type='BONE'; obj.parent_bone=rec['bone']
            # Full matrix retains reflections and any scale correction without decomposition.
            obj.matrix_parent_inverse=correction; obj.matrix_basis=Matrix.Identity(4)
            obj['UE_socket_name']=rec['name']; obj['UE_socket_bone']=rec['bone']; obj['UE_socket_definition']=json.dumps(rec)
        return created
    except Exception:
        for obj in created: bpy.data.objects.remove(obj,do_unlink=True)
        raise


class CreateUESockets(bpy.types.Operator):
    bl_idname='object.ue_create_socket_anchors'
    bl_label='UE Create Live Socket Anchors'
    bl_description='Create bone-parented anchors on the active native armature; optionally select a reference skeleton containing socket definitions'
    bl_options={'REGISTER','UNDO'}
    available_only: BoolProperty(name='Available bones only',description='Explicitly omit sockets whose source bones are absent on a simplified rig',default=False)
    @classmethod
    def poll(cls,context):
        return context.mode=='OBJECT' and context.object is not None and context.object.type=='ARMATURE'
    def invoke(self,context,event):
        return context.window_manager.invoke_props_dialog(self)
    def execute(self,context):
        arm=context.object
        try:
            source=arm
            if not arm.get('UE_socket_definitions'):
                candidates=[o for o in context.selected_objects if o!=arm and o.type=='ARMATURE' and o.get('UE_socket_definitions')]
                if len(candidates)!=1: raise ValueError('Select one socket-bearing reference skeleton and make the target armature active')
                source=candidates[0]
                target_package=arm.get('UE_skeleton_package','')
                source_package=source.get('UE_skeleton_package','')
                source_name=str(source.get('UE_skeleton_source','')).replace('\\','/').rsplit('/',1)[-1].removesuffix('.uasset')
                if not target_package or (source_package!=target_package if source_package else source_name!=target_package.rsplit('/',1)[-1]):
                    raise ValueError('Reference skeleton does not match target skeleton identity')
            records=json.loads(source['UE_socket_definitions']); missing=[r['name'] for r in records if arm.data.bones.get(r['bone']) is None]
            if missing and self.available_only: records=[r for r in records if arm.data.bones.get(r['bone']) is not None]
            anchors=create_socket_anchors(arm,records)
            arm['UE_omitted_socket_names']=json.dumps(missing if self.available_only else [])
            self.report({'INFO'},f'Created {len(anchors)} live bone socket anchors; omitted {len(missing) if self.available_only else 0}')
            return {'FINISHED'}
        except (ValueError,KeyError,TypeError,RuntimeError) as exc:
            self.report({'ERROR'},str(exc)); return {'CANCELLED'}


def register(): bpy.utils.register_class(CreateUESockets)
def unregister(): bpy.utils.unregister_class(CreateUESockets)
