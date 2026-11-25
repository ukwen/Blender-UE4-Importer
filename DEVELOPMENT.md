# 0.10.0 development candidate — Blender 4.2

This is an unaccepted compatibility candidate on the development branch, not a release. Original master is preserved. Target Blender 4.2.4 LTS; no UE5 import support is claimed. UE5 legacy package headers are rejected before the UE4 layout is read.

Changes: optional engine discovery and explicit engine-dependency errors; cross-platform project paths; updated Principled sockets, group interfaces, blend settings and probe enums; guarded removed mesh smoothing property; material extraction subprocess uses argument list and timeout. Blender 4.2 masked materials use a documented dithered approximation, not exact clipping. Native texture extraction still requires a compatible UModel binary (UMODEL_PATH for Linux). Plugin mounts remain unsupported.

Acceptance commands (from repository root):

    python -m unittest discover -s tests -p "test_*.py" -v
    blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py

Blender runtime and genuine UE4 import regression tests must pass before acceptance. Compare mesh vertices/faces, UVs, material slots, actor transforms, and saved/reopened scenes against the original baseline. No distribution or installer until original licensing is resolved.
