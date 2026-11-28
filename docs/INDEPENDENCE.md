# Independent-component migration (internal; commercial release prohibited pending rights review)

Reference baseline: development 0.10.95-dev, commit 8afb826f9a63f92a7e6c67d4cbfde7d820764de3, tree 954982b398cdbcf672cf7efea7d5c7ea485142a8. Preserve both development and master. Active migration branch: feature/independent-importer. Upstream Waffle1434 authorship retained. This is reimplementation with existing interface knowledge, not a certified clean-room process. No license grant for inherited code is established.

| Component | Migration result | Provenance / limitations |
|---|---|---|
| register_helper.py | Deleted; addon_lifecycle.py | Fresh class/menu registration via Blender Python API. No global driver namespace state. Integration callers still derived. |
| UE_nodes.blend | Deleted; generated_shader_groups.py | Fresh node construction from mathematical operations and required interface contracts, not extracted graphs. 22 groups, seven controlled CPU output evaluations. CameraVector, ScreenPosition, additive rendering explicitly approximate. Scalar math and vector/HLSL edge-case parity not established. CameraDepthFade now requires actual source function, no substitute. |
| umodel.exe | Deleted; native texture bridge | No automatic executable or implicit extracted cache. Existing validated editor reader, actual original T_UE_Logo_M success, missing source refusal, pack/reopen. Explicit-profile cooked operator remains; automatic cooked material texture fallback not yet replaced. Existing native readers have separate provenance reviews pending. |
| README.md | Replaced | New project description retains attribution. |
| uasset.py | Pending | Modified inherited parser; new bounded package reader must be built from permitted specifications and original fixtures. |
| umesh.py | Pending | Modified inherited geometry integration; replace after package interface. |
| umat.py | Pending | Modified inherited graph and material integration; generated groups and texture boundary now decoupled but legacy mapping and graph code remain. |
| umap.py | Pending | Modified inherited level import integration; replace after parser and mesh engine. |
| __init__.py and other historical files | Audit pending | No claim of complete inventory or ownership. |

Dependency audit still required: Blender GPL obligations, UAssetAPI MIT attribution and scope, pinned pyooz and BLAKE3 source/binary rights (not included in installer), fixture rights, any use of Epic specifications or source. Do not rebrand as independently owned or distribute the migration candidate until review. Existing generated graphs in old .blend files are not rewritten; fresh imports select marked generated groups rather than same-named foreign groups. Existing packed images or old materials are not relicensed.

## Next priority

Independent, bounded package reader and immutable typed scene records. Start with header/name/import/export tables and tagged values, compare against original source fixture values and preserve rejection behavior. Migrate callers incrementally. Retain the baseline for behavioral comparison without copying or translating its implementation. Review each new module's provenance and test evidence. Expand native cooked material texture decoding before declaring parity. Follow with mesh, material, scene integration, and whole-tree rights audit.
