import unittest
from legacy_full_scene import supported

class LegacyProfileTests(unittest.TestCase):
    def test_exact_editor_profile_only(self):
        good=dict(status='tables_inspected',legacy=-7,ue4=508,ue5=None,licensee=0,sidecars=[])
        self.assertTrue(supported(good))
        for changes in ({'ue4':522},{'ue5':1016},{'legacy':-8},{'licensee':1},{'sidecars':['.uexp']},{'status':'invalid_or_truncated'}):
            self.assertFalse(supported(dict(good,**changes)),changes)
