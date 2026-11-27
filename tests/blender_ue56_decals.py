"""Verify original saved decal guides against independently composed transforms."""
import bpy,math,os,sys,json
from pathlib import Path
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_decals import records,extend_decals
project=Path(os.environ['UE56_EDITOR_PROJECT']);c=project.parent/'Content';p=c/'MyStuff/Maps/MainLevel.umap';out=Path(os.environ['UE56_EDITOR_OUTPUT']);bpy.ops.wm.read_factory_settings(use_empty=True)
root=bpy.data.collections.new('Decal test');bpy.context.scene.collection.children.link(root);r=extend_decals(c,p,root);assert r['projector_anchors']==561 and r['size_guides']==549 and r['rendered_decals']==0 and r['material_status']=={'missing':561} and not r['skipped']
expected={x['actor']:x for x in records(c,p)['records']};swap=Matrix(((0,1,0),(1,0,0),(0,0,1)))
def verify():
    bpy.context.view_layer.update();root=bpy.data.collections['Decal test'];obs=[o for o in root.all_objects if o.get('UE_decal_projector')];assert len(obs)==561 and len(root.all_objects)==1110;poserr=axiserr=0.
    for o in obs:
        x=expected[o['UE_actor']];assert o.hide_render and o.type=='EMPTY' and json.loads(o['UE_decal_record'])==json.loads(json.dumps(x));f=x['fields'];p,y,r=map(math.radians,f['RelativeRotation']);R=Matrix.Rotation(y,3,'Z')@Matrix.Rotation(-p,3,'Y')@Matrix.Rotation(-r,3,'X');S=Matrix.Diagonal(Vector(f['RelativeScale3D']));M=swap@R@S@swap;pos=swap@Vector(f['RelativeLocation'])*.01;poserr=max(poserr,(o.matrix_world.translation-pos).length);axiserr=max(axiserr,max(abs(o.matrix_world[i][j]-M[i][j]) for i in range(3) for j in range(3)))
        s=x['decal_size_cm'];assert len(o.children)==(1 if s else 0)
        if s:
            g=o.children[0];assert g.type=='EMPTY' and g.hide_render and g.empty_display_type=='CUBE';assert (g.scale-swap@Vector(s)*.01).length<1e-5
    assert poserr<.001 and axiserr<.001,(poserr,axiserr)
    return dict(anchors=len(obs),size_guides=549,max_position_error_m=poserr,max_linear_matrix_component_error=axiserr)
a=verify();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));b=verify();out.with_suffix('.json').write_text(json.dumps(dict(before=a,after=b,missing_material_packages=len({x['material_package'] for x in expected.values()}),rendered_decals=0,scope='Saved projector guides only'),indent=2));print('DECAL_ACCEPTANCE_PASS',a,b,flush=True)
