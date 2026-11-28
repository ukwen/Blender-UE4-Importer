import os, shutil, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
from source_recovery import plan,restore,_target
from types import SimpleNamespace

class SourceRecoveryTests(unittest.TestCase):
    def test_target_no_overwrite_and_mount_guards(self):
        with tempfile.TemporaryDirectory() as d:
            c=Path(d).resolve();p=_target(c,'/Game/A/B');self.assertEqual(p,c/'A/B.uasset')
            for k in ('/Engine/A','/Game/../A','/Game/__ExternalActors__/A','/Game/A\\B','/Game/A//B'):
                with self.assertRaises(ValueError):_target(c,k)
            p.parent.mkdir();p.with_suffix('.ubulk').touch()
            with self.assertRaises(ValueError):_target(c,'/Game/A/B')
            p.with_suffix('.ubulk').unlink();p.touch()
            with self.assertRaises(ValueError):_target(c,'/Game/A/B')
            p.unlink();p.symlink_to(c/'absent')
            with self.assertRaises(ValueError):_target(c,'/Game/A/B')

@unittest.skipUnless(os.environ.get('UE56_EDITOR_PROJECT'),'Original fixture required')
class OriginalSourceRecoveryTests(unittest.TestCase):
    def test_exact_identity_staleness_and_atomic_failure(self):
        src=Path(os.environ['UE56_EDITOR_PROJECT']).parent/'Content'
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);project=root/'P';content=project/'Content';content.mkdir(parents=True);(project/'P.uproject').write_text('{}');level=content/'L.umap';level.touch();folder=root/'Recovery';folder.mkdir()
            files=[next(src.rglob('SM_Cube.uasset')),next(src.rglob('SM_DoorFrame_Edge.uasset'))];keys=['/Game/'+p.relative_to(src).with_suffix('').as_posix() for p in files]
            for i,p in enumerate(files):shutil.copy2(p,folder/f'renamed_{i}.uasset')
            def audit(p,l):
                dependencies={k:dict(status='available' if (content/f'{k[6:]}.uasset').is_file() else 'missing_game',hard=['/Game/L'],soft=[]) for k in keys}
                return dict(dependencies=dependencies,unresolved_hard=sum(v['status']!='available' for v in dependencies.values()),unresolved_soft_only=0,unknown_tables=[])
            p=SimpleNamespace(dir=str(project))
            with patch('source_recovery.audit',audit):
                r=plan(p,level,folder);self.assertEqual(r['counts'],{'ready':2})
                self.assertEqual(len(list(content.rglob('*.uasset'))),0)
                shutil.copy2(files[0],folder/'duplicate.uasset');self.assertEqual(plan(p,level,folder)['counts'],{'ambiguous':1,'ready':1})
                with self.assertRaisesRegex(ValueError,'plan changed'):restore(p,level,folder,r)
                (folder/'duplicate.uasset').unlink();self.assertEqual(plan(p,level,folder),r)
                orig=os.link;calls=[]
                def fail(a,b):
                    calls.append(b)
                    if len(calls)==2:raise OSError('Injected publication error')
                    return orig(a,b)
                with patch('source_recovery.os.link',fail):
                    with self.assertRaisesRegex(OSError,'Injected'):restore(p,level,folder,r)
                self.assertEqual(list(content.rglob('*.uasset')),[]);self.assertEqual(list(content.rglob('.ue-recovery-*')),[])
                result,deps=restore(p,level,folder,r);self.assertEqual(len(result['restored']),2);self.assertEqual(deps['unresolved_hard'],0)
                for f,k in zip(files,keys):self.assertEqual(f.read_bytes(),(content/f'{k[6:]}.uasset').read_bytes())
                with self.assertRaisesRegex(ValueError,'plan changed'):restore(p,level,folder,r)
