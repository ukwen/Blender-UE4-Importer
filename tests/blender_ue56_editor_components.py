"""Original saved Blueprint component hierarchies and native live sockets."""
import sys,os,json,math
from pathlib import Path
import bpy
from mathutils import Matrix,Vector,Quaternion
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_components import placements
from static_scene import reconstruct_static_map
from native_sockets import register,unregister
from ue5_editor_skeleton import read_skeleton
root=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
axis=Matrix(((0,1,0,0),(1,0,0,0),(0,0,1,0),(0,0,0,1)))
def local(fields):
    t=fields['RelativeLocation'];p,y,r=map(math.radians,fields['RelativeRotation']);s=fields['RelativeScale3D'];return axis@Matrix.Translation(Vector(t)*.01)@Matrix.Rotation(y,4,'Z')@Matrix.Rotation(-p,4,'Y')@Matrix.Rotation(-r,4,'X')@Matrix.Diagonal((*s,1.))@axis
bpy.ops.wm.read_factory_settings(use_empty=True);report={}
for rel in ('Variant_Combat/Lvl_Combat.umap','Variant_SideScrolling/Lvl_SideScrolling.umap'):
    p=root/rel;actors,skips=placements(root,p);collection,result=reconstruct_static_map(str(p),components=True,cooked_profile='5.6');bpy.context.view_layer.update();actual={(o['UE_source_actor_package'],o['UE_actor'],o['UE_component_name']):o for o in collection.objects if o.get('UE_component_name')};err=0.
    for a in actors:
        matrices={};objects={}
        for c in a['components']:
            want=matrices.get(c['parent'],Matrix.Identity(4))@local(c['fields']);o=actual[a['source'],a['actor'],c['name']];matrices[c['index']]=want;objects[c['index']]=o
            assert o.parent==objects.get(c['parent']);err=max(err,max(abs(o.matrix_world[i][j]-want[i][j]) for i in range(4) for j in range(4)))
            if c['package']:assert o['UE_mesh_package']==c['package']
            if o.type=='MESH':
                for i,pkg in enumerate(c['overrides']):
                    if i<len(o.material_slots) and pkg:assert o.material_slots[i].material['UE_material_package']==pkg
    assert err<.0001 and result['component_report']['actors']==len(actors)
    report[rel]=dict(result['component_report'],max_world_matrix_error=err);print('COMPONENT_PASS',rel,report[rel],flush=True)
# Independent save/reopen and actual UI batch reuse with components enabled.
import uproject_browser as browser
browser.register();state=bpy.context.scene.ueimport_project;state.project_path=os.environ['UE56_EDITOR_PROJECT'];state.batch_scope='ALL_MAPS';state.cooked_profile='5.6';state.components=True;state.static_materials=False;state.job_filter='Lvl_Combat';assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert len(state.job_items)==1;assert bpy.ops.ueimport.batch_import()=={'FINISHED'}
n=len(bpy.data.objects);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));state=bpy.context.scene.ueimport_project;assert bpy.ops.ueimport.refresh_jobs()=={'FINISHED'};assert bpy.ops.ueimport.batch_import()=={'FINISHED'};rr=json.loads(bpy.data.texts[state.batch_report].as_string());assert rr['results'][0]['reused'] and len(bpy.data.objects)==n;report['batch_reuse']=True
# Existing native animation fixture and live socket operator on full and simplified rigs.
bpy.ops.wm.open_mainfile(filepath=os.environ['UE56_SOCKET_INPUT']);register();rigs=[o for o in bpy.data.objects if o.type=='ARMATURE'];full=next(o for o in rigs if len(o.data.bones)==161);source=read_skeleton(root/'Characters/Mannequins/Meshes/SK_Mannequin.uasset');recs=source['sockets'];assert len(recs)==5;counts={}
for rig in rigs:
    bpy.ops.object.select_all(action='DESELECT');full.select_set(True);rig.select_set(True);bpy.context.view_layer.objects.active=rig
    assert bpy.ops.object.ue_create_socket_anchors(available_only=rig!=full)=={'FINISHED'}
    anchors=[o for o in rig.children if o.get('UE_socket_name')];counts[rig.name]=len(anchors);assert len(anchors)==sum(r['bone'] in rig.data.bones for r in recs)
    assert set(json.loads(rig['UE_omitted_socket_names']))=={r['name'] for r in recs if r['bone'] not in rig.data.bones}

def verify():
    bpy.context.view_layer.update();err=0.
    for rig in rigs:
        for o in rig.children:
            if not o.get('UE_socket_name'):continue
            r=next(r for r in recs if r['name']==o['UE_socket_name']);p,y,rr=[math.radians(v)/2 for v in r['rotation_pyr']];sp,cp,sy,cy,sr,cr=math.sin(p),math.cos(p),math.sin(y),math.cos(y),math.sin(rr),math.cos(rr);q=Quaternion((cr*cp*cy+sr*sp*sy,cr*sp*sy-sr*cp*cy,-cr*sp*cy-sr*cp*sy,cr*cp*sy-sr*sp*cy));loc=axis@Matrix.LocRotScale(Vector(r['location_cm'])*.01,q,Vector(r['scale']))@axis;b=rig.data.bones[r['bone']];v=b['UE_world_matrix_m'];rest=Matrix([v[i:i+4] for i in range(0,16,4)]);want=rig.matrix_world@rig.pose.bones[b.name].matrix@b.matrix_local.inverted()@rest@loc;err=max(err,max(abs(o.matrix_world[i][j]-want[i][j]) for i in range(4) for j in range(4)))
    return err
errors=[];orig=[];scene=bpy.context.scene
for frame in (1,12,24,36,46):
    scene.frame_set(frame);errors.append(verify());orig.append(next(o for o in full.children if o.get('UE_socket_name')=='HandGrip_R').matrix_world.translation.copy())
assert max(errors)<1e-5 and max((x-orig[0]).length for x in orig)>.01
socket_out=out.with_name('shootersam_live_sockets_060.blend');bpy.ops.wm.save_as_mainfile(filepath=str(socket_out));bpy.ops.wm.open_mainfile(filepath=str(socket_out));rigs=[o for o in bpy.data.objects if o.type=='ARMATURE'];bpy.context.scene.frame_set(24);assert verify()<1e-5
report['sockets']=dict(counts=counts,max_matrix_error=max(errors),reopen=True);out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('COMPONENT_SOCKET_REOPEN_PASS',report['sockets'],flush=True)
