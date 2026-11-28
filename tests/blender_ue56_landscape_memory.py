"""Fresh-process original level benchmark. Compare digest and counts across versions.
Peak RSS captured before diagnostic buffer allocation; no total memory portability claim.
"""
import os,sys,json,resource,hashlib,time
from array import array
from pathlib import Path
import bpy
sys.path.insert(0,os.environ.get('UE_BENCH_SOURCE',str(Path(__file__).resolve().parents[1])))
from import_workflow import table_scope
from ue5_full_scene import reconstruct
p=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content/MyStuff/Maps/MainLevel.umap'
out=Path(os.environ['UE56_EDITOR_OUTPUT']);budget=int(os.environ.get('UE_MEMORY_CACHE_BUDGET','0'))
bpy.ops.wm.read_factory_settings(use_empty=True)
start=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024;t=time.perf_counter()
with table_scope(budget):root,report=reconstruct(str(p),partial=True)
elapsed=time.perf_counter()-t;peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024

def snapshot():
    ob=next(o for o in bpy.data.objects if o.get('UE_landscape_record'));m=ob.data;result={}
    for name,c,f,k,n in [('vertices',m.vertices,'co','f',3),('loops',m.loops,'vertex_index','i',1),('polygon_starts',m.polygons,'loop_start','i',1),('polygon_sizes',m.polygons,'loop_total','i',1),('components',m.attributes['UE_landscape_component_index'].data,'value','i',1),('atlas_uv',m.uv_layers[ob['UE_landscape_source_uv']].data,'uv','f',2)]:
        a=array(k,[0])*(len(c)*n);c.foreach_get(f,a);result[name]=hashlib.sha256(memoryview(a)).hexdigest();del a
    im=bpy.data.images[ob['UE_landscape_source_atlas']];result['packed_atlas']=hashlib.sha256(im.packed_file.data).hexdigest();result['matrix']=[list(r) for r in ob.matrix_world];return result
before=snapshot();bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out));assert snapshot()==before
result=dict(cache_budget_bytes=budget,start_peak_rss_bytes=start,process_peak_rss_bytes=peak,elapsed_seconds=elapsed,counts=report['counts'],performance=report['performance'],terrain_digest=before,reopen=True,scope='Original full MainLevel, Linux process high-water RSS before digest and save/reopen; one process per run')
out.with_suffix('.json').write_text(json.dumps(result,indent=2));print('LANDSCAPE_MEMORY_PASS',peak,elapsed,flush=True)
