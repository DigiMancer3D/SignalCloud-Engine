# Mini-Boss — Worked PCP3 Mode Workflow

Create an elite hostile between a normal enemy and boss, with limited phases and a smaller encounter footprint.

Environment key: `mini_boss`

Recommended point budget: **500,000**

## Starter project

`examples/pcp3/tutorials/mini_boss_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Mini-Boss template and separate body, armor, and attack-anchor layers.
2. Use a compact rig and four-state Entity Runtime clips.
3. Reference it from a Raid or Encounter wave using one-level asset placement.
4. Use Streaming if the elite form exceeds its recommended point budget.

## Template layers

- **Body** — `enemy_body` — required.
- **Armor / Elite Form** — `enemy_body` — optional.
- **Bone Guides** — `bone` — optional.
- **Attack Anchors** — `trigger` — required.
- **Signal Effects** — `light` — optional.

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
