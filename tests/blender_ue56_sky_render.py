import bpy,sys,math,os,json
from mathutils import Vector
from pathlib import Path
source=Path(os.environ['UE56_EDITOR_OUTPUT']);output=source.with_name(source.stem+'-sky.exr')
bpy.ops.wm.open_mainfile(filepath=str(source))
scene=bpy.context.scene;root=next(c for c in scene.collection.children if c.get('UE_full_scene_source','').endswith('Lvl_ThirdPerson.umap'));scene.world=root['UE_environment_world']
# Isolate sky response, no geometry or lamps; render an upward-facing camera on CPU.
for c in scene.collection.children:c.hide_render=True
camera=bpy.data.objects.new('Sky test camera',bpy.data.cameras.new('Sky test camera'));scene.collection.objects.link(camera);camera.rotation_euler=Vector((0,0,1)).to_track_quat('-Z','Y').to_euler();scene.camera=camera
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.render.resolution_x=32;scene.render.resolution_y=32;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR';scene.render.filepath=str(output);bpy.ops.render.render(write_still=True)
i=bpy.data.images.load(scene.render.filepath);pixels=list(i.pixels);rgb=[v for j,v in enumerate(pixels) if j%4!=3];assert all(math.isfinite(x) and x>=0 for x in rgb) and max(rgb)>.01;print('SKY_RENDER_PASS',min(rgb),max(rgb),flush=True);output.with_suffix('.json').write_text(json.dumps(dict(engine='Cycles CPU',resolution=[32,32],samples=4,min_linear_rgb=min(rgb),max_linear_rgb=max(rgb),scope='nonzero finite sky radiance only, not Unreal equivalence'),indent=2))
