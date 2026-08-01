from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
import re

HELP_SCHEMA = "pcp3_authoring_help_v1"


@dataclass(frozen=True)
class HelpTopic:
    key: str
    title: str
    category: str
    summary: str
    body: str
    keywords: tuple[str, ...] = ()
    main_tab: str = ""
    authoring_tab: str = ""
    tool_key: str = ""
    mode_key: str = ""
    example: str = ""
    document: str = ""
    checklist: tuple[str, ...] = ()
    blocked_reason: str = ""

    def searchable_text(self) -> str:
        return " ".join(
            (
                self.key,
                self.title,
                self.category,
                self.summary,
                self.body,
                " ".join(self.keywords),
                " ".join(self.checklist),
                self.main_tab,
                self.authoring_tab,
                self.tool_key,
                self.mode_key,
                self.blocked_reason,
            )
        ).casefold()


@dataclass(frozen=True)
class HelpContext:
    main_tab: str = ""
    authoring_tab: str = ""
    tool_key: str = ""
    mode_key: str = ""


MODE_WORKFLOWS: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "enemy": (
        "Enemy",
        "Build a formed or formless hostile, then connect its rig, state clips, guarded entity runtime, and optional encounter placement.",
        (
            "Apply the Enemy mode template and keep Body as enemy_body.",
            "Add root/limb bones and paint named bone-weight channels where deformation is needed.",
            "Create Idle, Move, Alert, and Attack clips; keep attack events telemetry-only until approved.",
            "Configure Entity Runtime, test in Playback, then export with Streaming enabled for large forms.",
        ),
    ),
    "boss": (
        "Boss",
        "Author a multi-phase hostile with a persistent core, phase geometry, attack anchors, encounter thresholds, and bounded LOD.",
        (
            "Apply the Boss template and separate the core from phase layers.",
            "Create the rig and phase-specific clips before enabling Entity Runtime.",
            "Use Encounter boss phases for progress thresholds and visual state changes.",
            "Validate point budgets, references, phase order, and Streaming limits before export.",
        ),
    ),
    "mini_boss": (
        "Mini-Boss",
        "Create an elite hostile between a normal enemy and boss, with limited phases and a smaller encounter footprint.",
        (
            "Apply the Mini-Boss template and separate body, armor, and attack-anchor layers.",
            "Use a compact rig and four-state Entity Runtime clips.",
            "Reference it from a Raid or Encounter wave using one-level asset placement.",
            "Use Streaming if the elite form exceeds its recommended point budget.",
        ),
    ),
    "raid": (
        "Raid",
        "Assemble an arena, entry portal, boss slots, wave triggers, friendlies, completion conditions, and reward telemetry.",
        (
            "Apply the Raid template and build the arena shell before placements.",
            "Add World portals/spawns and validate all referenced entity assets.",
            "Author Encounter waves, boss phases, persistent friendlies, and reset policy.",
            "Run the deterministic Encounter simulator, then stress-test the Full Map submission.",
        ),
    ),
    "friendly": (
        "User Friendly",
        "Build a friendly humanoid or helper with interaction anchors, movement clips, and persistent encounter placement.",
        (
            "Apply the User Friendly template and keep the body semantic friendly_body.",
            "Rig and weight the body, then create Idle/Move/Alert clips.",
            "Add interaction anchors and use guarded triggers for reveal, alert, theme, or light effects.",
            "Place the exported asset through Encounter Friendly or World Placement records.",
        ),
    ),
    "environment_object": (
        "Environment Object",
        "Create a prop, pickup, weapon, sign, light, proof, or usable object with optional collision guides and interaction anchors.",
        (
            "Apply the Environment Object template and give the asset a unique database-safe ID.",
            "Paint geometry on the semantic layer that best describes runtime priority.",
            "Add an authored Gameplay trigger; a trigger-semantic point layer alone is not an executable trigger.",
            "Enable only the Factory/Interaction systems needed, validate, and export.",
        ),
    ),
    "environment_theme": (
        "Environment Theme",
        "Create a reusable semantic palette and room-part set for walls, floors, ceilings, portals, lights, and props.",
        (
            "Apply the Theme template and build representative architecture parts.",
            "Create Flow/Theme slots mapping semantics to colors, brushes, and guided presets.",
            "Reference the theme from World Assembly rooms and audit missing theme assets.",
            "Confirm theme preview never rewrites source point colors.",
        ),
    ),
    "room": (
        "Room",
        "Build a complete room shell with portals, lighting, objects, triggers, liquids, host-zone metadata, and streaming limits.",
        (
            "Apply the Room template and use Room Shell for walls, floor, and ceiling.",
            "Add portal frames and separate World portal records with destinations/spawns.",
            "Add placements, liquids, themes, and guarded triggers; run the World reference audit.",
            "Stress-test Full Map stability and Streaming LOD before accepting the room.",
        ),
    ),
    "liquid": (
        "Liquid Maker",
        "Create liquid surface and volume geometry with flow guides, tint, opacity, waves, and bounded Streaming behavior.",
        (
            "Apply the Liquid template and separate water_surface from water_volume.",
            "Add normalized Flow nodes for direction, strength, and viscosity.",
            "Configure World Liquid visuals and keep physical force/damage disabled unless a later runtime approves them.",
            "Validate maximum liquid points and test surface/volume motion in native preview.",
        ),
    ),
}


def _topic(
    key: str,
    title: str,
    category: str,
    summary: str,
    body: str,
    *,
    keywords: Iterable[str] = (),
    main_tab: str = "",
    authoring_tab: str = "",
    tool_key: str = "",
    mode_key: str = "",
    example: str = "",
    document: str = "",
    checklist: Iterable[str] = (),
    blocked_reason: str = "",
) -> HelpTopic:
    return HelpTopic(
        key=key,
        title=title,
        category=category,
        summary=summary,
        body=body.strip(),
        keywords=tuple(keywords),
        main_tab=main_tab,
        authoring_tab=authoring_tab,
        tool_key=tool_key,
        mode_key=mode_key,
        example=example,
        document=document,
        checklist=tuple(checklist),
        blocked_reason=blocked_reason,
    )


def build_topics() -> tuple[HelpTopic, ...]:
    topics: list[HelpTopic] = [
        _topic(
            "quick_start",
            "Quick Start — Recommended Authoring Order",
            "Start Here",
            "A safe order for creating, previewing, validating, and exporting a PCP3 asset.",
            """
1. Choose the correct Environment type and press Template.
2. Name the asset, set a database-safe Asset ID, and complete Certificate authorship.
3. Build geometry on clearly named semantic layers.
4. Validate the static asset before authoring runtime behavior.
5. Add Rig, Timeline, Gameplay, Placement, Flow/Theme, or later runtime records only when the asset needs them.
6. Use Runtime Playback for non-destructive inspection.
7. Enable Factory, Interaction, Entity, World, Encounter, and Streaming explicitly; disabled systems remain inert.
8. Compile dry-run sidecars and resolve errors or missing references.
9. Export the asset and test in Native Preview or the engine-native stress tester.
10. Preserve the accepted source sibling before moving to another phase or repair.
""",
            keywords=("begin", "workflow", "order", "first asset", "tutorial"),
            main_tab="Mode",
            document="docs/PCP3_AUTHORING_HELP_GUIDE.md",
            checklist=(
                "Template applied",
                "Unique Asset ID",
                "Certificate creator filled",
                "Static validation passed",
                "Only required runtimes enabled",
                "Dry-run sidecars passed",
                "Native/stress test completed",
            ),
        ),
        _topic(
            "sidebar_navigation",
            "Responsive Sidebar and Shared Scrolling",
            "Interface",
            "Use Template/Validate/Studio, X/Y active-page scrolling, and Sub-Tab scrolling without losing tab content.",
            """
The sidebar action header contains Template, Validate, and Studio. The shared scrollbar controls the active page when Sub-Tab is off. X moves wide page content and Y moves tall page content. Enable Sub-Tab to lock the same scrollbar onto the wrapped Authoring tab rows. The main sidebar tabs and action header remain visible while content scrolls.

At the normal resting sidebar width, full labels are preferred. The selected main and Authoring tabs, axis, and Sub-Tab state are remembered in config/pcp3_workspace.json.
""",
            keywords=("tabs", "scroll", "sub-tab", "sidebar", "template", "studio", "overflow"),
            main_tab="Layers",
            document="docs/PCP3_BRANCH10_R1_RESPONSIVE_SIDEBAR_NAVIGATION.md",
        ),
        _topic(
            "viewport_workflow",
            "Views, Depth, Rotation and Window Sync",
            "Core Editing",
            "Understand Single, 3-Square, 4-Square, perspective, per-pane depth, NP pan, and buffered Window Sync.",
            """
Use orthographic panes to place points accurately and Perspective 3D to verify form. Each pane keeps independent pan, zoom, angle, and depth. Active pane depth controls the hidden coordinate for 2D placement. Window Sync is a buffered one-shot alignment tool: select the source and targets, wait for the 1.3-second application, then return to another tool. It is not a permanent feedback loop.
""",
            keywords=("projection", "depth", "front", "top", "side", "perspective", "window sync", "NP pan"),
            main_tab="Depth",
            document="docs/PCP3_BRANCH2_R3_VIEWPORT_STUDIO.md",
        ),
        _topic(
            "editing_tools",
            "Selection, Pencil, Brush, Eraser, Recolor, Lines and Rotation",
            "Core Editing",
            "Choose the correct editing tool and understand what changes geometry versus only view state.",
            """
Select Region chooses points or a 3D region. Point Pencil lays a continuous path. 3D Brush stamps the active brush database entry. Eraser removes points, Recolor changes RGBA, and Attribute Picker copies point attributes into the active controls. Line/Curve creates deterministic paths. Rotate and Roll change selection geometry when points are selected; view-angle controls change only the camera. Save before large destructive edits and use Undo/Redo immediately when the result is not expected.
""",
            keywords=("select", "pencil", "brush", "eraser", "recolor", "picker", "line", "curve", "rotate", "roll"),
            tool_key="brush",
            document="docs/PCP3_TOOLS_HELP.md",
        ),
        _topic(
            "guided_shapes",
            "Guided Shapes, Architecture Presets and Room Shell",
            "Core Editing",
            "Generate bounded geometry with live region previews and correct semantic layers.",
            """
Guided Shapes use a selected region and a parameter dialog. The cyan preview is temporary. Walls, floors, ceilings, fixtures, and opening frames automatically assign recommended semantics and metadata. An opening frame leaves its center unfilled but does not subtract a boolean hole from an existing wall. Room Shell interprets Top as a footprint and Front/Side as wall-face selections, then generates separate Walls, Floor, and Ceiling layers.
""",
            keywords=("box", "sphere", "cylinder", "wall", "floor", "ceiling", "fixture", "opening", "room shell"),
            main_tab="Layers",
            document="docs/PCP3_BRANCH3_R1_ARCHITECTURE_PRESETS.md",
        ),
        _topic(
            "layers_colors_brushes",
            "Layers, Custom Colors and the 3D Brush Editor",
            "Core Editing",
            "Organize semantics, preserve colors, and author layered 3D brushes including named bone weights.",
            """
Layers control visibility, locking, opacity, grouping, and semantics. Runtime priority depends on semantics, not only the layer name. Custom Colors retains the newest 24 colors in user_data/pcp3/custom_colors.json. The 3D Brush Editor stores geometry and advanced channels such as bone_weight, flow_strength, trigger_mask, light_intensity, and density. Bone-weight brushes preserve a named bone target and stable channel number.
""",
            keywords=("layer", "semantic", "color", "palette", "brush database", "bone weight"),
            main_tab="Layers",
            document="docs/PCP3_BRANCH8_ENTITY_BEHAVIOR_ANIMATION_RUNTIME.md",
        ),
        _topic(
            "certificate_export",
            "Certificate, Validation, Export and Sidecars",
            "Files and Export",
            "Prepare provenance, validate the asset, and understand which files belong to one exported PCP3 asset.",
            """
The .pcp3 project describes the document and points to a sealed .pcp3cloud file. The .pcpcert.json certificate records authorship and proof-chain checksums. Validation creates a .pcp3validation.json sidecar. Advanced systems add authoring, runtime, factory, interaction, entity, world, encounter, and streaming sidecars only when applicable. Keep files with the same asset stem together. Do not rename only one file after export.
""",
            keywords=("certificate", "proof", "checksum", "sidecar", "export", "database", "udata"),
            main_tab="Certificate",
            document="docs/PCP3_FORMAT_V0.md",
            checklist=("Creator name", "Unique Asset ID", "No validation errors", "References resolved", "Export files share one stem"),
        ),
        _topic(
            "rig",
            "Rig Bones, Anchors and Bone Guides",
            "Advanced Authoring",
            "Build a parent-child bone hierarchy and named anchors for animation, attacks, effects, cameras, interactions, and spawns.",
            """
Create bones with unique names, a parent, and world-space start/end positions. Avoid zero-length bones and parent cycles. Generate Bone Guide points for visible inspection. Anchors are named positions with roles such as attack, effect, interaction, camera, and spawn. Entity Runtime reads up to 64 bones and follows parent chains.
""",
            keywords=("bone", "rig", "anchor", "parent", "cycle", "guide"),
            main_tab="Authoring",
            authoring_tab="Rig",
            example="examples/pcp3/entity_runtime_demo.pcp3",
            document="docs/PCP3_BRANCH4_ADVANCED_AUTHORING_STUDIO.md",
        ),
        _topic(
            "timeline",
            "Timeline Clips, Keyframes and Events",
            "Advanced Authoring",
            "Create deterministic clips for root and bone transforms and inspect event timing safely.",
            """
A clip stores duration, FPS, loop state, keyframes, and timed events. Keyframes can target root or named bones and contain position, rotation, scale, and interpolation. Runtime Playback interpolates the selected clip without changing source geometry. Events appear in telemetry; script, damage, economy, and unrestricted AI actions remain blocked unless an approved later service explicitly handles them.
""",
            keywords=("clip", "keyframe", "animation", "event", "interpolation", "scrubber"),
            main_tab="Authoring",
            authoring_tab="Timeline",
            example="examples/pcp3/advanced_enemy_demo.pcp3",
            document="docs/PCP3_BRANCH4_ADVANCED_AUTHORING_STUDIO.md",
        ),
        _topic(
            "gameplay_triggers",
            "Gameplay Triggers",
            "Advanced Authoring",
            "Create executable trigger records rather than relying on trigger-semantic geometry alone.",
            """
A layer or point with semantic trigger is visual/attribute data. Executable behavior requires a Gameplay trigger record with type, position, radius, action, target, delay, repeat, cooldown, and optional conditions. Approved trigger types include proximity, scanner, threshold, timer, and interaction. Validate the action against Guarded Interaction before export.
""",
            keywords=("trigger", "scanner", "proximity", "timer", "interaction", "threshold", "cooldown"),
            main_tab="Authoring",
            authoring_tab="Gameplay",
            example="examples/pcp3/guarded_interaction_demo.pcp3",
            document="docs/PCP3_BRANCH7_R1_INTERACTION_AUTHORING_REPAIR.md",
        ),
        _topic(
            "placements_waves",
            "Placements and Raid-Wave Authoring",
            "Advanced Authoring",
            "Reference exported assets by ID without duplicating their point geometry in the source project.",
            """
Placements store an asset ID, kind, transform, group, and enabled state. Runtime loading is bounded to one reference level. Raid-wave records store wave order, asset IDs, counts, delay, lifetime, spread, and future attributes. Missing references remain warnings and never become arbitrary file paths.
""",
            keywords=("placement", "asset id", "wave", "raid", "reference", "spawn"),
            main_tab="Authoring",
            authoring_tab="Placement",
            example="examples/pcp3/encounter_runtime_demo.pcp3",
            document="docs/PCP3_BRANCH10_ENCOUNTER_RAID_BOSS_FRIENDLY_RUNTIME.md",
        ),
        _topic(
            "flow_theme",
            "Flow Fields and Theme Slots",
            "Advanced Authoring",
            "Author normalized directional fields and semantic color/brush/preset mappings.",
            """
Flow nodes store position, normalized direction, strength, and viscosity. They currently provide visual/runtime evidence and liquid motion intent rather than unrestricted force. Theme slots map a semantic to a color, 3D brush, guided preset, and future attributes. Theme preview and runtime application do not rewrite source colors.
""",
            keywords=("flow", "liquid", "wind", "theme", "semantic color", "viscosity"),
            main_tab="Authoring",
            authoring_tab="Flow/Theme",
            example="examples/pcp3/world_assembly_demo.pcp3",
            document="docs/PCP3_BRANCH9_WORLD_ASSEMBLY_PORTAL_LIQUID_RUNTIME.md",
        ),
        _topic(
            "playback",
            "Runtime Playback Lab",
            "Runtime",
            "Scrub and play authored clips with temporary overlays before enabling a live runtime factory.",
            """
Playback is non-destructive. Select a clip, speed, loop state, geometry budget, and overlay toggles. The native preview can show transformed geometry, rig bones, anchors, triggers, placements, flow, raid markers, themes, and event markers. Bake Snapshot Copy writes a disabled preview project under user_data/pcp3/runtime_snapshots.
""",
            keywords=("play", "pause", "scrub", "native runtime preview", "snapshot", "overlay"),
            main_tab="Authoring",
            authoring_tab="Playback",
            example="examples/pcp3/advanced_enemy_demo.pcp3",
            document="docs/PCP3_BRANCH5_RUNTIME_PREVIEW_PLAYBACK.md",
        ),
        _topic(
            "factory",
            "Runtime Factory Bridge",
            "Runtime",
            "Compile approved authoring data into guarded Game/Stress sidecars.",
            """
Runtime Factory must be enabled explicitly and given Game and/or Stress targets. It can compile root motion, scanner/proximity visibility gates, one-level real PCP3 placements, trigger/flow evidence, and semantic themes. Nested point limits, missing references, and unsupported event actions are validated. Use Compile Dry Run before database export.
""",
            keywords=("factory", "compile", "dry run", "scanner gate", "nested points"),
            main_tab="Authoring",
            authoring_tab="Factory",
            example="examples/pcp3/advanced_enemy_demo.pcp3",
            document="docs/PCP3_BRANCH6_RUNTIME_FACTORY_BRIDGE.md",
        ),
        _topic(
            "interaction",
            "Guarded Interaction Runtime",
            "Runtime",
            "Execute only bounded reversible actions through delay, repeat, cooldown, and reset policies.",
            """
Both Runtime Factory and Interaction must be enabled. Approved actions are show, hide, reveal, alert, spawn_proxy, set_theme, and pulse_light. State, event-ledger, and proxy pools are capped. Zone Exit is the recommended reset policy. Unsafe actions are retained as telemetry-only and never modify health, saves, inventory, or economy.
""",
            keywords=("show", "hide", "reveal", "alert", "proxy", "pulse light", "cooldown", "reset"),
            main_tab="Authoring",
            authoring_tab="Interaction",
            example="examples/pcp3/guarded_interaction_demo.pcp3",
            document="docs/PCP3_BRANCH7_GUARDED_INTERACTION_RUNTIME.md",
        ),
        _topic(
            "entity",
            "Entity Behavior and Animation Runtime",
            "Runtime",
            "Configure four visual states, movement profiles, rig deformation, state clips, and anchor evidence.",
            """
Supported entity assets are Enemy, Boss, Mini-Boss, and User Friendly. Distance selects Idle, Move, Alert, or Attack. Safe movement profiles include stationary, hover, patrol_line, face_viewer, approach_viewer, and friendly_follow. One named bone channel per point is supported; multi-bone skin blending, damage, physics ragdolls, and unrestricted AI remain deferred.
""",
            keywords=("entity", "idle", "move", "alert", "attack", "hover", "patrol", "bone deformation"),
            main_tab="Authoring",
            authoring_tab="Entity",
            example="examples/pcp3/entity_runtime_demo.pcp3",
            document="docs/PCP3_BRANCH8_ENTITY_BEHAVIOR_ANIMATION_RUNTIME.md",
        ),
        _topic(
            "world",
            "World Assembly, Portals, Themes and Liquids",
            "Runtime",
            "Host a PCP3 room in a SignalCloud zone and connect guarded portals, placements, themes, and liquid visuals.",
            """
World Assembly stores World/Room IDs, host zone, safe-room intent, level, theme, portals, placements, and liquids. A guarded portal requires a valid destination asset and destination portal or default spawn. Visual point clouds do not generate collision/navigation geometry. Missing links stay inactive and visible as diagnostics.
""",
            keywords=("world", "room", "portal", "spawn", "host zone", "liquid", "reference audit"),
            main_tab="Authoring",
            authoring_tab="World",
            example="examples/pcp3/world_assembly_demo.pcp3",
            document="docs/PCP3_BRANCH9_WORLD_ASSEMBLY_PORTAL_LIQUID_RUNTIME.md",
        ),
        _topic(
            "encounter",
            "Encounter, Raid, Boss and Friendly Runtime",
            "Runtime",
            "Schedule bounded sequential waves, persistent friendlies, boss phases, completion, reset, and reward telemetry.",
            """
Start conditions include world_enter, proximity, scanner, interaction, timer, and manual. Encounter limits cap waves, active entities, total spawns, and reference depth. Boss phases are progress-ordered visual states. Reward hooks report proof/XAR/scrap intent but do not modify the wallet, inventory, or save. Use the deterministic simulator before live execution.
""",
            keywords=("encounter", "raid", "wave", "boss phase", "friendly", "reward hook"),
            main_tab="Authoring",
            authoring_tab="Encounter",
            example="examples/pcp3/encounter_runtime_demo.pcp3",
            document="docs/PCP3_BRANCH10_ENCOUNTER_RAID_BOSS_FRIENDLY_RUNTIME.md",
        ),
        _topic(
            "streaming",
            "Streaming, LOD and Large-Asset Runtime",
            "Runtime",
            "Apply deterministic distance LOD and semantic-priority sampling without changing the global adaptive 8M environment baseline.",
            """
Streaming adds Near, Mid, Far, and Very Far ratios, minimum/maximum points, semantic reserve, stable chunk manifests, profile presets, and upload-budget intent. Sampling occurs before expensive animation and world transforms. Background loading, partial binary reads, and GPU chunk decoding are preserved as future intent; Branch 11 does not claim a free-running asynchronous loader.
""",
            keywords=("streaming", "lod", "chunk", "adaptive 8m", "semantic reserve", "pop-in", "large asset"),
            main_tab="Authoring",
            authoring_tab="Streaming",
            example="examples/pcp3/streaming_lod_demo.pcp3",
            document="docs/PCP3_BRANCH11_STREAMING_LOD_LARGE_ASSET_RUNTIME.md",
        ),
        _topic(
            "blocked_actions",
            "Why Is This Action Blocked?",
            "Troubleshooting",
            "Understand why authored data can be preserved while execution remains telemetry-only.",
            """
PCP3 preserves future authoring intent, but the current runtime executes only an approved allowlist. Scripts, external programs, damage, health changes, wallet/economy changes, inventory changes, save mutation, unrestricted AI commands, deep reference nesting, and unguarded teleportation are blocked. The editor should report telemetry_only or a validation warning rather than deleting the authored record.

To make an approved action execute, enable every required guarded layer, select a Game/Stress target, resolve references, and use the exact approved action spelling.
""",
            keywords=("blocked", "telemetry only", "unsafe", "script", "damage", "economy", "save"),
            main_tab="Authoring",
            authoring_tab="Interaction",
            blocked_reason="The requested effect is outside the current runtime allowlist or a required guarded layer is disabled.",
        ),
        _topic(
            "missing_references",
            "Missing Asset, Portal, Theme or Placement References",
            "Troubleshooting",
            "Resolve database IDs safely without replacing them with arbitrary filesystem paths.",
            """
Export referenced assets first and use the exact database Asset ID, not the display name or filename. Run World, Encounter, Factory, or Streaming audits after export. A missing reference should produce a warning, inactive portal/placement, or omitted spawn—not a crash. Reference depth is intentionally limited to prevent cycles and unbounded expansion.
""",
            keywords=("missing", "reference", "asset id", "portal destination", "not found", "cycle"),
            main_tab="Authoring",
            authoring_tab="World",
        ),
        _topic(
            "full_map_stability",
            "Full Map, Signal Void and Vanishing-World Diagnostics",
            "Troubleshooting",
            "Interpret visibility and route-containment evidence when rooms, walls, or scanner geometry disappear.",
            """
Healthy Full Map runs retain every room range and keep DRAW above zero. Signal Void is not a room; it means the stress route left every authored walk area. Route containment should convert raw Signal Void into a valid effective room. Continuous FULL_MAP restore messages, decreasing represented-room counts, or zero renderer submission are failures. Inspect native_stress_visibility_trace.csv and native_stress_route_containment_trace.csv.
""",
            keywords=("black", "walls disappear", "signal void", "full map", "scanner empty", "route guard", "draw zero"),
            document="docs/PCP3_BRANCH8_R2_ROUTE_CONTAINMENT_FULL_MAP_STABILITY.md",
        ),
        _topic(
            "performance_troubleshooting",
            "Performance, LOD Pop-In and Large-Asset Troubleshooting",
            "Troubleshooting",
            "Tune per-asset Streaming without reducing the accepted resident world baseline.",
            """
Begin with adaptive_8m. Reduce an authored asset's maximum points or distant ratios before changing the global environment tier. Increase semantic reserve when portals, walls, lights, or entity silhouettes become unreadable. Increase hysteresis when a moving camera repeatedly crosses tier boundaries. Use chunk audit totals to confirm every source point belongs to one stable chunk.
""",
            keywords=("fps", "performance", "pop-in", "memory", "lod", "hysteresis", "intel mesa"),
            main_tab="Authoring",
            authoring_tab="Streaming",
        ),
        _topic(
            "crash_recovery",
            "Crash Logs, Workspace Repair and Safe Recovery",
            "Troubleshooting",
            "Recover the editor without deleting projects, brushes, colors, or certificates.",
            """
Crash logs are stored under reports and archived during repair installers. Use scripts/repair_pcp3_workspace.sh when pane or sidebar state is malformed, or scripts/reset_pcp3_workspace.sh only when a clean layout is required. Workspace repair targets config state; it does not delete projects, exported database assets, brushes, Custom Colors, or certificate proof chains.
""",
            keywords=("crash", "traceback", "workspace", "reset", "repair", "layout"),
            document="docs/PCP3_BRANCH7_R1_INTERACTION_AUTHORING_REPAIR.md",
        ),
    ]

    for key, (label, summary, checklist) in MODE_WORKFLOWS.items():
        topics.append(
            _topic(
                f"mode_{key}",
                f"Worked Mode Workflow — {label}",
                "Nine Environment Modes",
                summary,
                "\n".join(f"{index}. {step}" for index, step in enumerate(checklist, start=1)),
                keywords=(key, label, "mode template", "worked example"),
                main_tab="Mode",
                mode_key=key,
                example=f"examples/pcp3/tutorials/{key}_starter.pcp3",
                document=f"docs/tutorials/PCP3_MODE_{key.upper()}_WORKFLOW.md",
                checklist=checklist,
            )
        )

    return tuple(topics)


TOPICS = build_topics()
TOPIC_BY_KEY = {topic.key: topic for topic in TOPICS}


def categories(topics: Iterable[HelpTopic] = TOPICS) -> tuple[str, ...]:
    ordered: list[str] = []
    for topic in topics:
        if topic.category not in ordered:
            ordered.append(topic.category)
    return tuple(ordered)


def search_topics(query: str, topics: Iterable[HelpTopic] = TOPICS) -> list[HelpTopic]:
    words = [word for word in re.split(r"\s+", query.casefold().strip()) if word]
    if not words:
        return list(topics)
    scored: list[tuple[int, HelpTopic]] = []
    for topic in topics:
        text = topic.searchable_text()
        if not all(word in text for word in words):
            continue
        score = 0
        title = topic.title.casefold()
        summary = topic.summary.casefold()
        for word in words:
            if word in title:
                score += 8
            if word in summary:
                score += 4
            if word in topic.key.casefold():
                score += 3
            score += text.count(word)
        scored.append((score, topic))
    scored.sort(key=lambda row: (-row[0], row[1].category, row[1].title))
    return [topic for _score, topic in scored]


def topics_for_context(context: HelpContext) -> list[HelpTopic]:
    scored: list[tuple[int, HelpTopic]] = []
    for topic in TOPICS:
        score = 0
        if context.authoring_tab and topic.authoring_tab == context.authoring_tab:
            score += 20
        if context.main_tab and topic.main_tab == context.main_tab:
            score += 10
        if context.tool_key and topic.tool_key == context.tool_key:
            score += 8
        if context.mode_key and topic.mode_key == context.mode_key:
            score += 16
        if score:
            scored.append((score, topic))
    scored.sort(key=lambda row: (-row[0], row[1].category, row[1].title))
    if scored:
        return [topic for _score, topic in scored]
    return [TOPIC_BY_KEY["quick_start"]]


def resolve_resource(root_path: Path, relative: str) -> Path | None:
    if not relative:
        return None
    path = (root_path / relative).resolve()
    root = root_path.resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path if path.exists() else None


def topic_markdown(topic: HelpTopic) -> str:
    parts = [f"# {topic.title}", "", topic.summary, "", topic.body.strip(), ""]
    if topic.checklist:
        parts.extend(["## Checklist", ""])
        parts.extend(f"- [ ] {item}" for item in topic.checklist)
        parts.append("")
    if topic.blocked_reason:
        parts.extend(["## Why blocked", "", topic.blocked_reason, ""])
    if topic.example:
        parts.extend(["## Example", "", f"`{topic.example}`", ""])
    if topic.document:
        parts.extend(["## Related documentation", "", f"`{topic.document}`", ""])
    return "\n".join(parts).rstrip() + "\n"


def guide_markdown(topics: Iterable[HelpTopic] = TOPICS) -> str:
    parts = [
        "# Point Cloud Paint++ Authoring Help Guide",
        "",
        "Schema: `pcp3_authoring_help_v1`",
        "",
        "This guide mirrors the searchable Help → Authoring Help Guide window in Branch 12.",
        "",
        "## Contents",
        "",
    ]
    for category in categories(topics):
        parts.append(f"### {category}")
        parts.append("")
        for topic in topics:
            if topic.category == category:
                parts.append(f"- [{topic.title}](#{_anchor(topic.title)})")
        parts.append("")
    for topic in topics:
        parts.append(topic_markdown(topic))
    return "\n".join(parts).rstrip() + "\n"


def _anchor(title: str) -> str:
    value = re.sub(r"[^a-z0-9\s-]", "", title.casefold())
    return re.sub(r"[\s-]+", "-", value).strip("-")
