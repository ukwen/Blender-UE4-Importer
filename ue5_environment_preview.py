"""Opt-in per-level analytical sky. Not captured UE radiance or fog evaluation."""
import math


def plan(records):
    sky=[r for r in records if r['kind']=='SkyLight']
    atmosphere=[r for r in records if r['kind']=='SkyAtmosphere']
    fog=[r for r in records if r['kind'] in ('ExponentialHeightFog','AtmosphericFog')]
    suns=[r for r in records if r['kind']=='DirectionalLight' and all(r['properties'].get(k,True) for k in ('bVisible','bAffectsWorld'))]
    report=dict(status='unsupported',fog_records=fog,scope='Analytical Blender sky preview; no Unreal captured radiance, fog, clouds or postprocess evaluation.')
    if len(sky)!=1 or len(atmosphere)!=1 or len(suns)!=1:
        report['detail']='Requires one saved SkyLight, SkyAtmosphere and enabled sun';return report
    p=sky[0]['properties']
    # Only the observed real-time-capture profile, not specified cubemaps or ambiguous fields.
    if p.get('bRealTimeCapture') is not True or not all(p.get(k,True) for k in ('bVisible','bAffectsWorld')) or set(sky[0].get('untranslated_component_fields',[]))-{'Mobility'}:
        report['detail']='Unsupported sky capture settings';return report
    pitch,yaw,_=map(math.radians,suns[0]['fields']['RelativeRotation'])
    direction=(-math.sin(yaw)*math.cos(pitch),-math.cos(yaw)*math.cos(pitch),-math.sin(pitch))
    elevation=math.asin(max(-1.,min(1.,direction[2])))
    if elevation<0:
        report['detail']='Below-horizon sun not supported by this preview';return report
    # Blender Nishita azimuth convention: zero along +X, positive toward +Y.
    rotation=math.atan2(direction[1],direction[0])%(2*math.pi)
    report.update(status='planned',sky_source_properties=p,atmosphere_source_properties=atmosphere[0]['properties'],sun_actor=suns[0]['actor'],sky_actor=sky[0]['actor'],sun_direction=list(direction),sun_elevation=elevation,sun_rotation=rotation,strength=p.get('Intensity',1.),strength_source='saved intensity (preview only)' if 'Intensity' in p else 'Blender preview default',sun_disc=False)
    return report


def build(root, records):
    import bpy
    report=plan(records)
    if report['status']!='planned':return report
    world=bpy.data.worlds.new(root.name+' — Sky preview');world.use_nodes=True
    nodes=world.node_tree.nodes;nodes.clear()
    sky=nodes.new('ShaderNodeTexSky');sky.sky_type='NISHITA';sky.sun_disc=False
    sky.sun_elevation=report['sun_elevation'];sky.sun_rotation=report['sun_rotation'];sky.location=(-320,0)
    background=nodes.new('ShaderNodeBackground');background.inputs['Strength'].default_value=report['strength'];background.location=(0,0)
    output=nodes.new('ShaderNodeOutputWorld');output.location=(240,0)
    world.node_tree.links.new(sky.outputs['Color'],background.inputs['Color']);world.node_tree.links.new(background.outputs[0],output.inputs['Surface'])
    world['UE_preview_only']=True;world['UE_sun_actor']=report['sun_actor'];root['UE_environment_world']=world
    report.update(status='sky_preview_ready',world=world.name,activation='Explicit Apply Selected Level Sky Preview; scene world unchanged during import')
    return report


def activate(scene, source):
    roots=[c for c in scene.collection.children_recursive if c.get('UE_full_scene_source')==source]
    if len(roots)!=1:raise ValueError('Import exactly one copy of the selected level first')
    world=roots[0].get('UE_environment_world')
    if world is None:raise ValueError('Selected level has no supported sky preview')
    scene.world=world
    return world
