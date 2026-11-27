"""Import five original UE5.7 class previews in actual Blender and reopen."""
import json,math,os,sys
from pathlib import Path
import bpy
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_blueprint import inspect_class
import skeleton_blender
root=Path(os.environ['UASSETAPI_ASSETS'])/'TestEditorUE5_7'/'Blueprints';out=Path(os.environ['UE57_BLUEPRINT_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);skeleton_blender.register();expected={}
for path in sorted(root.glob('*.uasset')):
    d=inspect_class(path);expected[str(path.resolve())]=d
    assert getattr(bpy.ops,'import').ue57_blueprint_preview(filepath=str(path))=={'FINISHED'}
    n=len(bpy.data.objects)
    try:assert getattr(bpy.ops,'import').ue57_blueprint_preview(filepath=str(path))=={'CANCELLED'}
    except RuntimeError as e:assert 'already imported' in str(e)
    assert len(bpy.data.objects)==n

def verify():
    counts={};error=0.;rotation_error=0.;swap=Matrix(((0,1,0),(1,0,0),(0,0,1)))
    for path,d in expected.items():
        c=next(c for c in bpy.data.collections if c.get('UE_blueprint_source')==path);r=json.loads(bpy.data.texts[c['UE_report']].as_string());assert r['generated_class']==d['generated_class'];lookup={o['UE_component_index']:o for o in c.objects}
        assert set(lookup)=={v['index'] for v in d['components'] if v['placement']=='anchor'}
        for x in d['components']:
            if x['placement']!='anchor':assert x['index'] not in lookup;continue
            o=lookup[x['index']];assert o.type=='EMPTY' and o['UE_preview_only'];assert o.parent==lookup.get(x['parent_index']);assert o['UE_mesh_package']==x['package'];assert json.loads(o['UE_component_properties'])==x['properties']
            f=x['fields'];t=f.get('RelativeLocation',(0.,0.,0.));p=f.get('RelativeRotation',(0.,0.,0.));s=f.get('RelativeScale3D',(1.,1.,1.));error=max(error,math.dist(tuple(o.location),(t[1]*.01,t[0]*.01,t[2]*.01)));pitch,yaw,roll=map(math.radians,p);rot=swap@Matrix.Rotation(yaw,3,'Z')@Matrix.Rotation(-pitch,3,'Y')@Matrix.Rotation(-roll,3,'X')@swap;rotation_error=max(rotation_error,max(abs(a-b) for ar,br in zip(rot,o.rotation_euler.to_matrix()) for a,b in zip(ar,br)));assert tuple(o.scale)==tuple(Vector((s[1],s[0],s[2])))
        counts[d['generated_class']]=dict(anchors=len(lookup),metadata_only=len(d['components'])-len(lookup))
    assert len(expected)==5 and sum(x['anchors'] for x in counts.values())==8 and sum(x['metadata_only'] for x in counts.values())==2
    assert error<1e-6 and rotation_error<1e-6
    return dict(classes=counts,max_position_error_m=error,max_rotation_matrix_error=rotation_error)
a=verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));b=verify();report=dict(before=a,after=b,geometry_claim=False,socket_world_placement=False,duplicate_rejected=True);out.with_suffix('.json').write_text(json.dumps(report,indent=2));print('UE57_BLUEPRINT_PREVIEW_PASS',report,flush=True)
