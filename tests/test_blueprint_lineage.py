import unittest
from blueprint_lineage import resolve_lineage


def binding(package='',explicit=False,kind='SkeletalMeshComponent',template='Mesh0',origin='CDO'):
    return dict(package=package,explicit=explicit,**{'class':kind},template=template,origin=origin,fields={})


class LineageTest(unittest.TestCase):
    child=('/Game/Child','Child_C'); parent=('/Game/Parent','Parent_C')
    def make(self,child=None,parent=None):
        child=child if child is not None else binding()
        parent=parent if parent is not None else binding('/Game/ParentMesh',True)
        return {self.child:dict(status='inspected',parent_blueprint=self.parent[0],parent_class=self.parent[1],bindings={'Mesh':child}),
                self.parent:dict(status='inspected',parent_blueprint='/Script/Engine',parent_class='Character',bindings={'Mesh':parent,'UnprovenSCS':binding('/Game/Accessory',True,origin='SCS')})}
    def test_omitted_child_mesh(self):
        r=resolve_lineage(self.child,self.make().__getitem__)
        self.assertEqual(r['bindings']['Mesh']['package'],'/Game/ParentMesh')
        self.assertEqual(r['bindings']['Mesh']['mesh_declared_in'],self.parent[0])
        self.assertNotIn('UnprovenSCS',r['bindings'])
    def test_explicit_override(self):
        r=resolve_lineage(self.child,self.make(binding('/Game/ChildMesh',True)).__getitem__)
        self.assertEqual(r['bindings']['Mesh']['package'],'/Game/ChildMesh')
    def test_explicit_null(self):
        r=resolve_lineage(self.child,self.make(binding('',True)).__getitem__)
        self.assertEqual(r['bindings']['Mesh']['package'],'')
        self.assertTrue(r['bindings']['Mesh']['explicit'])
    def test_different_template_no_inheritance(self):
        r=resolve_lineage(self.child,self.make(binding(template='Other')).__getitem__)
        self.assertFalse(r['bindings']['Mesh']['explicit'])
    def test_missing_parent(self):
        d=self.make();d[self.parent]={'status':'missing','detail':'absent'}
        r=resolve_lineage(self.child,d.__getitem__)
        self.assertEqual(r['lineage_status'],'unresolved');self.assertFalse(r['bindings']['Mesh']['explicit'])
    def test_cycle(self):
        d=self.make();d[self.parent].update(parent_blueprint=self.child[0],parent_class=self.child[1]);r=resolve_lineage(self.child,d.__getitem__)
        self.assertEqual(r['lineage_status'],'unresolved');self.assertFalse(r['bindings']['Mesh']['explicit'])
    def test_kind_conflict(self):
        r=resolve_lineage(self.child,self.make(binding(kind='StaticMeshComponent')).__getitem__)
        self.assertNotIn('Mesh',r['bindings']);self.assertEqual(r['binding_conflicts'],['Mesh'])
