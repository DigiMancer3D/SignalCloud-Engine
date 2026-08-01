# +PCP+ examples

## Signal Orb

Open `signal_orb_demo.pcp3` from Point Cloud Paint++ and press **F5** for the native SignalCloud preview. The example is not automatically inserted into the game database. Use **Export to SignalCloud Database** after changing the asset ID, author form, and placement settings for your own test copy.

## Advanced Enemy

Open `advanced_enemy_demo.pcp3` to inspect the Branch 4 rig, timeline, event, and authoring-sidecar workflow. Use the Playback tab to inspect it without changing the source project.

## Guarded Interaction Demo

Open `guarded_interaction_demo.pcp3` to inspect the Branch 7 guarded interaction workflow. It contains a scanner reveal, an interaction-driven light pulse, and a delayed timer alert together with example factory and interaction sidecars.

Runtime behavior remains inactive unless the asset is exported with both **Runtime Factory** and **Guarded Interaction Runtime** explicitly enabled for the chosen Game or Stress target.

## Entity Runtime Demo

`entity_runtime_demo.pcp3` demonstrates Branch 8 guarded entity behavior: two-bone weighted deformation, four state clips, hover movement, and attack/effect anchors. It is Stress-enabled and Game-disabled by default.

## World Assembly Demo

`world_assembly_demo.pcp3` demonstrates Branch 9 room packaging, room bounds, one guarded portal marker, a default spawn point, semantic theme slots, and bounded water-wave/flow visuals. It is Stress-enabled and Game-disabled by default. The example portal intentionally has no destination so it remains evidence-only until linked to another exported room asset.
## Encounter Runtime Demo

`encounter_runtime_demo.pcp3` demonstrates Branch 10 guarded encounters: two bounded waves, one persistent friendly reference, three progress-based boss phases, zone-exit reset, and a combined proof/XAR/scrap telemetry hook. It is Stress-enabled and Game-disabled by default. Export compatible assets with IDs `entity_runtime_demo` and `signal_orb_demo` before expecting referenced geometry in the live database runtime.


## Branch 11 streaming example

`streaming_lod_demo.pcp3` is a 36K-point multi-semantic room configured for the `adaptive_8m` streaming profile. Open **Authoring → Streaming** to inspect its chunk audit, four distance LOD tiers, semantic reserve, point bounds, and dry-run/export sidecars.
