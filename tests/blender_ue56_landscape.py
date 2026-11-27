"""One-operation original level transfer; full height-grid and world-space reopen checks."""
import os,sys,json
from pathlib import Path
import bpy,numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_editor_landscape import records
from ue5_full_scene import reconstruct
from project_session import new_ids
p=Path(os.environ['UE56_EDITOR_PROJECT']);out=Path(os.environ['UE56_EDITOR_OUTPUT']);content=p.parent/'Content';level=content/'MyStuff/Maps/MainLevel.umap'
bpy.ops.wm.read_factory_settings(use_empty=True);plans,skips=records(content,level);assert len(plans)==1 and not skips
rec,grid=plans[0];root,report=reconstruct(str(level),partial=True);print('SCENE_COUNTS',report['counts'],flush=True);terrain=report['stages']['geometry']['landscape_report'];assert terrain['actors']==1 and terrain['components']==64 and terrain['vertices']==1009**2 and terrain['quads']==1008**2 and not terrain['skipped'];assert any(r['actor']=='Landscape1' and 'geometry' in r['representation'] for r in report['coverage']['records'])
assert report['counts']['armatures']==6 and report['counts']['cameras']==6

def verify():
    ob=next(o for o in bpy.data.objects if o.get('UE_landscape_record'));bpy.context.view_layer.update();assert len(ob.data.vertices)==grid.size and len(ob.data.polygons)==1008**2;assert ob['UE_unresolved_material'];co=np.empty(grid.size*3,dtype=np.float32);ob.data.vertices.foreach_get('co',co);co=co.reshape(1009,1009,3);yy,xx=np.indices(grid.shape);expected=np.stack((yy*.01,xx*.01,grid/128*.01),axis=-1);err=float(np.max(abs(co-expected)));assert err<1e-6,err
    # Independently compute world coordinates from saved root location and scale, without using importer transform helper.
    world=co.astype(np.float64)@np.array(ob.matrix_world.to_3x3()).T+np.array(ob.matrix_world.translation);truth=np.stack((-1327.2+yy*2.5,-1278+xx*2.5,190.19+grid/128*2.5),axis=-1);we=float(np.max(abs(world-truth)));assert we<.0003,we
    assert ob.data.polygons[0].normal.z>0
    return dict(local_max_error_m=err,world_max_error_m=we,world_min_m=world.min(axis=(0,1)).tolist(),world_max_m=world.max(axis=(0,1)).tolist())
a=verify();ids=set(new_ids())
try:reconstruct(str(level));raise AssertionError('duplicate accepted')
except ValueError as e:assert 'already imported' in str(e)
assert set(new_ids())==ids
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));b=verify();r=dict(terrain=terrain,scene_counts=report['counts'],before=a,after=b,reopen=True,duplicate_refused=True,missing_meshes=report['stages']['geometry']['actor_status']);out.with_suffix('.json').write_text(json.dumps(r,indent=2));print('LANDSCAPE_ACCEPTANCE_PASS',a,b,flush=True)
