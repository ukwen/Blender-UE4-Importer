"""Linux fresh-process peak RSS measurement of an original map import.
Peak includes Blender startup, dependencies and scene data; not cache-only memory.
"""
import json, os, sys, resource
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from import_workflow import table_scope
from ue5_full_scene import reconstruct
project=Path(os.environ['UE56_EDITOR_PROJECT']);p=project.parent/'Content/MyStuff/Maps/MainLevel.umap';out=Path(os.environ['UE56_EDITOR_OUTPUT']);budget=int(os.environ['UE_MEMORY_CACHE_BUDGET'])
bpy.ops.wm.read_factory_settings(use_empty=True)
start=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
with table_scope(budget):
    root,report=reconstruct(str(p),partial=True)
peak=resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*1024
result=dict(map=str(p),cache_budget_bytes=budget,start_peak_rss_bytes=start,process_peak_rss_bytes=peak,counts=report['counts'],performance=report['performance'],scope='Linux process high-water RSS including Blender startup; one fresh process per budget; no cross-platform or causal guarantee')
out.write_text(json.dumps(result,indent=2));print('MEMORY_PASS',result,flush=True)
