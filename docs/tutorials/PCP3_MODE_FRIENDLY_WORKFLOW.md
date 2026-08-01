# User Friendly — Worked PCP3 Mode Workflow

Build a friendly humanoid or helper with interaction anchors, movement clips, and persistent encounter placement.

Environment key: `friendly`

Recommended point budget: **180,000**

## Starter project

`examples/pcp3/tutorials/friendly_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the User Friendly template and keep the body semantic friendly_body.
2. Rig and weight the body, then create Idle/Move/Alert clips.
3. Add interaction anchors and use guarded triggers for reveal, alert, theme, or light effects.
4. Place the exported asset through Encounter Friendly or World Placement records.

## Template layers

- **Body** — `friendly_body` — required.
- **Bone Guides** — `bone` — optional.
- **Outfit / Accessories** — `friendly_body` — optional.
- **Interaction Anchor** — `trigger` — required.
- **Friendly Effects** — `light` — optional.

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
