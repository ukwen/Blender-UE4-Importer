"""List exact missing mesh packages for supported saved UE5.6 placements; never substitute geometry."""
import argparse,json,sys
from collections import Counter,defaultdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from uasset import UProject
from ue5_editor_scene import placement_records
from ue5_editor_components import placements

def audit(descriptor):
    project=UProject(str(descriptor));content=Path(project.dir)/'Content';maps={};missing=defaultdict(Counter)
    for p in sorted(content.rglob('*.umap')):
        rel=p.relative_to(content).as_posix()
        try:
            data=placement_records(content,p);actors,skips=placements(content,p)
        except Exception as e:
            maps[rel]={'status':'unsupported','detail':str(e)};continue
        refs=Counter(r['package'] for r in data['records']);refs.update(c['package'] for a in actors for c in a['components'] if c['package']);unavailable={};statuses=Counter()
        for package,count in sorted(refs.items()):
            try:present=Path(project.resolve_package(package)).is_file()
            except (FileNotFoundError,ValueError):present=False
            status='present' if present else 'missing_engine' if package.startswith('/Engine/') else 'missing_game' if package.startswith('/Game/') else 'unsupported_mount'
            statuses[status]+=count
            if not present:unavailable[package]={'placements':count,'status':status};missing[package][rel]+=count
        maps[rel]={'status':'inspected','root_static_actors':len(data['records']),'blueprint_mesh_components':sum(bool(c['package']) for a in actors for c in a['components']),'placements':dict(statuses),'missing':unavailable,'skipped_root':data['skipped'],'skipped_components':skips}
    return {'scope':'Exact package file availability for supported serialized static mesh placements; presence does not certify decodability or runtime completeness','maps':maps,'missing_packages':{p:{'placements':sum(v.values()),'levels':dict(v)} for p,v in sorted(missing.items())}}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('project',type=Path);parser.add_argument('--report',type=Path,required=True);args=parser.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else None);args.report.write_text(json.dumps(audit(args.project),indent=2),encoding='utf-8')
