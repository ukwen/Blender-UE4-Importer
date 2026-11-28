"""Original map and separate controlled CPU volume / RGB probe."""
import os,sys,json,math,tempfile
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uproject_browser as browser
from ue5_material_semantics import rgb_lerp
from ue5_editor_material import resolve_material
from ue5_fog_preview import build
from ue5_editor_lighting import records
from ue5_fog_preview import plan
project=Path(os.environ['UE56_EDITOR_PROJECT']);c=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);p=c/'ThirdPerson/Lvl_ThirdPerson.umap'
bpy.ops.wm.read_factory_settings(use_empty=True);browser.register();sc=bpy.context.scene;state=sc.ueimport_project;state.project_path=str(project);state.partial_materials=True
assert bpy.ops.ueimport.scan_project()=={'FINISHED'};state.active=next(i for i,m in enumerate(state.maps) if Path(m.filepath)==p);assert bpy.ops.ueimport.full_scene()=={'FINISHED'}
root=next(x for x in sc.collection.children if x.get('UE_full_scene_source')==str(p));world=sc.world;before=len(root.all_objects);assert root.get('UE_fog_preview_object') is None
assert bpy.ops.ueimport.toggle_fog_preview()=={'FINISHED'};obj=root['UE_fog_preview_object'];assert len(root.all_objects)==before+1 and sc.world==world;assert obj['UE_source_density']==plan(records(c,p)['records'])['source_density'];assert len(obj.data.polygons)==6
assert bpy.ops.ueimport.toggle_fog_preview()=={'FINISHED'} and obj.hide_render;assert bpy.ops.ueimport.toggle_fog_preview()=={'FINISHED'} and not obj.hide_render and len(root.all_objects)==before+1
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));sc=bpy.context.scene;root=next(x for x in sc.collection.children if x.get('UE_full_scene_source')==str(p));assert root['UE_fog_preview_object'].data.materials[0].use_nodes;assert bpy.ops.ueimport.toggle_fog_preview()=={'FINISHED'} and root['UE_fog_preview_object'].hide_render
# Check original override flags, not guessed default values.
def resolve(stem):return resolve_material(c,'/Game/'+next(c.rglob(stem+'.uasset')).relative_to(c).with_suffix('').as_posix())
a=resolve('MI_GlowNT')['base_property_audit'];assert {x['property'] for x in a if x['status']=='active_unresolved'}=={'BlendMode','ShadingModel'};assert next(x for x in a if x['property']=='TwoSided')['status']=='inactive_no_flag'
# Controlled CPU test: use a small volume and emission backdrop, same source density and height.
bpy.ops.wm.read_factory_settings(use_empty=True);sc=bpy.context.scene;root=bpy.data.collections.new('Controlled volume');sc.collection.children.link(root);bpy.ops.mesh.primitive_plane_add(size=2);plane=bpy.context.object;sc.collection.objects.unlink(plane) if plane.name in sc.collection.objects else None
for col in list(plane.users_collection):col.objects.unlink(plane)
root.objects.link(plane);mat=bpy.data.materials.new('Emission probe');mat.use_nodes=True;plane.data.materials.append(mat);nt=mat.node_tree;nt.nodes.clear();em=nt.nodes.new('ShaderNodeEmission');outnode=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(em.outputs[0],outnode.inputs['Surface']);em.inputs['Color'].default_value=(1,1,1,1)
bpy.ops.object.camera_add(location=(0,0,3));sc.camera=bpy.context.object;sc.camera.data.type='ORTHO';sc.camera.data.ortho_scale=1
sc.render.engine='CYCLES';sc.cycles.device='CPU';sc.cycles.samples=256;sc.cycles.use_adaptive_sampling=False;sc.cycles.use_denoising=False;sc.render.resolution_x=sc.render.resolution_y=8;sc.render.resolution_percentage=100;sc.render.image_settings.file_format='OPEN_EXR';sc.render.image_settings.color_depth='32';sc.world=None
fog=build(root,plan(records(c,p)['records']));fogmat=fog.data.materials[0];fognt=fogmat.node_tree
with tempfile.TemporaryDirectory() as d:
    def render(name):
        sc.render.filepath=str(Path(d)/(name+'.exr'));bpy.ops.render.render(write_still=True);im=bpy.data.images.load(sc.render.filepath,check_existing=False);v=list(im.pixels);bpy.data.images.remove(im);return [sum(v[i::4])/64 for i in range(3)]
    fog.hide_render=True;clear=render('clear');fog.hide_render=False;scatter=render('scatter');assert all(math.isfinite(v) and 0<v<.999 for v in scatter),(clear,scatter)
    # Absorption-only diagnostic validates the analytical density integral separately from scattering.
    scatter_node=next(n for n in fognt.nodes if n.type=='VOLUME_SCATTER');absorb=fognt.nodes.new('ShaderNodeVolumeAbsorption');absorb.inputs['Color'].default_value=(0,0,0,1);fognt.links.new(scatter_node.inputs['Density'].links[0].from_socket,absorb.inputs['Density']);fognt.links.new(absorb.outputs[0],next(n for n in fognt.nodes if n.type=='OUTPUT_MATERIAL').inputs['Volume']);absval=render('absorption');r=plan(records(c,p)['records']);expected=math.exp(-r['preview_density_per_m']*math.exp(r['preview_falloff_per_m']*r['reference_height_m'])*(1-math.exp(-3*r['preview_falloff_per_m']))/r['preview_falloff_per_m']);assert max(abs(v-expected) for v in absval)<.035,(absval,expected)
    fog.hide_render=True;ns=nt.nodes;ls=nt.links
    def constant(v):
        n=ns.new('ShaderNodeRGB');n.outputs[0].default_value=(*v,1);return n.outputs[0]
    def comp(s):
        n=ns.new('ShaderNodeSeparateXYZ');ls.new(s,n.inputs[0]);return tuple(n.outputs)
    def combine(v,label):
        n=ns.new('ShaderNodeCombineXYZ');n.label=label
        for i,s in enumerate(v):ls.new(s,n.inputs[i])
        return n.outputs[0]
    def op(operation,x,y,label='Source arithmetic'):
        n=ns.new('ShaderNodeMath');n.operation=operation;ls.new(x,n.inputs[0]);ls.new(y,n.inputs[1]);return n.outputs[0]
    aa=(.3,.4,.5);bb=(.5,.6,.7);ff=(-.5,.25,1.5);f=ns.new('ShaderNodeCombineXYZ');
    for i,v in enumerate(ff):f.inputs[i].default_value=v
    s=rgb_lerp(constant(aa),constant(bb),f.outputs[0],components=comp,combine=combine,mathop=op,label='Vector Lerp');ls.new(s,em.inputs['Color']);rgb=render('rgb');target=[a+(b-a)*f for a,b,f in zip(aa,bb,ff)];error=max(abs(x-y) for x,y in zip(rgb,target));assert error<1e-5,(rgb,target)
out.with_suffix('.json').write_text(json.dumps(dict(original_map=p.name,source_density=r['source_density'],reopen=True,toggle=True,clear=clear,scatter=scatter,absorption=absval,analytic_absorption=expected,rgb_vector_expected=target,rgb_vector_observed=rgb,rgb_max_error=error,scope='original level toggle and controlled CPU volume and RGB probe; no UE rendering parity'),indent=2));print('FOG_VECTOR_PASS',flush=True)
