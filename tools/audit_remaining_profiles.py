"""Read-only evidence inventory of original library packages; does not infer native support."""
import argparse,json,sys
from collections import Counter
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from ue5_full_scene import actor_inventory
from ue5_instance_inventory import summarize
from ue5_level_layout import inventory
from ue5_editor_decals import records as decals
from package_inspector import inspect_package


def audit(project,fixtures):
    content=project.parent/'Content';levels=[]
    for p in sorted(content.rglob('*.umap')):
        components=[]
        try:
            actors,errors=actor_inventory(content,p,components);layout=inventory(content,p);d=decals(content,p)
            levels.append(dict(source=p.relative_to(content).as_posix(),serialized_actors=len(actors),instances=summarize(components,errors),composition_candidates=layout['composition_candidates'],partition=layout['partition'],decals=len(d['records']),decal_material_status=dict(Counter(r['material_status'] for r in d['records'])),missing_decal_materials=sorted({r['material_package'] for r in d['records'] if r['material_status']=='missing'})))
        except (ValueError,OSError) as exc:levels.append(dict(source=p.relative_to(content).as_posix(),unsupported=str(exc)))
    profiles=[]
    for root in (fixtures/'TestEditorUE5_7',fixtures/'TestUE5_7'):
        for p in sorted(root.rglob('*')):
            if p.suffix.lower() not in ('.uasset','.umap'):continue
            try:
                m=inspect_package(p);profiles.append(dict(source=p.relative_to(fixtures).as_posix(),ue5=m.get('ue5'),ue4=m.get('ue4'),status=m.get('status'),sidecars=m.get('sidecars'),flags=m.get('flags')))
            except Exception as exc:profiles.append(dict(source=p.relative_to(fixtures).as_posix(),error=str(exc)))
    return dict(levels=levels,ue57_profiles=profiles,scope='Original saved packages only. Does not infer missing materials, native instance counts, streaming, or render fidelity.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('project',type=Path);parser.add_argument('fixtures',type=Path);parser.add_argument('output',type=Path);a=parser.parse_args();a.output.write_text(json.dumps(audit(a.project.resolve(),a.fixtures.resolve()),indent=2));print('PROFILE_AUDIT',a.output)
