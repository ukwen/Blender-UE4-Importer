import unittest
from material_gap_diagnostics import material_gaps

class MaterialGaps(unittest.TestCase):
    def test_hard_closure_only_and_cycles(self):
        deps={'dependencies':{'/Game/M':{'status':'available'},'/Game/T':{'status':'missing_game'},'/Game/S':{'status':'missing_game'},'/Game/U':{'status':'available'}},'records':{'/Game/M':{'references':['/Game/P','/Game/U'],'soft_references':['/Game/S']},'/Game/P':{'references':['/Game/M','/Game/T']}}}
        r=material_gaps({'/Game/M':{'status':'partial','issues':['unsupported']},'/Game/S':{'status':'supported_pbr_subset'}},deps)
        self.assertEqual(r['distinct_missing_packages'],['/Game/T']);self.assertEqual(r['materials'][0]['unknown_tables'],['/Game/U']);self.assertEqual(len(r['materials']),1)
    def test_saved_surface_references(self):
        d={'dependencies':{'/Game/D':{'status':'missing_game'},'/Game/L':{'status':'missing_game'}},'records':{}}
        r=material_gaps({},d,[('/Game/D','decal_projector'),('/Game/D','decal_projector'),('/Game/L','landscape_surface')])
        self.assertEqual(r['distinct_missing_packages'],['/Game/D','/Game/L']);self.assertEqual(r['materials'][0]['uses'],['decal_projector']);self.assertEqual(r['materials'][1]['status'],'not_reconstructed')
