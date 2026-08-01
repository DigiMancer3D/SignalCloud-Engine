# Environment Theme — Worked PCP3 Mode Workflow

Create a reusable semantic palette and room-part set for walls, floors, ceilings, portals, lights, and props.

Environment key: `environment_theme`

Recommended point budget: **2,000,000**

## Starter project

`examples/pcp3/tutorials/environment_theme_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Theme template and build representative architecture parts.
2. Create Flow/Theme slots mapping semantics to colors, brushes, and guided presets.
3. Reference the theme from World Assembly rooms and audit missing theme assets.
4. Confirm theme preview never rewrites source point colors.

## Template layers

- **Walls** — `wall` — required.
- **Floors** — `floor` — required.
- **Ceilings** — `ceiling` — required.
- **Doors / Windows** — `portal` — optional.
- **Lights** — `light` — optional.
- **Theme Props** — `generic` — optional.

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
