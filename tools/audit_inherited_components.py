"""Fail-closed removal gate for known inherited files and production references.

This inventory is not copyright clearance, a clean-room certificate or a
substitute for human provenance review of retained algorithms and dependencies.
"""
import argparse
import ast
import json
from pathlib import Path

CORE = {'uasset', 'umesh', 'umat', 'umap', 'register_helper'}
FILES = {x+'.py' for x in CORE} | {'UE_nodes.blend', 'umodel.exe'}


def audit(root):
    root = Path(root)
    present = sorted(p for p in FILES if (root/p).exists())
    refs = []
    branding = []
    for path in sorted(root.glob('*.py')):
        source = path.read_text(encoding='utf-8')
        tree = ast.parse(source, filename=str(path))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ''] if node.module else [a.name for a in node.names]
            elif isinstance(node, ast.Call) and node.args:
                fn = node.func
                dynamic = (isinstance(fn, ast.Name) and fn.id == '__import__' or
                           isinstance(fn, ast.Attribute) and fn.attr == 'import_module')
                if dynamic and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                    names = [node.args[0].value]
            matches = sorted({part for name in names for part in name.split('.') if part in CORE})
            if matches:
                refs.append({'file': path.name, 'line': node.lineno, 'modules': matches})
            if isinstance(node, ast.Constant) and isinstance(node.value, str) and 'waffle1434' in node.value.casefold():
                branding.append({'file': path.name, 'line': node.lineno})
    return {'remaining_files': present, 'references': sorted(refs,key=lambda x:(x['file'],x['line'])),
            'upstream_name_locations': branding,
            'known_removal_gate_passed': not present and not refs,
            'commercial_clearance': False,
            'scope': 'Root production files and literal import references only; full provenance and notices require separate review.'}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    p.add_argument('--require-removed', action='store_true')
    args = p.parse_args(); result = audit(args.root); print(json.dumps(result,indent=2))
    raise SystemExit(1 if args.require_removed and not result['known_removal_gate_passed'] else 0)
