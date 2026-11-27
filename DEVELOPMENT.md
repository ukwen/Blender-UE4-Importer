# 0.10.0 development candidate — Blender 4.2

This is an unaccepted compatibility candidate on the development branch, not a release. Original master is preserved. Target Blender 4.2.4 LTS; no UE5 import support is claimed. UE5 legacy package headers are rejected before the UE4 layout is read.

Changes: optional engine discovery and explicit engine-dependency errors; cross-platform project paths; updated Principled sockets, group interfaces, blend settings and probe enums; guarded removed mesh smoothing property; material extraction subprocess uses argument list and timeout. Blender 4.2 masked materials use a documented dithered approximation, not exact clipping. Native texture extraction still requires a compatible UModel binary (UMODEL_PATH for Linux). Plugin mounts remain unsupported.

Acceptance commands (from repository root):

    python -m unittest discover -s tests -p "test_*.py" -v
    blender -b --factory-startup --python-exit-code 1 --python tests/blender_smoke.py

Blender runtime and genuine UE4 import regression tests must pass before acceptance. Compare mesh vertices/faces, UVs, material slots, actor transforms, and saved/reopened scenes against the original baseline. No distribution or installer until original licensing is resolved.

## 0.10.44-dev

See [Goblin character assembly](docs/0.10.44-goblin-assembly.md).

## 0.10.45-dev

See [Physics asset collision preview](docs/0.10.45-physics-preview.md).

## 0.10.46-dev

See [Native vehicle collision and automatic association](docs/0.10.46-vehicle-physics.md).

## 0.10.47-dev

See [Project batch workflow](docs/0.10.47-project-batch.md).

## 0.10.48-dev

See [Saved-scene import sessions and asset selection](docs/0.10.48-project-sessions.md).

## 0.10.49-dev

See [UE5 dependency inventory and Blueprint ancestry](docs/0.10.49-ue5-dependencies.md).

## 0.10.50-dev

See [UE5.0 cooked geometry acceptance](docs/0.10.50-ue5-cooked-geometry.md).

## 0.10.51-dev

See [Modern UE5 cooked geometry, material parameters and texture acceptance](docs/0.10.51-modern-ue5.md).

## 0.10.52-dev

See [UE5.6 native skeletal LOD acceptance](docs/0.10.52-ue5-skeletal-lods.md).

## 0.10.53-dev

See [Shared LODs and cooked material dependencies](docs/0.10.53-shared-lods-material-dependencies.md).

## 0.10.54-dev

See [UE5.7 editor dependency tables](docs/0.10.54-ue57-dependencies.md).

## 0.10.55-dev
See [UE5.6 editor source reconstruction](docs/0.10.55-ue56-editor.md).

## 0.10.56-dev

See [UE5.6 source textures and material graphs](docs/0.10.56-editor-materials.md).

## 0.10.57-dev

See [UE5.6 editor FK animation](docs/0.10.57-editor-animation.md).

## 0.10.58-dev

See [editor animation curves and expanded compatibility](docs/0.10.58-editor-animation-curves.md).

## 0.10.59-dev

See [full UE5.6 reference skeleton and authored animation previews](docs/0.10.59-editor-skeleton-preview.md).
