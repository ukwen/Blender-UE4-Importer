"""Original classic particle materials and bound smoke mesh; no inherited imports."""
import hashlib,importlib.abc,json,os,sys
from pathlib import Path
import bpy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
CORE={'uasset','umesh','umat','umap'};attempts=[]
class Block(importlib.abc.MetaPathFinder):
    def find_spec(self,fullname,path=None,target=None):
        if fullname.split('.')[-1] in CORE:
            attempts.append(fullname);raise ImportError('Inherited importer prohibited: '+fullname)
assert CORE.isdisjoint(sys.modules);sys.meta_path.insert(0,Block())
from asset_entrypoints import register,unregister
from material_stage import MaterialResolver,connected_surface
from project_paths import ProjectPaths
root=Path(os.environ['UE_WESTERN_PROJECT']);out=Path(os.environ['UE_PARTICLE_OUTPUT'])
bpy.ops.wm.read_factory_settings(use_empty=True);register()
records={}
for stem,preview in [('Mat_FX','unlit_translucent'),('Mat_Dust_FX','classic_lit_particle')]:
    path=next(root.rglob(stem+'.uasset'))
    for partial in (False,True):
        before=set(bpy.data.materials)
        assert getattr(bpy.ops,'import').umat(filepath=str(path),allow_partial=partial)=={'FINISHED'}
        m,=set(bpy.data.materials)-before
        status=m['UE_editor_material_status'];assert m.use_fake_user
        assert status==('partial' if partial else 'metadata_only'),status
        assert json.loads(m['UE_editor_graph'])['blend']=='BLEND_Translucent'
        issues=json.loads(m['UE_editor_material_issues']);assert any('no particle simulation' in v for v in issues),issues
        if partial:
            assert m['UE_surface_preview']==preview and connected_surface(m.node_tree)
            alpha=[n for n in m.node_tree.nodes if n.type=='VALUE' and '(preview alpha)' in n.label];assert len(alpha)==1
            alpha[0].outputs[0].default_value=.375
            surface=next(n for n in m.node_tree.nodes if n.type=='OUTPUT_MATERIAL').inputs['Surface'].links[0].from_node
            assert surface.type=='MIX_SHADER' and surface.inputs[0].is_linked
            if stem=='Mat_Dust_FX':
                tex=next(n for n in m.node_tree.nodes if n.type=='TEX_IMAGE');assert tex.image.packed_file
                assert any(l.from_socket==tex.outputs['Alpha'] for l in m.node_tree.links)
        else:
            assert 'UE_surface_preview' not in m
            assert not any(l.to_node.type=='BSDF_PRINCIPLED' for l in m.node_tree.links)
        records[m.name]=dict(status=status,partial=partial,preview=m.get('UE_surface_preview'),issues=issues)
# Actual production material-bearing mesh operator.
path=next(root.rglob('SM_Particle_Smoke_01.uasset'));before=set(bpy.data.objects)
assert getattr(bpy.ops,'import').umesh(filepath=str(path),materials=True)=={'FINISHED'}
obj,=set(bpy.data.objects)-before;mat=obj.data.materials[0]
assert mat['UE_material_status']=='partial_graph_unresolved' and mat['UE_surface_preview']=='unlit_translucent'
assert obj['UE_unresolved_material']
# Strict resolver rejects partials and doesn't leak preview graphs.
package=mat['UE_material_package'];strict=MaterialResolver(ProjectPaths(path));m=strict.resolve(package,'Particle')
assert m['UE_material_status']=='graph_failed' and m['UE_unresolved_material']
packed={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file};assert packed
bpy.ops.wm.save_as_mainfile(filepath=str(out));bpy.ops.wm.open_mainfile(filepath=str(out))
for nm,row in records.items():
    m=bpy.data.materials[nm];assert m['UE_editor_material_status']==row['status']
    if row['partial']:
        alpha=next(n for n in m.node_tree.nodes if n.type=='VALUE' and '(preview alpha)' in n.label)
        assert abs(alpha.outputs[0].default_value-.375)<1e-7
assert packed=={i.name:hashlib.sha256(i.packed_file.data).hexdigest() for i in bpy.data.images if i.packed_file}
assert not attempts and CORE.isdisjoint(sys.modules),(attempts,CORE.intersection(sys.modules))
unregister();out.with_suffix('.json').write_text(json.dumps(dict(materials=records,packed=packed,mesh='SM_Particle_Smoke_01',reopen=True,zero_inherited_imports=True),indent=2));print('CLASSIC_PARTICLE_PASS',flush=True)
