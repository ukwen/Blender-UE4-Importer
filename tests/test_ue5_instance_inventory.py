import unittest
from ue5_instance_inventory import scan_exports, summarize

class InstanceInventoryTests(unittest.TestCase):
    def scan(self, exports, inline=True, level='/Game/L'):
        def ref(i): return exports[i-1] if i>0 else dict(kind='Level',name='PersistentLevel',outer=0)
        return scan_exports(exports,ref,lambda i:'/Game/L','source',level,inline)
    def row(self, kind, name, outer): return dict(kind=kind,name=name,outer=outer)
    def test_inline_nested_component(self):
        rows=self.scan([self.row('Level','PersistentLevel',0),self.row('Actor','A',1),self.row('SceneComponent','root',2),self.row('InstancedStaticMeshComponent','I',3)])
        self.assertEqual(rows[0]['actor'],'A');self.assertEqual(rows[0]['status'],'unsupported_native_instance_payload');self.assertIsNone(rows[0]['instance_count'])
    def test_external_level_identity(self):
        exports=[self.row('InstancedFoliageActor','F',-1),self.row('FoliageInstancedStaticMeshComponent','I',1)]
        self.assertEqual(self.scan(exports,False)[0]['status'],'unsupported_native_instance_payload')
        self.assertEqual(self.scan(exports,False,'/Game/Other')[0]['status'],'different_level')
    def test_cycle_template_and_unknown_scan(self):
        exports=[self.row('HierarchicalInstancedStaticMeshComponent','I',2),self.row('Actor','A',1),self.row('InstancedStaticMeshComponent','Template',0)]
        rows=self.scan(exports);self.assertEqual(summarize(rows,[{'error':'bad package'}])['status'],{'unverified_ownership':2});self.assertFalse(summarize(rows,[{}])['inventory_complete'])
