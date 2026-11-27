"""Render original procedural grid materials as explicit preview, not Unreal pixel parity."""
import bpy,sys,os,json
from pathlib import Path
from mathutils import Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_material import build_material
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.render.resolution_x=256;scene.render.resolution_y=256;scene.render.resolution_percentage=100;scene.view_settings.view_transform='Standard';scene.world=bpy.data.worlds.new('Preview World');scene.world.color=(.2,.2,.2)
records=[]
for i,stem in enumerate(('MI_PrototypeGrid_Gray_02','MI_PrototypeGrid_TopDark')):
    p=next(root.rglob(stem+'.uasset'));pkg='/Game/'+p.relative_to(root).with_suffix('').as_posix();mat=build_material(root,pkg,True);mat.use_fake_user=True
    strict=build_material(root,pkg,False);assert strict['UE_editor_material_status']=='metadata_only';assert not any(l.to_node.type=='BSDF_PRINCIPLED' for l in strict.node_tree.links)
    assert mat['UE_editor_material_status']=='partial';assert set(json.loads(mat['UE_editor_connected_outputs']))=={'BaseColor','Roughness'}
    imgs={n.image.name for n in mat.node_tree.nodes if n.type=='TEX_IMAGE' and n.image};assert imgs=={'T_GridChecker_A'}
    bpy.ops.mesh.primitive_cube_add(size=2.,location=(i*3.-1.5,0,0));obj=bpy.context.object;obj.name=stem;obj.data.materials.append(mat)
    records.append(dict(material=mat.name,node_count=len(mat.node_tree.nodes),image_names=sorted(imgs),issues=json.loads(mat['UE_editor_material_issues'])))
bpy.ops.object.camera_add(location=(5,-8,7));cam=bpy.context.object;cam.rotation_euler=(-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=7.5;scene.camera=cam
bpy.ops.object.light_add(type='AREA',location=(1,-4,7));bpy.context.object.data.energy=1400;bpy.context.object.data.shape='DISK';bpy.context.object.data.size=6;bpy.context.object.rotation_euler=(-bpy.context.object.location).to_track_quat('-Z','Y').to_euler()
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(out.with_suffix('.png'));bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));bpy.ops.render.render(write_still=True)
image=bpy.data.images.load(str(out.with_suffix('.png')),check_existing=False);pixels=list(image.pixels);assert len(pixels)==256*256*4;assert all(0<=x<=1 for x in pixels);assert len(set(round(x,3) for x in pixels[::4]))>20
out.with_suffix('.json').write_text(json.dumps(dict(materials=records,reopen=True,rendered=True,render_resolution=[256,256],unreal_pixel_parity=False),indent=2));print('GRID_RENDER_PASS',flush=True)
