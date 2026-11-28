import os, sys, json, pathlib, builtins
import bpy
sys.path.insert(0,os.environ['IMPORTER_SOURCE'])
if os.environ.get('BLOCK_LEGACY'):
    original=builtins.__import__
    def guard(name,*args,**kwargs):
        if name.split('.')[0] in ('uasset','umesh','umat','umap'):raise AssertionError('Inherited module requested: '+name)
        return original(name,*args,**kwargs)
    builtins.__import__=guard
from map_layout import import_layout
bpy.ops.wm.read_factory_settings(use_empty=True)
root=pathlib.Path(os.environ['UE_WESTERN_PROJECT']);result={}
for path in sorted(root.rglob('*.umap')):
    collection,report=import_layout(str(path));bpy.context.view_layer.update()
    result[path.name]={'report':report,'actors':{o['UE_actor']:{'name':o.name,'package':o['UE_mesh_package'],'matrix':list(v for row in o.matrix_world for v in row),'parent':o.parent['UE_actor'] if o.parent else None,'overrides':list(o.get('UE_material_overrides',[])),'override_packages':o.get('UE_material_override_packages','[]')} for o in collection.objects}}
pathlib.Path(os.environ['COMPARE_OUTPUT']).write_text(json.dumps(result,sort_keys=True,indent=2));print({k:(len(v['actors']),len(v['report']['skipped'])) for k,v in result.items()})
