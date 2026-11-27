import unittest
from legacy_full_scene import supported, validate_tables

class LegacyProfileTests(unittest.TestCase):
    def test_exact_editor_profile_only(self):
        good=dict(status='tables_inspected',legacy=-7,ue4=508,ue5=None,licensee=0,sidecars=[])
        self.assertTrue(supported(good))
        self.assertTrue(supported(dict(good,ue4=522)))
        for changes in ({'ue4':521},{'ue5':1016},{'legacy':-8},{'licensee':1},{'sidecars':['.uexp']},{'status':'invalid_or_truncated'},{'flags':0x80000000},{'flags':0x2000}):
            self.assertFalse(supported(dict(good,**changes)),changes)

    def test_table_extents(self):
        for version,stride,export_stride in ((508,28,96),(522,36,104)):
            good=dict(status='tables_inspected',legacy=-7,ue4=version,ue5=None,licensee=0,sidecars=[],flags=0x20000,import_count=3,export_count=2,import_offset=100,export_offset=100+3*stride,header_end=100+3*stride+2*export_stride,size=1000)
            validate_tables(good)
            for changes in ({'export_offset':good['export_offset']+1},{'export_count':100},{'import_count':0},{'header_end':9999}):
                with self.assertRaises(ValueError): validate_tables(dict(good,**changes))
