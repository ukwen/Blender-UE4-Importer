"""Reconstruct serialized Blueprint and skeletal actor component hierarchies.
No Blueprint execution, inherited template defaults or socket transforms are invented.
"""
from collections import Counter, defaultdict
from pathlib import Path
import json
import bpy
from classic_map_records import MapRecords, owned_export, apply_component_transform
from blueprint_defaults import BlueprintResolver
from reference_identity import package_reference

MESH_TYPES={'StaticMeshComponent','SkeletalMeshComponent','InstancedStaticMeshComponent','HierarchicalInstancedStaticMeshComponent'}


def extend_components(filepath,collection,resolver):
    from package_inspector import inspect_package
    meta=inspect_package(filepath)
    if meta.get("ue4") in (508,522) and meta.get("ue5") is None:
        return build_components(MapRecords(filepath),collection,resolver)
    raise NotImplementedError('Unsupported native classic map component profile; no validated native decoder for this profile')


def build_components(asset,collection,resolver):
    """Use only map-owned components. Keep unresolved placements as diagnostic empties."""
    records=[]; actor_count=Counter(); failures=[]; skeletal_cache={}; skeletal_attempts=0
    owners={}; nodes={}; props={}; plans=[]
    blueprints=BlueprintResolver(resolver.project)
    from blueprint_placement import resolve_body, place_body, body_sockets
    placement_cache={}; socket_cache={}; body_rigs={}; resolved_accessories=set()
    children=defaultdict(list)
    for c in asset.exports: children[c.outer_index].append(c)
    for index,actor in enumerate(asset.exports,1):
        kind=actor.export_class_type or ''
        if kind!='SkeletalMeshActor' and not kind.endswith('_C'): continue
        # Require direct ownership by a serialized Level, not an arbitrary CDO.
        outer=actor.outer_index
        if not 0<outer<=len(asset.exports) or asset.GetExport(outer).export_class_type!='Level': continue
        try:
            actor.ReadProperties(False)
            root=actor.properties.TryGetValue('RootComponent')
            if not owned_export(root,asset) or root.outer_index!=index:
                raise ValueError('Missing map-owned RootComponent')
            selected={id(root):root}
            selected.update({id(c):c for c in children[index] if c.export_class_type in MESH_TYPES})
            # Include intermediate attachment nodes even when they are not meshes.
            pending=list(selected.values())
            while pending:
                c=pending.pop(); c.ReadProperties(False); props[id(c)]=c.properties
                parent=c.properties.TryGetValue('AttachParent')
                if owned_export(parent,asset) and parent.outer_index==index and id(parent) not in selected:
                    selected[id(parent)]=parent; pending.append(parent)
            actor_count[kind if kind=='SkeletalMeshActor' else 'BlueprintActor']+=1
            label=actor.properties.TryGetValue('ActorLabel',actor.object_name)
            for c in selected.values(): owners[id(c)]=(actor,root,label,kind)
            plans.extend(selected.values())
        except Exception as exc: failures.append({'actor':actor.object_name,'detail':str(exc)})
    # First allocate anchors so export order cannot affect parenting.
    for c in plans:
        actor,root,label,kind=owners[id(c)]
        anchor=bpy.data.objects.new(label if c is root else label+' / '+c.object_name,None)
        collection.objects.link(anchor); anchor.empty_display_type='ARROWS'; anchor.empty_display_size=.15
        anchor['UE_component']=c.object_name; anchor['UE_component_actor']=actor.object_name; anchor['UE_component_class']=c.export_class_type
        anchor['UE_component_anchor']=True; anchor['UE_blueprint_defaults_unresolved']=kind.endswith('_C')
        anchor.rotation_mode='YXZ'; apply_component_transform(c,anchor); nodes[id(c)]=anchor
    # Determine parent edges and refuse cycles, missing parents, absolute flags and socket placement.
    edges={}; reasons={}
    for c in plans:
        key=id(c); p=props[key]; actor,root,label,kind=owners[key]
        parent=p.TryGetValue('AttachParent'); socket=p.TryGetValue('AttachSocketName','None')
        if socket not in (None,'None',''): reasons[key]='socket_transform_unresolved'; nodes[key]['UE_attach_socket']=str(socket)
        if any(p.TryGetValue(flag,False) for flag in ('bAbsoluteLocation','bAbsoluteRotation','bAbsoluteScale')): reasons[key]='absolute_transform_unsupported'
        if parent is not None:
            target=nodes.get(id(parent))
            if target is None: reasons[key]='external_parent_unresolved'
            else: edges[key]=id(parent)
        elif c is not root: reasons[key]='missing_attach_parent'
    for key in nodes:
        seen=set(); x=key
        while x in edges:
            if x in seen:
                reasons[key]='attachment_cycle'; break
            seen.add(x); x=edges[x]
    for key,node in nodes.items():
        if key in edges and reasons.get(key)!='attachment_cycle': node.parent=nodes[edges[key]]
    def unresolved_ancestor(key):
        seen=set()
        while key not in seen:
            seen.add(key)
            if key in reasons: return reasons[key]
            if key not in edges: return None
            key=edges[key]
        return 'attachment_cycle'
    # Parent-first, independent of export order. Cycles retain diagnostic status.
    def depth(c):
        seen=set(); k=id(c)
        while k in edges and k not in seen:
            seen.add(k); k=edges[k]
        return len(seen)
    for c in sorted(plans,key=depth):
        key=id(c); node=nodes[key]; actor,root,label,kind=owners[key]; p=props[key]; cls=c.export_class_type
        field='SkeletalMesh' if cls=='SkeletalMeshComponent' else 'StaticMesh'
        package=package_reference(p.TryGetValue(field)) if cls in MESH_TYPES else ''
        binding=None
        if kind.endswith('_C'):
            bp=blueprints.load(actor); node['UE_blueprint_package']=bp['package']; node['UE_blueprint_status']=bp['status']
            if 'lineage_status' in bp: node['UE_blueprint_lineage_status']=bp['lineage_status']; node['UE_blueprint_lineage']=json.dumps(bp['lineage'])
            if cls in MESH_TYPES and field not in p:
                binding=blueprints.component(actor,c)
                if binding is not None and binding['explicit']:
                    package=binding['package']; node['UE_mesh_reference_origin']=binding['origin']; node['UE_mesh_template']=binding['template']
                    if binding.get('mesh_declared_in'): node['UE_mesh_declared_in']=binding['mesh_declared_in']
                    if binding.get('socket'): node['UE_template_socket']=binding['socket']
        reason=unresolved_ancestor(key)
        status='anchor_only'; detail=reason or ''; geom=None
        placement=None; socket_result=None
        if kind.endswith('_C') and cls=='SkeletalMeshComponent' and package and not reason and actor.properties.TryGetValue('Mesh') is c:
            try:
                placement=resolve_body(resolver.project,actor,c,root,bp['package'],placement_cache)
                if nodes[id(root)].parent is not None or node.parent!=nodes[id(root)]: raise ValueError('Unexpected body anchor hierarchy')
            except Exception as exc:
                placement=None; detail='Body placement unresolved: '+str(exc)
        accessory=False; master=None
        if kind.endswith('_C') and binding and binding['origin']=='SCS' and id(actor) in body_rigs:
            try:
                from blueprint_placement import transform4,apply_fields
                from mathutils import Matrix
                import math
                body_component,body_rig=body_rigs[id(actor)]
                parent=p.TryGetValue('AttachParent'); socket=p.TryGetValue('AttachSocketName','None')
                if not owned_export(parent,asset) or id(parent) not in nodes or parent.outer_index!=c.outer_index:
                    raise ValueError('No map-owned accessory parent')
                if binding.get('parent') not in (None,'','None',parent.object_name): raise ValueError('Template/map parent mismatch')
                if binding.get('socket') not in (None,'','None',socket): raise ValueError('Template/map socket mismatch')
                if reason not in (None,'socket_transform_unresolved'): raise ValueError(reason)
                fields={'RelativeLocation':(0.,0.,0.),'RelativeRotation':(0.,0.,0.),'RelativeScale3D':(1.,1.,1.)}
                fields.update(binding['fields']);fields.update(transform4(p))
                if not all(math.isfinite(v) for a in fields.values() for v in a) or any(v==0 for v in fields['RelativeScale3D']): raise ValueError('Invalid accessory transform')
                if socket not in (None,'','None'):
                    if parent is not body_component: raise ValueError('Non-body socket unsupported')
                    anchors=[o for o in body_rig.children if o.get('UE_socket_name')==socket]
                    if len(anchors)!=1: raise ValueError('Socket definition unavailable')
                    target=anchors[0]
                elif parent is body_component: target=nodes[id(parent)]
                elif id(parent) in resolved_accessories: target=nodes[id(parent)]
                else: raise ValueError('Accessory parent unresolved')
                if cls=='SkeletalMeshComponent':
                    if p.TryGetValue('MasterPoseComponent') is not body_component or parent is not body_component or socket not in (None,'','None') or fields!={'RelativeLocation':(0.,0.,0.),'RelativeRotation':(0.,0.,0.),'RelativeScale3D':(1.,1.,1.)}: raise ValueError('Unsupported master pose relationship')
                    master=body_rig
                node.parent=target;node.matrix_parent_inverse=Matrix.Identity(4);apply_fields(node,fields)
                node['UE_blueprint_defaults_unresolved']=False;node['UE_accessory_placement']='serialized_template_map';node['UE_accessory_fields']=json.dumps(fields)
                reasons.pop(key,None);reason=None;detail='';accessory=True;resolved_accessories.add(key)
            except Exception as exc: detail='Accessory placement unresolved: '+str(exc)
        if cls in MESH_TYPES:
            if reason: status=reason
            elif cls in ('InstancedStaticMeshComponent','HierarchicalInstancedStaticMeshComponent'): status='instance_transforms_unsupported'
            elif not package: status='inherited_mesh_unresolved' if kind.endswith('_C') else 'mesh_reference_unresolved'
            elif kind.endswith('_C') and placement is None and not accessory: status='blueprint_defaults_unresolved'
            elif cls=='StaticMeshComponent':
                mesh,status=resolver(package)
                if mesh is None: detail=resolver.records.get(package,{}).get('detail','Source mesh unavailable')
                if mesh is not None:
                    geom=bpy.data.objects.new(node.name+' / Mesh',mesh); collection.objects.link(geom); geom.parent=node
            else:
                try:
                    if package not in skeletal_cache:
                        try:
                            path=Path(resolver.project.resolve_package(package))
                            if not path.is_file(): raise FileNotFoundError(str(path))
                            from skeletal_mesh_native import read_native_mesh
                            skeletal_attempts+=1; skeletal_cache[package]=(read_native_mesh(path,resolver.cooked_profile),'reconstructed','')
                        except Exception as exc:
                            skeletal_cache[package]=(None,'missing' if isinstance(exc,FileNotFoundError) else 'unsupported' if isinstance(exc,NotImplementedError) else 'failed',str(exc))
                    data,status,detail=skeletal_cache[package]
                    if data is not None:
                        from skeletal_mesh_native import build_mesh
                        geom,arm=build_mesh(data,collection); arm.parent=node
                        if placement is not None:
                            place_body(nodes[id(root)],node,arm,placement)
                            body_rigs[id(actor)]=(c,arm)
                            try:
                                skeleton=arm.get('UE_skeleton_package','')
                                if not skeleton: raise ValueError('Missing source skeleton package')
                                if skeleton not in socket_cache:
                                    from editor_skeleton import read_editor_skeleton
                                    sk=read_editor_skeleton(resolver.project.resolve_package(skeleton))
                                    if sk['name']!=skeleton.rsplit('/',1)[-1]: raise ValueError('Skeleton asset identity mismatch')
                                    socket_cache[skeleton]=sk['sockets']
                                socket_result=body_sockets(arm,socket_cache[skeleton],collection)
                            except Exception as exc:
                                socket_result={'created':0,'detail':str(exc)}
                        elif master is not None:
                            from native_attachments import bind_compatible_accessory
                            try:
                                old=bind_compatible_accessory(geom,master)
                            except Exception:
                                bpy.data.objects.remove(geom,do_unlink=True); geom=None
                                bpy.data.objects.remove(arm,do_unlink=True); raise
                            geom['UE_master_pose_component']=master.name
                            geom['UE_accessory_binding']='serialized_master_pose_compatible_reference_space'
                            del geom['UE_accessory_original_armature']
                            bpy.data.objects.remove(old,do_unlink=True)
                except Exception as exc: status='failed'; detail=str(exc)
        node['UE_component_status']=status
        if package: node['UE_mesh_package']=package
        if reason: node['UE_placement_unresolved']=reason
        if geom:
            overrides=p.TryGetValue('OverrideMaterials', [])
            if overrides:
                geom['UE_material_override_packages']=json.dumps([package_reference(v.value) for v in overrides])
            geom['UE_component_actor']=actor.object_name; geom['UE_mesh_package']=package; geom['UE_component_status']=status
        records.append(dict(actor=actor.object_name,component=c.object_name,kind=cls,package=package,status=status,detail=detail,parent=nodes[edges[key]].name if key in edges else '',socket=node.get('UE_attach_socket',''),reference_origin=node.get('UE_mesh_reference_origin','map' if field in p else ''),blueprint=node.get('UE_blueprint_package','')))
        if accessory: records[-1].update(accessory_placement='serialized_template_map',fields=fields,master_pose=master.name if master else '')
        if placement is not None and geom is not None and status=='reconstructed':
            records[-1].update(placement=placement,sockets=socket_result)
    return dict(actors=dict(actor_count),components=len(records),status=dict(Counter(r['status'] for r in records)),skeletal_decode_attempts=skeletal_attempts,records=records,failures=failures,blueprint_dependencies=[blueprints.resolved_cache.get(k,v) for k,v in blueprints.cache.items()])
