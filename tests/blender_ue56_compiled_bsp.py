"""Original compiled BSP and volume acceptance, independent source offset walk."""
import os,sys,json,struct,math,tempfile
from pathlib import Path
import bpy
from mathutils import Vector,Matrix
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_blueprint import read_tables
from ue5_editor_tags import export_tags
from ue5_editor_bsp import extend_bsp
from ue5_editor_volumes import extend_volumes
from ue5_full_scene import reconstruct
c=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
main=bpy.data.collections.new('MainLevel BSP and volumes');scene.collection.children.link(main)
a=c/'MyStuff/Maps/MainLevel.umap';b=c/'MyStuff/Maps/TestLevel.umap';mr=extend_bsp(c,a,main);mv=extend_volumes(c,a,main);root,fr=reconstruct(str(b),partial=True);tr=fr['stages']['compiled_bsp'];assert (mr['components'],mr['faces'],mr['corners'])==(17,917,4091),mr;assert (tr['components'],tr['faces'],tr['corners'])==(9,76,304),tr
assert fr['counts']['meshes']==10 and fr['counts']['volume_guide_objects']==1 and fr['coverage']['representation_counts']['volume_guide']==1
reports={a.stem:mv,b.stem:fr['stages']['volumes']}
for rel in ('ThirdPerson/Lvl_ThirdPerson','Variant_Combat/Lvl_Combat','Variant_Platforming/Lvl_Platforming','Variant_SideScrolling/Lvl_SideScrolling'):
    p=c/(rel+'.umap');reports[p.stem]=extend_volumes(c,p,main)
assert sum(x['volumes'] for x in reports.values())==12 and all(not x['skipped'] for x in reports.values())
source={}
for path,coll in [(a,main),(b,root)]:
    meta,raw,_,ex,ref,pkg=read_tables(path)
    for obj in coll.all_objects:
        if not obj.get('UE_compiled_bsp'):continue
        mo=ref(obj['UE_bsp_model_export']);base=mo['offset']+mo['script_end'];end=mo['offset']+mo['size'];off=base+62
        # Independent native offset walk, reading saved render records from source, not decoder outputs.
        for _ in range(2):stride,n=struct.unpack_from('<ii',raw,off);assert stride==12;off+=8+stride*n
        stride,n=struct.unpack_from('<ii',raw,off);assert stride==64;node_off=off+8;off+=8+stride*n;ns=struct.unpack_from('<i',raw,off)[0];surf_off=off+4;off+=4+56*ns
        stride,n=struct.unpack_from('<ii',raw,off);assert stride==24;off+=8+stride*n+8
        for _ in range(2):stride,n=struct.unpack_from('<ii',raw,off);assert stride==4;off+=8+stride*n
        outside,linked,np,nr=struct.unpack_from('<4i',raw,off);rv=off+16;assert rv+56*nr+56==end
        ce=next(e for e in ex if e['name']==obj['UE_actor'] and e['kind']=='ModelComponent');co=ce['offset']+ce['script_end'];num=struct.unpack_from('<i',raw,co+12)[0];j=co+16
        for _ in range(num):nn=struct.unpack_from('<i',raw,j+24)[0];j+=28+2*nn
        ci,nn=struct.unpack_from('<ii',raw,j);ids=struct.unpack_from('<'+'H'*nn,raw,j+8);assert j+8+nn*2==ce['offset']+ce['size']
        faces=[]
        for idx in ids:
            no=node_off+64*idx;si,first=struct.unpack_from('<ii',raw,no+20);n=raw[no+54];mat=struct.unpack_from('<i',raw,surf_off+56*si)[0];normal=struct.unpack_from('<3f',raw,no);verts=[struct.unpack_from('<14f',raw,rv+56*(first+k)) for k in range(n)];faces.append((normal,verts,pkg(mat) if mat else ''))
        source[obj.name]=faces
assert len(source)==26
# Validate source polygons and transforms for the separate non-rendering volume stage.
volume_source={}
for o in bpy.data.objects:
    if not o.get('UE_volume_guide'):continue
    d=json.loads(o['UE_volume_record']);p=c/d['source'];meta,raw,_,ex,ref,_=read_tables(p);e=next(e for e in ex if e['name']==d['actor'] and e['kind']==d['kind']);at=export_tags(raw,e,meta['names']);co=ref(struct.unpack('<i',at['BrushComponent']['data'])[0]);mo=ref(struct.unpack('<i',at['Brush']['data'])[0]);pe=ref(struct.unpack_from('<i',raw,mo['offset']+mo['script_end']+1566)[0]);j=pe['offset']+pe['script_end']+8;pts=[]
    for _ in range(6):n=struct.unpack_from('<i',raw,j+48)[0];assert n==4;pts.append([struct.unpack_from('<3f',raw,j+52+12*k) for k in range(n)]);j+=128+12*n
    assert j==pe['offset']+pe['size'];ct=export_tags(raw,co,meta['names']);fields={k:struct.unpack('<3d',ct[k]['data']) if k in ct else default for k,default in [('RelativeLocation',(0.,0.,0.)),('RelativeRotation',(0.,0.,0.)),('RelativeScale3D',(1.,1.,1.))]};volume_source[o.name]=(pts,fields)
assert len(volume_source)==12

def check():
    bpy.context.view_layer.update();pos=uv=lm=normal=geometric_normal=source_normal_error=volume_error=0.;corners=faces_count=0;matrices={}
    for name,faces in source.items():
        o=bpy.data.objects[name];assert not o.hide_render and all(not cl.hide_render for cl in o.users_collection);assert o.matrix_world==Matrix.Identity(4);mesh=o.data;assert len(mesh.polygons)==len(faces);assert mesh.uv_layers.active.name=='UV0'
        for poly,(n,rows,mat) in zip(mesh.polygons,faces):
            assert mesh.materials[poly.material_index]['UE_material_package']==mat
            geometric_normal=max(geometric_normal,(poly.normal-Vector((n[1],n[0],n[2])).normalized()).length)
            assert len(poly.loop_indices)==len(rows)
            for li,r in zip(poly.loop_indices,reversed(rows)):
                source_normal_error=max(source_normal_error,(mesh.attributes['UE_saved_render_normal'].data[li].vector-Vector((r[7],r[6],r[8]))).length);normal=max(normal,(mesh.corner_normals[li].vector-Vector((r[7],r[6],r[8])).normalized()).length);v=mesh.vertices[mesh.loops[li].vertex_index].co;pos=max(pos,(v-Vector((r[1]*.01,r[0]*.01,r[2]*.01))).length);uv=max(uv,(mesh.uv_layers['UV0'].data[li].uv-Vector((r[10],1-r[11]))).length);lm=max(lm,(mesh.uv_layers['LightmapUV'].data[li].uv-Vector((r[12],1-r[13]))).length);corners+=1
            faces_count+=1
        matrices[name]=[list(v) for v in o.matrix_world]
    for name,(pts,f) in volume_source.items():
        o=bpy.data.objects[name];assert o.hide_render and all(cl.hide_render for cl in o.users_collection)
        t,s=f['RelativeLocation'],f['RelativeScale3D'];p,y,r=map(math.radians,f['RelativeRotation']);m=Matrix.Translation((t[1]*.01,t[0]*.01,t[2]*.01))@(Matrix.Rotation(-y,3,'Z')@Matrix.Rotation(p,3,'X')@Matrix.Rotation(r,3,'Y')).to_4x4()@Matrix.Diagonal((s[1],s[0],s[2],1.))
        for poly,vs in zip(o.data.polygons,pts):
            actual=[o.matrix_world@o.data.vertices[i].co for i in poly.vertices];expected=[m@Vector((v[1]*.01,v[0]*.01,v[2]*.01)) for v in vs];volume_error=max(volume_error,max(min((x-y).length for y in actual) for x in expected))
        matrices[name]=[list(v) for v in o.matrix_world]
    assert corners==4395 and faces_count==993;assert pos<1e-5 and uv<1e-6 and lm<1e-6 and source_normal_error==0 and normal<.0005 and volume_error<.001,(pos,uv,lm,normal,volume_error)
    return dict(corners=corners,faces=faces_count,position_error_m=pos,uv_error=uv,lightmap_uv_error=lm,source_normal_error=source_normal_error,normal_error=normal,geometric_normal_error=geometric_normal,volume_world_error_m=volume_error),matrices
pre,mats=check();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));post,mats2=check();assert mats==mats2
# Render one actual source compiled face from the normal side using a diagnostic emissive material.
scene=bpy.context.scene;ob=bpy.data.objects[next(iter(source))];f=ob.data.polygons[0];center=f.center.copy();n=f.normal.copy()
for o in bpy.data.objects:o.hide_render=True
ob.hide_render=False;mat=bpy.data.materials.new('Diagnostic BSP visibility');mat.use_nodes=True;nt=mat.node_tree;nt.nodes.clear();em=nt.nodes.new('ShaderNodeEmission');em.inputs['Color'].default_value=(.2,.4,.6,1);output=nt.nodes.new('ShaderNodeOutputMaterial');nt.links.new(em.outputs[0],output.inputs['Surface']);ob.data.materials.clear();ob.data.materials.append(mat)
cam=bpy.data.cameras.new('Diagnostic');cam.type='ORTHO';cam.ortho_scale=.05;cam.clip_start=.001;cam.clip_end=10;co=bpy.data.objects.new('Diagnostic',cam);scene.collection.objects.link(co);co.location=center+n*.02;co.rotation_euler=(-n).to_track_quat('-Z','Y').to_euler();scene.camera=co
scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=4;scene.cycles.use_denoising=False;scene.render.resolution_x=8;scene.render.resolution_y=8;scene.render.resolution_percentage=100;scene.render.image_settings.file_format='OPEN_EXR';scene.render.image_settings.color_depth='32'
with tempfile.TemporaryDirectory() as d:
    scene.render.filepath=str(Path(d)/'probe.exr');bpy.ops.render.render(write_still=True);im=bpy.data.images.load(scene.render.filepath);rgb=tuple(im.pixels[4*36:4*36+3])
assert max(abs(x-y) for x,y in zip(rgb,(.2,.4,.6)))<.01,rgb
report=dict(main=mr,test=tr,volumes=reports,pre=pre,post=post,reopen=True,exact_reopen_matrices=True,cpu_visibility_probe_rgb=rgb,scope='Original saved BSP render polygons and UVs, non-rendering original volume bounds; diagnostic emission only, missing materials and runtime effects unresolved')
out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('COMPILED_BSP_PASS',json.dumps(report),flush=True)
