# Liquid Maker — Worked PCP3 Mode Workflow

Create liquid surface and volume geometry with flow guides, tint, opacity, waves, and bounded Streaming behavior.

Environment key: `liquid`

Recommended point budget: **1,200,000**

## Starter project

`examples/pcp3/tutorials/liquid_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Liquid template and separate water_surface from water_volume.
2. Add normalized Flow nodes for direction, strength, and viscosity.
3. Configure World Liquid visuals and keep physical force/damage disabled unless a later runtime approves them.
4. Validate maximum liquid points and test surface/volume motion in native preview.

## Template layers

- **Surface** — `water_surface` — required.
- **Volume** — `water_volume` — required.
- **Flow Guides** — `liquid_flow` — optional.
- **Boundary** — `wall` — optional.
- **Interaction Triggers** — `trigger` — optional.
- **Liquid Effects** — `light` — optional.

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
