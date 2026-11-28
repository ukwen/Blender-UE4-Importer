"""Original split package dependency inventory via MaterialResolver, no inherited imports."""
import os,sys,tempfile,shutil,importlib.abc,json
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
forbidden={'uasset','umat','umap','umesh'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname in forbidden:
            attempts.append(fullname);raise ImportError(fullname)
assert forbidden.isdisjoint(sys.modules);sys.meta_path.insert(0,Block())
from material_stage import MaterialResolver
from project_paths import ProjectPaths
root=Path(os.environ['MATYA_ASSETS']);reports={}
for profile in ('4.18','4.27','5.0'):
    with tempfile.TemporaryDirectory() as d:
        desc=Path(d)/'Worm.uproject';desc.write_text(json.dumps(dict(FileVersion=3,EngineAssociation=profile)))
        content=desc.parent/'Content';shutil.copytree(root/profile,content)
        resolver=MaterialResolver(ProjectPaths(desc));report=resolver.audit('/Game/M_Worm')
        assert report==dict(packages=['/Game/M_Worm','/Game/T_Worm_A','/Game/T_Worm_D','/Game/T_Worm_N'],missing=[],errors={}),report
        (content/'T_Worm_D.uasset').unlink()
        missing=resolver.audit('/Game/M_Worm');assert missing['missing']==['/Game/T_Worm_D'] and not missing['errors'],missing
        (content/'M_Worm.uexp').unlink()
        invalid=resolver.audit('/Game/M_Worm');assert '/Game/M_Worm' in invalid['errors'],invalid
        reports[profile]=dict(available=len(report['packages']),missing=missing['missing'],sidecar_refused=True)
assert not attempts and forbidden.isdisjoint(sys.modules),attempts
print('SPLIT_DEPENDENCY_AUDIT_PASS',json.dumps(reports),flush=True)
