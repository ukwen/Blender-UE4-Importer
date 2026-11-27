"""Cooperative job runner; only completed jobs are retained on cancellation."""
import json
from pathlib import Path


def publish_report(name,report):
    import bpy
    text=bpy.data.texts.new(name); text.write(json.dumps(report,indent=2)); return text.name


def run_jobs(plan,profile='4.27',materials=True,components=True,partial=False,physics=False,all_lods=False):
    import bpy
    if plan['scope'] in ('GEOMETRY','MAP_GEOMETRY'):
        from project_geometry import iter_geometry_folder,finish_gallery
        it=iter_geometry_folder(plan['project'],plan['folder'],profile,physics,plan['jobs'],all_lods=all_lods)
        last=None
        try:
            while True:
                try: last=next(it)
                except StopIteration as stop:
                    if last is None: last=stop.value
                    return
                collection,report=last
                yield dict(job=report['assets'][-1]['package'],status=report['assets'][-1]['status'],result=report['assets'][-1],collection=collection.name)
        finally:
            it.close()
            if last is not None: finish_gallery(*last)
    else:
        from static_scene import reconstruct_static_map
        stores=(bpy.data.objects,bpy.data.collections,bpy.data.meshes,bpy.data.armatures,bpy.data.materials,bpy.data.images,bpy.data.texts,bpy.data.node_groups,bpy.data.actions)
        for path in plan['jobs']:
            before={x.as_pointer() for store in stores for x in store}
            try:
                collection,report=reconstruct_static_map(path,materials=materials,allow_partial_materials=partial,cooked_profile=profile,components=components)
                result=dict(job=path,status='completed',collection=collection.name,report=collection['UE_report'],static=report['actor_status'],foliage=report.get('foliage_report',{}).get('instances',0),components=report.get('component_report',{}).get('status',{}))
                result['has_unresolved_static']=any(k!='reconstructed' and v for k,v in result['static'].items())
                yield result
            except Exception as exc:
                created=[x for store in stores for x in store if x.as_pointer() not in before]
                if created: bpy.data.batch_remove(ids=created)
                yield dict(job=path,status='failed',detail=f'{type(exc).__name__}: {exc}')
