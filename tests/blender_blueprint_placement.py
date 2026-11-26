import bpy,sys,json,math,os
from pathlib import Path
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import uasset,blueprint_placement as bp
from native_sockets import socket_local
assets=Path(os.environ.get('UE_PLACEMENT_ASSETS','/mnt/data'))
class Project:
 def resolve_package(self,p):return str(assets/(p.rsplit('/',1)[-1]+'.uasset'))
# Use the genuine saved reference and validated character geometry; no redecoding mesh or source animation here.
bpy.ops.wm.open_mainfile(filepath=str(assets/'Goblin_live_sockets.blend'))
sockets=json.loads(next(o['UE_socket_definitions'] for o in bpy.data.objects if o.type=='ARMATURE' and o.get('UE_socket_definitions')))
bpy.ops.wm.open_mainfile(filepath=str(assets/'Goblin_level_all_standalone_skeletal.blend'))
collection=next(c for c in bpy.data.collections if c.get('UE_report'));report=json.loads(bpy.data.texts[collection['UE_report']].as_string());extra=report['component_report']
original_count=len([o for o in collection.objects if o.type=='MESH']); assert original_count==18
anchors={(o['UE_component_actor'],o['UE_component']):o for o in collection.objects if o.get('UE_component_anchor')}
records=[r for r in extra['records'] if r['reference_origin']=='CDO' and r['kind']=='SkeletalMeshComponent']; assert len(records)==15
# Append the independently verified native rigs from the source gallery, with exact reference package association from the map report.
with bpy.data.libraries.load(str(assets/'Goblin_rigged_characters.blend'),link=False) as (src,dst):
 names={r['package'].rsplit('/',1)[-1] for r in records}; dst.objects=[n for n in src.objects if n in names or n in {x+'_Armature' for x in names}]
rigs={o.name:o for o in dst.objects if o and o.type=='ARMATURE'};meshes={o.name:o for o in dst.objects if o and o.type=='MESH'}
assert len(rigs)==len(meshes)==15
for o in list(rigs.values())+list(meshes.values()): collection.objects.link(o)
cache={}; results=[]
with uasset.UAsset(str(assets/'Overview.umap')) as a:
 actors={e.object_name:e for e in a.exports if (e.export_class_type or '').startswith('BP_Chr_')}
 for rec in records:
  e=actors[rec['actor']];e.ReadProperties(False);m=e.properties.TryGetValue('Mesh');root=e.properties.TryGetValue('RootComponent');m.ReadProperties(False);root.ReadProperties(False)
  assert rec['blueprint']==bp.package4(a,e.class_index) and m.object_name==rec['component']
  placement=bp.resolve_body(Project(),e,m,root,rec['blueprint'],cache)
  assert placement['mesh']['RelativeLocation']==(0.,0.,-96.) and placement['mesh']['RelativeRotation']==(0.,270.,0.)
  mn=anchors[(e.object_name,m.object_name)];rn=anchors[(e.object_name,root.object_name)]; name=rec['package'].rsplit('/',1)[-1]; mesh=meshes[name];rig=rigs[name+'_Armature']
  assert mesh.parent==rig and mesh.modifiers[0].object==rig and rig['UE_skeleton_package'].endswith('/UE4_Mannequin_Skeleton')
  bp.place_body(rn,mn,rig,placement); status=bp.body_sockets(rig,sockets,collection);bpy.context.view_layer.update()
  # Independent composition for the genuine map's -90 yaw and inherited +270 yaw.
  t=placement['root']['RelativeLocation'];expected=Matrix.Translation(Vector((t[1],t[0],t[2]))*.01)@Matrix.Rotation(math.pi/2,4,'Z')@Matrix.Translation((0,0,-.96))@Matrix.Rotation(-3*math.pi/2,4,'Z')
  err=max(abs(rig.matrix_world[i][j]-expected[i][j]) for i in range(4) for j in range(4));assert err<5e-5
  assert mesh.modifiers[0].object==rig and len(mesh.vertex_groups)==len(rig.data.bones)
  # Check original bone-parented anchors at rest, then rotate head to demonstrate live following.
  def check_sockets():
   bpy.context.view_layer.update(); error=0
   for so in rig.children:
    if not so.get('UE_socket_name'):continue
    r=json.loads(so['UE_socket_definition']);b=rig.data.bones[r['bone']];v=b['UE_world_matrix_m'];source=Matrix([v[i:i+4] for i in range(0,16,4)]);want=rig.matrix_world@rig.pose.bones[b.name].matrix@b.matrix_local.inverted()@source@socket_local(r)
    error=max(error,max(abs(so.matrix_world[i][j]-want[i][j]) for i in range(4) for j in range(4)))
   return error
  err_socket=check_sockets(); pb=rig.pose.bones['head'];pb.rotation_mode='XYZ';pb.rotation_euler.x=.25;err_socket=max(err_socket,check_sockets());pb.rotation_euler.x=0;bpy.context.view_layer.update();assert err_socket<.0001
  mesh['UE_component_actor']=e.object_name;mesh['UE_mesh_package']=rec['package'];mesh['UE_component_status']='reconstructed';mn['UE_component_status']='reconstructed';rec.update(status='reconstructed',detail='',placement=placement,sockets=status)
  result=dict(actor=e.object_name,mesh=rec['package'],vertices=len(mesh.data.vertices),bones=len(rig.data.bones),placement_error=err,socket_error=err_socket,**status);results.append(result);print('PASS',result,flush=True)
from collections import Counter
extra['status']=dict(Counter(r['status'] for r in extra['records']));extra['body_placement_validation']=results
bpy.data.texts[collection['UE_report']].clear();bpy.data.texts[collection['UE_report']].write(json.dumps(report,indent=2))
assert len(results)==15 and len([o for o in collection.objects if o.type=='MESH'])==33
out=os.environ.get('UE_PLACEMENT_OUTPUT','/mnt/data/Goblin_level_character_bodies.blend');bpy.ops.wm.save_as_mainfile(filepath=out);bpy.ops.wm.open_mainfile(filepath=out)
collection=next(c for c in bpy.data.collections if c.get('UE_report'));assert len([o for o in collection.objects if o.type=='ARMATURE'])==30
assert sum(bool(o.get('UE_socket_name')) for o in collection.objects)==sum(r['created'] for r in results)
assert len(json.loads(bpy.data.texts[collection['UE_report']].as_string())['component_report']['body_placement_validation'])==15
Path(os.environ.get('UE_PLACEMENT_REPORT','/mnt/data/Goblin_character_placement_validation.json')).write_text(json.dumps(results,indent=2)); print('TOTAL',sum(r['created'] for r in results),sum(r['vertices'] for r in results),max(r['placement_error'] for r in results),max(r['socket_error'] for r in results))
