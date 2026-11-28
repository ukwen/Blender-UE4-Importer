"""Real mixed package gallery, explicit refusal and opt-in historical mesh route."""
import importlib.abc,json,os,shutil,sys,tempfile
from pathlib import Path
from unittest.mock import patch
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError(fullname)
block=Block();assert CORE.isdisjoint(sys.modules);sys.meta_path.insert(0,block)
from asset_entrypoints import import_mesh
from project_geometry import import_geometry_folder
from project_preflight import preflight
from project_session import new_ids
from editor_static522 import UnsupportedProfile
bpy.ops.wm.read_factory_settings(use_empty=True)
assets=Path(os.environ['UASSETAPI_ASSETS']);matya=Path(os.environ['MATYA_ASSETS'])
western=Path(os.environ['UE_WESTERN_PROJECT']);classic=next(western.rglob('SM_Particle_Smoke_01.uasset'))
with tempfile.TemporaryDirectory() as folder:
    root=Path(folder);descriptor=root/'Mixed.uproject';descriptor.write_text('{"FileVersion":3,"EngineAssociation":"4.27"}')
    content=root/'Content';content.mkdir()
    bp=assets/'TestEditorAssets/TestActorBP.uasset';split=assets/'TestJson/ABP_SMG_A.uasset';static=matya/'4.27/SM_Worm.uasset';skeletal=matya/'4.27/SK_Worm.uasset'
    for p in (bp,split,split.with_suffix('.uexp'),static,static.with_suffix('.uexp'),skeletal,skeletal.with_suffix('.uexp'),classic):shutil.copyfile(p,content/p.name)
    # Controlled unsupported version label: never claim this is an original 518 editor mesh.
    original=classic.read_bytes();bad=bytearray(original);bad[12:16]=(518).to_bytes(4,'little');(content/'UnknownVersion.uasset').write_bytes(bad)
    plan=preflight(descriptor,'GEOMETRY');assert '/Game/TestActorBP' not in plan['seeds'] and '/Game/ABP_SMG_A' not in plan['seeds']
    assert '/Game/UnknownVersion' in plan['seeds']
    collection,report=import_geometry_folder(descriptor,profile='4.27')
    by={r['package']:r for r in report['assets']}
    assert report['counts']=={'skipped_non_geometry':2,'reconstructed':3,'unsupported':1},report
    assert by['/Game/ABP_SMG_A']['class']=='NonGeometry' and by['/Game/TestActorBP']['class']=='NonGeometry'
    assert by['/Game/SK_Worm']['bones']==6
    before=set(new_ids())
    for path,profile in ((bp,'NONE'),(split,'4.27'),(content/'UnknownVersion.uasset','NONE')):
        try:import_mesh(path,False,False,profile)
        except (ValueError,NotImplementedError):pass
        else:raise AssertionError('Non-geometry or unknown profile accepted')
        assert set(new_ids())==before
    # Controlled decoder refusal must propagate without retrying the old importer.
    from package_records import read_package
    meta,raw,table=read_package(classic)
    with patch('package_inspector.inspect_package',return_value={**meta,'ue4':522}),patch('package_records.read_package',return_value=({**meta,'ue4':522},raw,table)),patch('editor_static522.read_static_lods',side_effect=UnsupportedProfile('injected profile')):
        try:import_mesh(classic,False,False)
        except UnsupportedProfile:pass
        else:raise AssertionError('Expected refusal')
        assert set(new_ids())==before
    out=Path(os.environ['UE_GEOMETRY_BOUNDARY_OUTPUT']);bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
    c=next(c for c in bpy.data.collections if c.name.startswith('UE native geometry gallery'))
    assert json.loads(bpy.data.texts[c['UE_report']].as_string())==report
    assert len(c.objects)==4 and not attempts and CORE.isdisjoint(sys.modules),attempts
# Explicit opt-in compatibility stays reachable; separate from native acceptance.
sys.meta_path.remove(block)
legacy=import_mesh(classic,False,False,'LEGACY');assert len(legacy)==1 and legacy[0].type=='MESH' and 'umesh' in sys.modules
print('NATIVE_GEOMETRY_BOUNDARY_PASS',json.dumps(dict(counts=report['counts'],totals=report['totals'],native_inherited_attempts=attempts,reopen=True,explicit_legacy_route=True)),flush=True)
