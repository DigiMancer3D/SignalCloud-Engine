# Environment Object — Worked PCP3 Mode Workflow

Create a prop, pickup, weapon, sign, light, proof, or usable object with optional collision guides and interaction anchors.

Environment key: `environment_object`

Recommended point budget: **250,000**

## Starter project

`examples/pcp3/tutorials/environment_object_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Environment Object template and give the asset a unique database-safe ID.
2. Paint geometry on the semantic layer that best describes runtime priority.
3. Add an authored Gameplay trigger; a trigger-semantic point layer alone is not an executable trigger.
4. Enable only the Factory/Interaction systems needed, validate, and export.

## Template layers

- **Geometry** — `generic` — required.
- **Collision Guide** — `wall` — optional.
- **Interaction Anchor** — `trigger` — optional.
- **Light / Effect** — `light` — optional.

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
