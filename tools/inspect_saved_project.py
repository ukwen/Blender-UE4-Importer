"""Read-only saved-level inventory; requires Python, not Blender or Unreal."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from project_paths import ProjectPaths, discover_maps


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='Original .uproject descriptor')
    args = parser.parse_args()
    redirects = []
    try:
        descriptor, association, levels = discover_maps(args.project, redirects)
        project = ProjectPaths(descriptor)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(json.dumps({'project': descriptor, 'engine_association': association,
                      'engine_content_available': project.engine_dir is not None,
                      'levels': [{'name': name, 'path': path} for name, path in levels],
                      'excluded_redirectors': redirects}, indent=2))


if __name__ == '__main__':
    main()
