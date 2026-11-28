# Unreal Project Importer — independent component migration

Internal development candidate **0.10.99-dev**, Blender 4.2.4. Direct saved Unreal project reconstruction in Blender without requiring FBX/USD conversion. This repository originated as a fork of [Waffle1434/Blender-UE4-Importer](https://github.com/Waffle1434/Blender-UE4-Importer). Original authorship is retained in the add-on metadata pending a complete rights and provenance audit. The candidate is not approved for commercial redistribution.

Active development takes place directly on `development`; independent component replacement and feature advancement are parallel engineering priorities. The former migration branch is a historical rollback checkpoint only. This candidate replaces the inherited registration helper and binary shader library and removes the bundled external texture executable. Native supported editor texture profiles are used; cooked textures retain their explicit-profile operator. This is not yet a complete independent implementation.

See [migration and provenance](docs/INDEPENDENCE.md), [handoff](docs/HANDOFF.md), [state](docs/PROJECT_STATE.json), [roadmap](docs/ROADMAP.md), [test report](docs/TEST_REPORT.md), and [dependencies](docs/DEPENDENCIES.md). Historical [development notes](DEVELOPMENT.md) document tested reconstruction profiles, not blanket support for any engine version. Missing assets and unsupported material or binary profiles remain explicit gaps. No third-party commercial fixture assets are distributed.

The Python-only inventory command `python tools/inspect_saved_project.py /path/to/Project.uproject` lists saved levels and excluded redirectors without launching Blender. It reports optional engine content availability, not rendering or complete dependency coverage.
