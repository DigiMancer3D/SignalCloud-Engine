# Room — Worked PCP3 Mode Workflow

Build a complete room shell with portals, lighting, objects, triggers, liquids, host-zone metadata, and streaming limits.

Environment key: `room`

Recommended point budget: **4,000,000**

## Starter project

`examples/pcp3/tutorials/room_starter.pcp3`

The starter contains the complete mode-template layer set but intentionally contains no finished geometry or enabled runtime behavior.

## Recommended workflow

1. Apply the Room template and use Room Shell for walls, floor, and ceiling.
2. Add portal frames and separate World portal records with destinations/spawns.
3. Add placements, liquids, themes, and guarded triggers; run the World reference audit.
4. Stress-test Full Map stability and Streaming LOD before accepting the room.

## Template layers

- **Walls** — `wall` — required.
- **Floor** — `floor` — required.
- **Ceiling** — `ceiling` — required.
- **Portals** — `portal` — required.
- **Lights** — `light` — optional.
- **Objects** — `generic` — optional.
- **Triggers** — `trigger` — optional.
- **Water Surface** — `water_surface` — optional.
- **Water Volume** — `water_volume` — optional.

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
