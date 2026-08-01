# Enemy — Worked PCP3 Mode Workflow

Build a formed or formless hostile, then connect its rig, state clips, guarded entity runtime, and optional encounter placement.

Environment key: `enemy`

Recommended point budget: **120,000**

## Starter project

`examples/pcp3/tutorials/enemy_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Enemy mode template and keep Body as enemy_body.
2. Add root/limb bones and paint named bone-weight channels where deformation is needed.
3. Create Idle, Move, Alert, and Attack clips; keep attack events telemetry-only until approved.
4. Configure Entity Runtime, test in Playback, then export with Streaming enabled for large forms.

## Template layers

- **Body** — `enemy_body` — required. Primary visible hostile form.
- **Bone Guides** — `bone` — optional. Future skeletal and deformation anchors.
- **Attack Anchors** — `trigger` — optional. Attack origins, cones, and effect anchors.
- **Signal Effects** — `light` — optional. Glow, trails, and alert-state points.

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
