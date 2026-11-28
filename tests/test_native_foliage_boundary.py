"""Unknown foliage profiles must never re-enter the inherited reader."""
import builtins
import unittest
from unittest.mock import patch
from foliage_legacy import reconstruct_foliage

class FoliageBoundaryTests(unittest.TestCase):
    def test_unknown_profile_refused(self):
        real=builtins.__import__
        def guard(name,*args,**kwargs):
            if name in ('uasset','umap','umat','umesh'):
                self.fail('Inherited import '+name)
            return real(name,*args,**kwargs)
        with patch('builtins.__import__',side_effect=guard),patch('package_inspector.inspect_package',return_value=dict(ue4=518,ue5=None)):
            with self.assertRaisesRegex(NotImplementedError,'no legacy fallback'):
                reconstruct_foliage('not-loaded.umap',None,None)
