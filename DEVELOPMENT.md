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

## 0.10.60-dev

See [editor Blueprint components and sockets](docs/0.10.60-editor-components.md).

## 0.10.61-dev

See [editor texture regions and decoder portability](docs/0.10.61-editor-texture-regions.md).

## 0.10.62-dev

See [legacy UE5 editor source profiles](docs/0.10.62-legacy-editor.md).

## 0.10.63-dev

See [local material functions and saved construction components](docs/0.10.63-editor-functions-components.md).

## 0.10.64-dev

See [native UE5.6 lighting and scene markers](docs/0.10.64-editor-lighting.md).

## 0.10.65-dev

See [UE5.7 saved Blueprint composition](docs/0.10.65-ue57-blueprint.md).

## 0.10.66-dev

See [targeted missing mesh recovery](docs/0.10.66-missing-mesh-repair.md).

## 0.10.67-dev

See [legacy PNG material channel previews and grid validation](docs/0.10.67-grid-channel-preview.md).

## 0.10.68-dev

See [saved UE5.6 spring-arm camera rig previews](docs/0.10.68-camera-preview.md).

## 0.10.69-dev

See [procedural material coordinate and opacity previews](docs/0.10.69-procedural-preview.md).

## 0.10.70-dev

See [authored root translation and external pose validation](docs/0.10.70-root-translation.md).

## 0.10.71-dev

See [bounded unlit translucent surface previews](docs/0.10.71-unlit-translucency.md).

## 0.10.72-dev

See [saved masked character materials and source character integration](docs/0.10.72-masked-character.md).

## 0.10.73-dev

See [saved skeletal characters in native level reconstruction](docs/0.10.73-level-characters.md).

## 0.10.74-dev

See [one-operation saved level transfer](docs/0.10.74-full-scene.md).

## 0.10.75-dev

See [selected-level source dependency qualification](docs/0.10.75-scene-dependencies.md).

## 0.10.76-dev

See [native saved landscape heightfield reconstruction](docs/0.10.76-landscape.md).

## 0.10.77-dev

See [handoff](docs/HANDOFF.md), [roadmap](docs/ROADMAP.md), and [test report](docs/TEST_REPORT.md). Saved UE5 instance-component inventory reports unsupported payloads rather than treating component counts as decoded instances.

## 0.10.78-dev

See [saved decal projector placement](docs/0.10.78-decal-projectors.md).

## 0.10.79-dev

See [unified legacy commercial scene transfer](docs/0.10.79-legacy-full-scene.md). The one-click operation now also dispatches the bounded UE4 editor 508 profile, with original foliage and materials, light preview and explicit coverage.

## 0.10.80-dev

See [legacy 522 mixed-version Goblin full-scene acceptance](docs/0.10.80-goblin-full-scene.md). The single scene operation recognizes the bounded UE4 editor 522 profile and validates both legacy map table extents before import. Existing native decoders are reused.

## 0.10.81-dev

See [opt-in sky preview](docs/0.10.81-environment-preview.md). Separate saved-world previews never silently change the scene world.

## 0.10.82-dev

See [editor sampler fidelity](docs/0.10.82-sampler-fidelity.md). Explicit UV0, shared address helper and bounded direct tangent normal source-art preview; no runtime tangent/compression parity claim.

## 0.10.83-dev

See [instance fidelity](docs/0.10.83-instance-fidelity.md): preserve selected/shadowed instance overrides and unresolved bindings; unclamped scalar-factor RGB interpolation validated in actual Blender CPU render.

## 0.10.84-dev

See [fog and material semantics](docs/0.10.84-fog-and-material.md). Explicit base property flags, bounded RGB-factor Lerp and opt-in finite fog. Original map toggle/reopen and controlled CPU render verified; no engine parity claim.

## 0.10.85-dev

See [saved level sets and partition ownership](docs/0.10.85-level-sets.md). Atomic checked independent maps, partition ownership and explicit unsupported composition, material override guard and external actor path safety.

## 0.10.86-dev

[Native saved brush operands](docs/0.10.86-brush-operands.md): exact bounded inline UE5.6 Polys geometry, 53 original operands, explicit CSG roles and non-rendering collection. Compiled BSP and volume reconstruction remain outstanding.

## 0.10.87-dev

See [compiled BSP and volume bounds](docs/0.10.87-compiled-bsp.md). Original compiled render buffers (26 components) and 12 non-rendering volume guides; native BSP materials remain absent or unspecified in fixtures.

## 0.10.88-dev

See [landscape source atlas](docs/0.10.88-landscape-atlas.md). Original 64 embedded finest-mip textures, exact lossless RGBA, 4,064,256 derived corner UVs, component material ancestry and Heightmap bindings. Painted layers and missing material graphs are not reconstructed.

## 0.10.89-dev

[Workflow performance and source actions](docs/0.10.89-workflow.md). No persistent package cache, measured table reuse and original geometry digests.

## 0.10.90-dev

[Source recovery, cancellation and memory](docs/0.10.90-source-recovery.md). Explicit read-only recovery plan and non-overwriting verified copies, restored source geometry under original level collections, between-map transaction close rollback, adjustable package cache budget and measured process peak RSS.

## 0.10.91-dev

See [landscape memory and whole-project acceptance](docs/0.10.91-landscape-memory.md). Lower temporary allocation with exact old/candidate terrain digests; map redirector detection; six-world and three commercial-map regressions.

## 0.10.92-dev

Primary sidebar workflow, project-path and rescan guards, safe inter-map event interval, explicit filesystem confirmation warning. Linux Xvfb actual X11 clipboard and keyboard acceptance, two original maps, original package recovery in disposable copy. See [desktop workflow](docs/0.10.92-desktop-workflow.md).

## 0.10.93-dev

Selected-level, level-set, source-action and last-operation report navigation and copy. Original two-level Blender and X11 acceptance; see [report navigation](docs/0.10.93-report-navigation.md).

## 0.10.94-dev

Scoped recovery plan review and confirmation, ignored-file diagnostics, zero-ready and stale-plan refusal. Original recovery, overlay and actual X11 confirmation regression. See [recovery review](docs/0.10.94-recovery-review.md).

## 0.10.95-dev

Cooperative UE5.6 full-scene and checked-level reconstruction with safe in-map actor/component/material checkpoints; exact rollback, actual X11 Escape, source-backed material closure diagnostics including decal/terrain, original UE5.7 fixture audit, and platform-local installer acceptance launcher. See [stage cancellation and evidence audit](docs/0.10.95-stage-cancellation.md).

## 0.10.96-dev — independent component migration

Separate `feature/independent-importer` branch, preserving development 0.10.95. Remove three inherited files; generated shader groups, registration lifecycle, native editor texture boundary. See [provenance and remaining replacements](docs/INDEPENDENCE.md). Not a clean-room or commercial release claim.

## 0.10.97-dev — typed editor package table migration

See [independence](docs/INDEPENDENCE.md) and [tests](docs/TEST_REPORT.md). Modern UE5 and UE4 522 preflight use bounded typed records; remaining inherited parser and import integration are still pending.

## 0.10.98-dev — project paths and classic property records

Independent project resolution, Python-only saved level inventory, bounded classic UE4 property headers, typed animation routing. See docs/INDEPENDENCE.md and docs/TEST_REPORT.md.

## 0.10.99-dev — native skeletal and physics migration

UE4.27 editor skeletal, reference-skeleton and PhysicsAsset readers now use typed package records without inherited parser imports; all ten recovered original decoded records exactly match 0.10.98. See docs/TEST_REPORT.md and docs/INDEPENDENCE.md.

## 0.10.100-dev — classic static geometry migration

Typed UE4 object version 508 package tables, soft dependencies and static geometry boundary. See docs/INDEPENDENCE.md and docs/TEST_REPORT.md.

## 0.10.101-dev — classic actor and foliage reconstruction boundary

Typed actor placement and foliage source records, legacy-free supported geometry-only map import, original two-map parity and reopening. See docs/TEST_REPORT.md and docs/INDEPENDENCE.md.

## 0.10.102-dev — typed Blueprint defaults and body template migration

See docs/INDEPENDENCE.md and docs/TEST_REPORT.md. Supported UE4 522 Blueprint CDO/SCS and Character body templates are host independent. Integrated Western Frontier and Goblin regressions passed.

## 0.10.103 — complete removal target, independent classic scene path

New `classic_map_records.py`, `reference_identity.py`, `classic_texture.py`, `source_compression.py`, `mesh_description_blender.py` and `classic_material.py` migrate typed map-owned components, legacy 508 skeletal package boundary, classic texture package boundary and modern mesh-description construction. Existing native payload algorithms retained where applicable; their provenance remains subject to audit. Basic UE4 508 material graph reads supported surface outputs, constant/scalar/color and texture expressions from typed property records (MIT UAssetAPI MaterialInputProperties reference and original editor packages); explicit unsupported expression/field diagnostics and fallback remain. Alpha/transmission preview and runtime material fidelity are not equivalent to Unreal. No new source assets. Original Western payload parity: 31 skeletal records and 14 PNG/metadata records exactly match 0.10.102 (canonical report SHA256 9caa50ef83aac0ada52ef70eacb71c360b383a410b1fc973a4248fbda3a90fe4). Actual both-map integrated geometry+material+component test blocks all four inherited modules, including failed import attempts; 2814 mesh objects, 36 rigs, 462 foliage, 10 effective materials and five packed scene images with verified slot identities and save/reopen. Graph status remains graph_imported_unverified. Original mixed Goblin report exact and reopen; modern two-level 94 objects, reopen and rollback pass. Earlier 522 texture parity and unsupported earlier static/Blueprint/texture profiles still evidence-gated.

User's acceptance target is now complete removal of inherited implementation, not merely migration of individual paths. `python tools/audit_inherited_components.py --require-removed` fails until known inherited files and direct/literal production imports are absent; it is not a clean-room certificate or legal clearance. At 0.10.103 four core files remain (uasset.py, umesh.py, umat.py, umap.py), 30 import sites including their internal dependencies, original registration, legacy direct import operators, older profiles, material layers/advanced graphs and wind. Keep the working fallback until equivalent supported features pass. Audit retained algorithms and necessary third-party notices before commercial distribution. No commercial clearance.

## 0.10.104-dev — cold registration and UE4.27 static source

See docs/TEST_REPORT.md and docs/INDEPENDENCE.md. Four original compressed MeshDescription sources matched the prior mesh data exactly; independent direct import and material persistence verified. Legacy compatibility remains.
