# Acceptance report — 0.10.81-dev

Verified: recovered 0.10.80 source archive SHA-256 4a71a5146fdf14914e886ceee457b46db7cebfcb2b85ee328c770b75eed136c6 and exact Git tree 9fa5e453c829dc5abe47c9bf6110abd60c65a64e. Four immutable dependency hashes matched. Reused existing runtime and decoder. Baseline 99 tests: 76 passed, 23 fixture skips; current 103: 80 passed, 23 skips, zero failures. Actual Blender sky test, CPU Cycles sky-only render and two-level UE5 scene regression including late rollback, duplicate refusal and reopen passed. See 0.10.81-environment-preview.md.

Previously verified, not rerun: Western Frontier, Goblin, terrain, decal and animation acceptance. Blocked or unverified: native UE5 instance evidence, missing original geometry/materials, fog rendering, captured sky, legacy sky, EEVEE, Windows and Unreal runtime equivalence.

Isolated candidate installation passed three native SM_Door imports and three reuse checks after reopening; runtime code identical to final source, documentation finalized afterward.
