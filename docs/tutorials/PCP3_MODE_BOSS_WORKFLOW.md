# Boss — Worked PCP3 Mode Workflow

Author a multi-phase hostile with a persistent core, phase geometry, attack anchors, encounter thresholds, and bounded LOD.

Environment key: `boss`

Recommended point budget: **1,500,000**

## Starter project

`examples/pcp3/tutorials/boss_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Boss template and separate the core from phase layers.
2. Create the rig and phase-specific clips before enabling Entity Runtime.
3. Use Encounter boss phases for progress thresholds and visual state changes.
4. Validate point budgets, references, phase order, and Streaming limits before export.

## Template layers

- **Core Body** — `enemy_body` — required. Persistent boss core.
- **Phase 1** — `enemy_body` — required. Initial visible phase.
- **Phase 2** — `enemy_body` — optional. Second-phase additions or replacement points.
- **Bone Guides** — `bone` — optional. Future large-scale rig anchors.
- **Attack Anchors** — `trigger` — required. Major attack and hazard origins.
- **Arena Effects** — `light` — optional. Phase lighting and environmental effects.

## Acceptance checklist

- [ ] Asset ID is unique and database-safe.
- [ ] Certificate creator and description are complete.
- [ ] Required semantic layers contain the intended geometry.
- [ ] Static validation has no errors.
- [ ] Runtime systems are enabled only when needed.
- [ ] Dry-run sidecars and references pass.
- [ ] Native Preview or stress testing confirms the result.

## Safety boundary

The starter has runtime execution disabled. Enable Factory, Interaction, Entity, World, Encounter, or Streaming only after the corresponding authoring records have been created and validated.
