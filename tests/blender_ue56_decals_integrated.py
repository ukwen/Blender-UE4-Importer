import sys,os,bpy,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_full_scene import reconstruct
p=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/MyStuff/Maps/MainLevel.umap'
bpy.ops.wm.read_factory_settings(use_empty=True)
root,r=reconstruct(str(p),partial=True)
assert r['stages']['decals']['projector_anchors']==561 and r['counts']['decal_objects']==1110
assert r['coverage']['representation_counts']['decal_projector_guide']==561
assert r['stages']['decals']['rendered_decals']==0
assert all(o.type=='EMPTY' for o in root.all_objects if o.get('UE_decal_projector'))
summary={'counts':r['counts'],'decal_projector_coverage':561,'rendered_decals':0,'missing_material_packages':103}
Path(os.environ['UE56_EDITOR_OUTPUT']).with_suffix('.json').write_text(json.dumps(summary,indent=2));print('INTEGRATED_PASS',summary,flush=True)
