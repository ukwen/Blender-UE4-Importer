# Unreal Project Importer — independent component migration

Internal development candidate **0.10.108-dev**, Blender 4.2.4. Direct saved Unreal project reconstruction in Blender without requiring FBX/USD conversion. This repository originated as a fork of [Waffle1434/Blender-UE4-Importer](https://github.com/Waffle1434/Blender-UE4-Importer). Original authorship is retained in the add-on metadata pending a complete rights and provenance audit. The candidate is not approved for commercial redistribution.

Active development takes place directly on `development`; independent component replacement and feature advancement are parallel engineering priorities. The former migration branch is a historical rollback checkpoint only. This candidate replaces the inherited registration helper and binary shader library and removes the bundled external texture executable. Native supported editor texture profiles are used; cooked textures retain their explicit-profile operator. This is not yet a complete independent implementation.

See [migration and provenance](docs/INDEPENDENCE.md), [handoff](docs/HANDOFF.md), [state](docs/PROJECT_STATE.json), [roadmap](docs/ROADMAP.md), [test report](docs/TEST_REPORT.md), and [dependencies](docs/DEPENDENCIES.md). Historical [development notes](DEVELOPMENT.md) document tested reconstruction profiles, not blanket support for any engine version. Missing assets and unsupported material or binary profiles remain explicit gaps. No third-party commercial fixture assets are distributed.

The Python-only inventory command `python tools/inspect_saved_project.py /path/to/Project.uproject` lists saved levels and excluded redirectors without launching Blender. It reports optional engine content availability, not rendering or complete dependency coverage.

Classic UE4 object-version 508 geometry-only maps now reconstruct supported static actors and foliage using typed records, without invoking the inherited importer modules. Other legacy profiles and optional material/skeletal-component extensions retain existing paths.

Supported UE4.27 Blueprint defaults and character body templates now use the typed package/property reader; the original mixed-version component integration and full Western Frontier skeletal/foliage regression pass.

Add-on registration and supported standalone mesh/material entry points no longer need the inherited modules at startup. UE4.27 single-source-LOD MeshDescription uses typed bounded records; older/advanced compatibility operations remain explicitly on demand. Directly imported supported basic materials are retained across save/reopen.

Supported modern standalone material instances and UE4.27 Goblin material graphs now use typed independent entry points. Three original 4K texture payloads and wind profiles match the prior reference. Unsupported graph and runtime wind semantics remain explicit gaps; partial material previews are opt-in.

Supported editor static file-menu imports use native geometry and material binding; explicit classic source LODs retain absent indices. Original multi-LOD evidence is still needed.

Classic Western particle materials use typed source graph records and editable, opt-in translucent previews; strict mode retains metadata without applying incomplete shaders. Supported 508/522/UE5.6 editor skeletal file-menu imports now construct native armatures and material bindings. Runtime particle simulation, complete layer graph replacement and older compatibility profiles remain unresolved.

Classic UE4.27 material layer topology and detached snapshots now have a bounded independent typed decoder, used by the compatibility graph bridge on the supported package profile. Controlled Blender composition and snapshot replay pass without inherited imports; actual original layer-stack packages and complete independent function graph translation remain unverified.
