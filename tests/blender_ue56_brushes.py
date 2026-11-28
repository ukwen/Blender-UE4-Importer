"""Original brush polygons, transforms, normals, rendering exclusion and persistence."""
import json, os, sys, math
from pathlib import Path
import bpy
from mathutils import Vector, Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_brushes import records, extend_brushes
from ue5_full_scene import reconstruct
from project_session import new_ids
from ue5_blueprint import read_tables
from ue5_editor_tags import export_tags
import struct
content=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
a=content/'MyStuff/Maps/MainLevel.umap';b=content/'MyStuff/Maps/TestLevel.umap'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
root=bpy.data.collections.new('MainLevel source operands');scene.collection.children.link(root)
main=extend_brushes(content,a,root);testroot,full=reconstruct(str(b),partial=True);test=full['stages']['brushes']
assert main['operands']==45 and test['operands']==8
assert full['coverage']['representation_counts']['brush_operand_guide']==8
assert full['counts']['brush_operand_objects']==8 and full['counts']['meshes']==10,full['counts']
source={};counts={}
for p,c in [(a,root),(b,testroot)]:
    meta,raw,_,exports,ref,_=read_tables(p);brushes={e['name']:e for e in exports if e['kind']=='Brush'}
    objs=[o for o in c.all_objects if o.get('UE_brush_operand')];counts[p.stem]=len(objs)
    for o in objs:
        actor=brushes[o['UE_actor']];at=export_tags(raw,actor,meta['names']);mi=struct.unpack('<i',at['Brush']['data'])[0];co=ref(struct.unpack('<i',at['BrushComponent']['data'])[0]);model=ref(mi);pi=struct.unpack_from('<i',raw,model['offset']+model['script_end']+102)[0];poly=ref(pi)
        # Independent offset walk of the exact source bytes, not builder records.
        start=poly['offset']+poly['script_end'];n=struct.unpack_from('<i',raw,start+4)[0];j=start+8;faces=[];normals=[]
        for _ in range(n):
            normals.append(struct.unpack_from('<3f',raw,j+12));k=struct.unpack_from('<i',raw,j+48)[0];faces.append([struct.unpack_from('<3f',raw,j+52+12*i) for i in range(k)]);j+=128+12*k
        assert j==poly['offset']+poly['size']
        ct=export_tags(raw,co,meta['names']);fields={k:struct.unpack('<3d',ct[k]['data']) if k in ct else default for k,default in [('RelativeLocation',(0.,0.,0.)),('RelativeRotation',(0.,0.,0.)),('RelativeScale3D',(1.,1.,1.))]}
        source[o.name]=(faces,normals,fields)

def verify():
    bpy.context.view_layer.update();mx=mn=mt=ms=mw=mr=0.;total=0;matrices={}
    for name,(faces,normals,fields) in source.items():
        o=bpy.data.objects[name];assert o.hide_render and o.display_type=='WIRE' and all(c.hide_render for c in o.users_collection)
        assert len(o.data.polygons)==len(faces)
        t=fields['RelativeLocation'];s=fields['RelativeScale3D'];mt=max(mt,max(abs(v-w) for v,w in zip(o.location,(t[1]*.01,t[0]*.01,t[2]*.01))));ms=max(ms,max(abs(v-w) for v,w in zip(o.scale,(s[1],s[0],s[2]))))
        pitch,yaw,roll=map(math.radians,fields['RelativeRotation']);rotation=Matrix.Rotation(-yaw,3,'Z')@Matrix.Rotation(pitch,3,'X')@Matrix.Rotation(roll,3,'Y')
        mr=max(mr,max(abs(rotation[i][j]-o.rotation_euler.to_matrix()[i][j]) for i in range(3) for j in range(3)))
        transform=Matrix.Translation((t[1]*.01,t[0]*.01,t[2]*.01))@rotation.to_4x4()@Matrix.Diagonal((s[1],s[0],s[2],1.))
        # Check exact face vertex sets and saved normal correspondence.
        for f,pts,n in zip(o.data.polygons,faces,normals):
            actual=[o.data.vertices[i].co for i in f.vertices];expected=[Vector((v[1]*.01,v[0]*.01,v[2]*.01)) for v in pts];assert len(actual)==len(expected)
            mx=max(mx,max(min((x-y).length for y in actual) for x in expected));mn=max(mn,(f.normal-Vector((n[1],n[0],n[2])).normalized()).length);total+=len(expected)
            mw=max(mw,max(min((transform@x-o.matrix_world@y).length for y in actual) for x in expected))
        matrices[name]=[list(v) for v in o.matrix_world]
    assert mx<1e-5 and mn<1e-4 and mt<.001 and ms<1e-5 and mw<.001 and mr<1e-6,(mx,mn,mt,ms,mw,mr)
    return dict(max_local_vertex_error_m=mx,max_normal_error=mn,max_translation_error_m=mt,max_scale_error=ms,max_world_vertex_error_m=mw,max_rotation_matrix_error=mr,source_face_corners=total),matrices
pre,mats=verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));post,mats2=verify();assert mats==mats2
report=dict(main=main,test=test,counts=counts,pre=pre,post=post,reopen=True,max_reopen_matrix_error=0,scope='Source brush operands only, not compiled BSP or rendered geometry; MainLevel brush-only stage, TestLevel full scene')
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('BRUSH_PASS',report,flush=True)
