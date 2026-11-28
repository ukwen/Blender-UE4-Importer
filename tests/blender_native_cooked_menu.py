"""Real cooked geometry through the main mesh menu, with inherited imports blocked."""
import importlib.abc,json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError(fullname)
assert CORE.isdisjoint(sys.modules);sys.meta_path.insert(0,Block())
from asset_entrypoints import import_mesh,register,unregister
from project_session import new_ids
root=Path(os.environ['MATYA_ASSETS']);bpy.ops.wm.read_factory_settings(use_empty=True);register()
rows=[]
for profile in ('4.18','4.27','5.0'):
    for stem in ('SM_Worm','SK_Worm'):
        path=root/profile/(stem+'.uasset');before=set(bpy.data.objects)
        assert getattr(bpy.ops,'import').umesh(filepath=str(path),materials=True,cooked_profile=profile)=={'FINISHED'}
        added=set(bpy.data.objects)-before;obj,=[o for o in added if o.type=='MESH'];mesh=obj.data
        assert (len(mesh.vertices),len(mesh.polygons))==(640,572)
        assert mesh.has_custom_normals and mesh.uv_layers and mesh.attributes.get('UE_source_tangent')
        assert mesh.materials[0]['UE_material_package']=='/Game/M_Worm' and obj['UE_unresolved_material']
        arm=obj.parent
        if stem.startswith('SK'):
            assert arm.type=='ARMATURE' and len(arm.data.bones)==6 and obj.modifiers[0].object==arm
            assert max(abs(sum(g.weight for g in v.groups)-1) for v in mesh.vertices)<1e-5
        else: assert len(added)==1
        rows.append(dict(profile=profile,asset=stem,object=obj.name,bones=len(arm.data.bones) if arm else 0))
# Original modern split samples: static cubes and the three shared Quinn LODs.
modern=Path(os.environ['UASSETAPI_ASSETS']);modern_rows=[]
for profile in ('5.4','5.5','5.6'):
    directory=modern/('TestUE'+profile.replace('.','_'))/('BpThirdPerson' if profile=='5.6' else 'BlankGame')
    path=directory/('SM_BlueCube.uasset' if profile=='5.4' else 'SM_Cube.uasset')
    obj,=import_mesh(path,True,False,profile)
    assert (len(obj.data.vertices),len(obj.data.polygons))==(24,12) and obj['UE_cooked_profile']==profile
    modern_rows.append(dict(object=obj.name,profile=profile,vertices=24,triangles=12))
quinn=next(modern.rglob('SKM_Quinn_Simple.uasset'));objects=import_mesh(quinn,True,True,'5.6')
from skeletal_lod_group import members,set_active_lod
arm=objects[0].parent;assert len(arm.data.bones)==89 and len(objects)==3
assert [(len(o.data.vertices),len(o.data.polygons)) for o in objects]==[(45993,87280),(14865,26998),(7421,12998)]
assert all(o.parent==arm for o in objects) and len(members(arm))==3
set_active_lod(arm,2);assert [o.hide_render for o in objects]==[True,True,False]
arm_name=arm.name
path=root/'4.27/SM_Worm.uasset';before=set(new_ids())
for args in [(path,True,False,'NONE'),(path,True,False,'4.18'),(path,True,True,'4.27'),(root/'4.27/M_Worm.uasset',True,False,'4.27')]:
    try: import_mesh(*args)
    except (ValueError,NotImplementedError): pass
    else: raise AssertionError('Unsupported input accepted')
    assert set(new_ids())==before
from cooked_static import build_static as real_build
with patch('cooked_static.build_static',side_effect=lambda data: (real_build(data), (_ for _ in ()).throw(ValueError('injected')))[1]):
    try: import_mesh(path,True,False,'4.27')
    except ValueError as e: assert str(e)=='injected'
    else: raise AssertionError('Injected failure accepted')
assert set(new_ids())==before
with tempfile.TemporaryDirectory() as tmp:
    output=str(Path(tmp)/'cooked.blend');bpy.ops.wm.save_as_mainfile(filepath=output);bpy.ops.wm.open_mainfile(filepath=output)
    for row in rows:
        obj=bpy.data.objects[row['object']];assert (len(obj.data.vertices),len(obj.data.polygons))==(640,572)
        assert obj['UE_cooked_profile']==row['profile'] and obj['UE_unresolved_material']
        if row['bones']: assert obj.modifiers[0].object==obj.parent and len(obj.parent.data.bones)==row['bones']
    for row in modern_rows:
        obj=bpy.data.objects[row['object']];assert (len(obj.data.vertices),len(obj.data.polygons))==(row['vertices'],row['triangles'])
    arm=bpy.data.objects[arm_name];assert arm['UE_active_lod']==2 and len(members(arm))==3
assert not attempts and CORE.isdisjoint(sys.modules);unregister()
print('NATIVE_COOKED_MENU_PASS',json.dumps(dict(worm=rows,modern=modern_rows,quinn_lods=3,quinn_bones=89)),flush=True)
