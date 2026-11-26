import sys,pathlib,collections,json,os,traceback
import bpy
from mathutils import Vector
sys.path.insert(0,str(pathlib.Path(__file__).resolve().parents[1]))
import uasset,umap,legacy_static as ls
root=pathlib.Path(os.environ['UE_WESTERN_PROJECT']).resolve(); output=os.environ['UE_WESTERN_OUTPUT']
bpy.ops.wm.read_factory_settings(use_empty=True)
cache={}; stats=[]; errors=[]
for p in sorted(root.rglob('*.uasset')):
 with uasset.UAsset(str(p)) as a:
  for e in a.exports:
   if e.export_class_type!='StaticMesh': continue
   try:
    d=ls.read_legacy_static(e);m=ls.build_legacy_static(d); key='/Game/'+p.relative_to(root/'Content').with_suffix('').as_posix();cache[key]=m
    assert len(m.polygons)==len(d['slots']); assert len(m.vertices)==len(d['points'])+3*m['UE_duplicate_faces_split']; assert len(m.uv_layers)==sum(bool(u) for u in d['uv']); assert all(v.value==d['sections'][j][0] for v,j in zip(m.attributes['UE_source_material_index'].data,d['slots']))
    stats.append(dict(package=key,vertices=len(m.vertices),triangles=len(m.polygons),split_faces=m['UE_duplicate_faces_split'],materials=len(d['materials'])))
   except Exception as exc:errors.append((p.name,str(exc)));print('FAIL',p.name,repr(exc),flush=True)
assert len(stats)==325 and not errors
assert sum(x['triangles'] for x in stats)==228484 and sum(x['vertices'] for x in stats)==130412 and sum(x['split_faces'] for x in stats)==16
print('MESHES',len(stats),collections.Counter(x['materials'] for x in stats),sum(x['vertices'] for x in stats),sum(x['triangles'] for x in stats),'ERRORS',errors,flush=True)
levels=[]
for p in sorted(root.rglob('*.umap')):
 coll=bpy.data.collections.new(p.stem);bpy.context.scene.collection.children.link(coll);status=collections.Counter();unresolved=[];actors=[];roots={}; referenced=set();location_error=0.
 with uasset.UAsset(str(p)) as a:
  for e in a.exports:
   if e.export_class_type!='StaticMeshActor':continue
   try:
    e.ReadProperties(True);r=e.properties.TryGetValue('RootComponent');c=e.properties.TryGetValue('StaticMeshComponent');r.ReadProperties(False);c.ReadProperties(False);ref=c.properties.TryGetValue('StaticMesh');key=ref.import_ref.object_name;referenced.add(key);m=cache.get(key);o=bpy.data.objects.new(e.properties.TryGetValue('ActorLabel',e.object_name),m);coll.objects.link(o);o.rotation_mode='YXZ';umap.Transform(r,o);o['UE_actor']=e.object_name;o['UE_mesh_package']=key;o['UE_geometry_status']='reconstructed' if m else 'missing';status[o['UE_geometry_status']]+=1;actors.append((r,o));roots[id(r)]=o
    v=r.properties.TryGetValue('RelativeLocation');
    if v:location_error=max(location_error,(o.location-Vector((v.y*.01,v.x*.01,v.z*.01))).length)
   except Exception as exc:status['failed']+=1;unresolved.append([e.object_name,str(exc)])
  for r,o in actors:
   parent=r.properties.TryGetValue('AttachParent');
   if parent:
    if id(parent) in roots:o.parent=roots[id(parent)]
    else:unresolved.append([o.name,'parent unavailable'])
  other=collections.Counter(e.export_class_type for e in a.exports if e.export_class_type in ('SkeletalMeshActor','FoliageInstancedStaticMeshComponent','InstancedFoliageActor'))
 result=dict(map=p.name,status=dict(status),unique_referenced=len(referenced),unique_reconstructed=len({o.data.as_pointer() for r,o in actors if o.type=='MESH'}),missing=sorted(k for k in referenced if k not in cache),unresolved=unresolved,other_actors=dict(other),location_error_m=location_error);levels.append(result);print('MAP',result,flush=True)
 coll['UE_geometry_only']=True
assert {r['map']:r['status'] for r in levels}=={'Demonstration.umap':{'reconstructed':1994,'missing':1},'Overview.umap':{'reconstructed':322,'missing':1}}
assert all(not r['unresolved'] and r['missing']==['/Engine/BasicShapes/Cube'] for r in levels)
# Hide the overview gallery so demonstration level opens visibly.
bpy.data.collections['Overview'].hide_viewport=True;bpy.data.collections['Overview'].hide_render=True
report=dict(meshes=stats,errors=errors,levels=levels)
text=bpy.data.texts.new('Western Frontier import report.json');text.write(json.dumps(report,indent=2));
bpy.ops.wm.save_as_mainfile(filepath=output);bpy.ops.wm.open_mainfile(filepath=output)
assert len(bpy.data.collections['Demonstration'].objects)==1995 and len(bpy.data.collections['Overview'].objects)==323
pathlib.Path(os.environ['UE_WESTERN_REPORT']).write_text(json.dumps(report,indent=2));print('REOPEN_PASS')
