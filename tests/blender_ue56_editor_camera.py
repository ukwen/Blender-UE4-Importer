"""Actual Blender camera operator, independent saved transform checks and reopen."""
import bpy, math, sys, os, json
from pathlib import Path
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_camera import records
import uproject_browser as browser
project=Path(os.environ['UE56_EDITOR_PROJECT']);root=project.parent/'Content';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True);browser.register()
scene=bpy.context.scene;d=bpy.data.cameras.new('Existing user camera');sentinel=bpy.data.objects.new('Existing user camera',d);scene.collection.objects.link(sentinel);scene.camera=sentinel;sentinel.location=(1,2,3)
s=scene.ueimport_project;s.project_path=str(project);assert bpy.ops.ueimport.scan_project()=={'FINISHED'};expected={}
for stem,n in [('MainLevel',6),('TestLevel',1)]:
    p=root/f'MyStuff/Maps/{stem}.umap';s.active=next(i for i,m in enumerate(s.maps) if Path(m.filepath)==p);data=records(root,p);expected[str(p.resolve())]=data;assert len(data['records'])==n and not data['skipped'];assert bpy.ops.ueimport.camera_preview()=={'FINISHED'};count=len(bpy.data.objects)
    try:assert bpy.ops.ueimport.camera_preview()=={'CANCELLED'}
    except RuntimeError as e:assert 'already imported' in str(e)
    assert len(bpy.data.objects)==count

def verify():
    bpy.context.view_layer.update();scene=bpy.context.scene;assert scene.camera.name=='Existing user camera' and tuple(scene.camera.location)==(1,2,3);poserr=direrr=uperr=0.;nc=0
    # Independent Unreal rotation composition and axis/length conversion.
    swap=Matrix(((0,1,0),(1,0,0),(0,0,1)))
    def transform(f):
        p,y,r=map(math.radians,f['RelativeRotation']);R=Matrix.Rotation(y,3,'Z')@Matrix.Rotation(-p,3,'Y')@Matrix.Rotation(-r,3,'X');T=Vector(f['RelativeLocation']);return Matrix.Translation(T)@R.to_4x4()
    for source,data in expected.items():
        collection=next(c for c in bpy.data.collections if c.get('UE_camera_source')==source);assert len(collection.objects)==4*len(data['records'])
        report=json.loads(bpy.data.texts[collection['UE_report']].as_string());assert len(report['records'])==len(data['records']);cams={o['UE_actor']:o for o in collection.objects if o.type=='CAMERA'}
        for record in data['records']:
            a,b,c=record['components'];p=b['properties'];x,y,z=p['SocketOffset'];M=transform(a['fields'])@transform(b['fields'])@Matrix.Translation((x-p['TargetArmLength'],y,z))@transform(c['fields']);camera=cams[record['actor']];pos=swap@M.translation*.01;forward=swap@M.to_3x3()@Vector((1,0,0));up=swap@M.to_3x3()@Vector((0,0,1));actual=camera.matrix_world
            poserr=max(poserr,(actual.translation-pos).length);direrr=max(direrr,(actual.to_3x3()@Vector((0,0,-1))-forward).length);uperr=max(uperr,(actual.to_3x3()@Vector((0,1,0))-up).length)
            assert camera.parent.parent.parent is not None and camera['UE_fov_source']=='preview_default_not_serialized';assert abs(math.degrees(camera.data.angle_x)-90)<1e-4;assert camera['UE_preview_only'];assert json.loads(camera['UE_camera_record'])==json.loads(json.dumps(record));nc+=1
    assert nc==7 and poserr<1e-4 and direrr<1e-5 and uperr<1e-5,(nc,poserr,direrr,uperr)
    return dict(cameras=nc,max_position_error_m=poserr,max_forward_vector_error=direrr,max_up_vector_error=uperr)
a=verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));b=verify();report=dict(before=a,after=b,duplicate_rejected=True,active_camera_preserved=True,source_fov_serialized=0,scope='Unoccluded saved camera rig previews; no runtime camera position or FOV equivalence');out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('CAMERA_ACCEPTANCE_PASS',report,flush=True)
