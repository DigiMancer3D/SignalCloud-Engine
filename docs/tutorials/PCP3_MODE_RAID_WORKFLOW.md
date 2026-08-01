# Raid — Worked PCP3 Mode Workflow

Assemble an arena, entry portal, boss slots, wave triggers, friendlies, completion conditions, and reward telemetry.

Environment key: `raid`

Recommended point budget: **6,000,000**

## Starter project

`examples/pcp3/tutorials/raid_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Raid template and build the arena shell before placements.
2. Add World portals/spawns and validate all referenced entity assets.
3. Author Encounter waves, boss phases, persistent friendlies, and reset policy.
4. Run the deterministic Encounter simulator, then stress-test the Full Map submission.

## Template layers

- **Arena Floor** — `floor` — required.
- **Arena Boundary** — `wall` — required.
- **Player Entry** — `portal` — required.
- **Boss Slots** — `trigger` — required.
- **Wave Triggers** — `trigger` — optional.
- **Arena Lighting** — `light` — optional.

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
