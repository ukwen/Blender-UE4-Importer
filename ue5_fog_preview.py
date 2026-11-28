"""Opt-in finite Blender height fog preview, not UE fog renderer conversion."""
import math


def plan(records):
    fog=[r for r in records if r['kind']=='ExponentialHeightFog']
    if len(fog)!=1:return dict(status='unsupported',detail='Requires exactly one saved exponential height fog actor')
    r=fog[0];p=r['properties'];d=p.get('FogDensity')
    if (d is None or not math.isfinite(d) or not 0<=d<=1 or r.get('untranslated_component_fields') or set(p)-{'FogDensity'} or tuple(r['fields']['RelativeScale3D'])!=(1.,1.,1.) or tuple(r['fields']['RelativeRotation'])!=(0.,0.,0.)):
        return dict(status='unsupported',detail='No unambiguous explicit density-only fog profile')
    z=r['fields']['RelativeLocation'][2]*.01
    if not math.isfinite(z):return dict(status='unsupported',detail='Invalid fog height')
    return dict(status='planned',actor=r['actor'],source_density=d,reference_height_m=z,preview_density_per_m=d,preview_falloff_per_m=.01,preview_density_cap=1.,scope='Finite editable Blender volume scattering approximation. Density coefficient and falloff are preview choices, not calibrated Unreal units/defaults; white scatter, no start distance, secondary fog, atmosphere coupling or UE render parity.')


def build(root, settings):
    import bpy
    from mathutils import Vector
    from project_session import new_ids,rollback_new
    if settings.get('status')!='planned':raise ValueError(settings.get('detail','No supported fog record'))
    if root.get('UE_fog_preview_object') is not None:raise ValueError('Fog preview already exists')
    bpy.context.view_layer.update()
    points=[o.matrix_world@Vector(v) for o in root.all_objects if o.type=='MESH' and not o.get('UE_fog_preview') for v in o.bound_box]
    if not points:raise ValueError('No reconstructed mesh bounds for finite fog volume')
    lo=[min(v[i] for v in points)-5 for i in range(3)];hi=[max(v[i] for v in points)+5 for i in range(3)]
    if not all(math.isfinite(v) for v in lo+hi) or max(b-a for a,b in zip(lo,hi))>10000:raise ValueError('Fog preview extent invalid or excessive')
    before=set(new_ids())
    try:
        mesh=bpy.data.meshes.new('UE fog bounds');mesh.from_pydata([(lo[0],lo[1],lo[2]),(hi[0],lo[1],lo[2]),(hi[0],hi[1],lo[2]),(lo[0],hi[1],lo[2]),(lo[0],lo[1],hi[2]),(hi[0],lo[1],hi[2]),(hi[0],hi[1],hi[2]),(lo[0],hi[1],hi[2])],[],[(3,2,1,0),(4,5,6,7),(0,1,5,4),(1,2,6,5),(2,3,7,6),(3,0,4,7)]);mesh.update()
        obj=bpy.data.objects.new('UE fog preview — '+settings['actor'],mesh);root.objects.link(obj);obj.display_type='WIRE';obj['UE_fog_preview']=True;obj['UE_source_density']=settings['source_density'];obj['UE_preview_scope']=settings['scope']
        mat=bpy.data.materials.new(obj.name);mat.use_nodes=True;mesh.materials.append(mat);nt=mat.node_tree;nt.nodes.clear();n=nt.nodes;l=nt.links
        def value(label,v):
            x=n.new('ShaderNodeValue');x.label=label;x.outputs[0].default_value=v;return x.outputs[0]
        def mathnode(op,a,b=None):
            x=n.new('ShaderNodeMath');x.operation=op
            for i,v in enumerate((a,b)):
                if v is None:continue
                if isinstance(v,(float,int)):x.inputs[i].default_value=v
                else:l.new(v,x.inputs[i])
            return x.outputs[0]
        geo=n.new('ShaderNodeNewGeometry');sep=n.new('ShaderNodeSeparateXYZ');l.new(geo.outputs['Position'],sep.inputs[0]);z=sep.outputs['Z']
        ref=value('Saved fog reference height (m)',settings['reference_height_m']);density=value('Preview density coefficient (1/m)',settings['preview_density_per_m']);fall=value('Preview falloff (1/m, not saved UE default)',settings['preview_falloff_per_m']);cap=value('Preview density cap',settings['preview_density_cap'])
        exponent=mathnode('MAXIMUM',-60.,mathnode('MINIMUM',60.,mathnode('MULTIPLY',mathnode('SUBTRACT',ref,z),fall)))
        coefficient=mathnode('MAXIMUM',0.,mathnode('MINIMUM',cap,mathnode('MULTIPLY',density,mathnode('EXPONENT',exponent))))
        scatter=n.new('ShaderNodeVolumeScatter');scatter.inputs['Color'].default_value=(1,1,1,1);l.new(coefficient,scatter.inputs['Density']);out=n.new('ShaderNodeOutputMaterial');l.new(scatter.outputs[0],out.inputs['Volume']);root['UE_fog_preview_object']=obj
        return obj
    except Exception:
        rollback_new(before);raise


def toggle(scene,source):
    import json
    import bpy
    roots=[c for c in scene.collection.children_recursive if c.get('UE_full_scene_source')==source]
    if len(roots)!=1:raise ValueError('Import exactly one copy of the selected level first')
    root=roots[0];obj=root.get('UE_fog_preview_object')
    if obj is not None:
        if obj not in root.all_objects[:]:raise ValueError('Fog preview moved outside imported level')
        enabled=obj.hide_render;obj.hide_render=not enabled;obj.hide_viewport=not enabled;return obj,enabled
    settings=json.loads(bpy.data.texts[root['UE_report']].as_string())['stages']['environment'].get('fog_preview',{})
    return build(root,settings),True
