from __future__ import annotations

from typing import Iterable
import re

from tools.pcp3 import help_guide as base

HELP_CENTER_SCHEMA = "pcp3_help_center_v2"

GUIDE_SCOPES: dict[str, str] = {
    "all": "All Guides",
    "editor": "Complete Editor",
    "authoring": "Authoring",
    "mode": "Mode",
    "tools": "Tools",
    "troubleshooting": "Troubleshooting",
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
) -> base.HelpTopic:
    return base.HelpTopic(
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


EDITOR_TOPICS: tuple[base.HelpTopic, ...] = (
    _topic(
        "editor_overview",
        "Complete Editor — Mental Model and Recommended Workflow",
        "Editor Guide — Start Here",
        "Understand how Mode, geometry, semantics, authoring records, proof and export fit together.",
        """
Treat a PCP3 asset as five connected parts: Mode describes the whole asset; geometry stores visible points; semantics describe runtime meaning; Authoring records describe optional behavior; certificate/validation/export prove and deliver the result. A project may contain geometry without behavior. Guarded runtimes execute only when explicitly enabled.

Recommended order: choose Mode, apply Template, identify the asset, create semantic geometry, inspect multiple views, validate static data, add only required Authoring records, compile dry runs, export, then test in Native Preview/game/stress.
""",
        keywords=("complete editor", "mental model", "workflow", "start", "overview"),
        main_tab="Mode",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
        checklist=(
            "Mode chosen before construction",
            "Template reviewed",
            "Unique Asset ID and creator",
            "Semantic layers",
            "Validation reviewed",
            "Only required runtimes enabled",
            "Native test completed",
        ),
    ),
    _topic(
        "editor_window_map",
        "Complete Editor — Window Map",
        "Editor Guide — Interface",
        "Learn what the menu, command rows, Active Tool HUD, tools sidebar, viewport, project sidebar and status bar control.",
        """
The menu and compact command row expose file/edit/preview operations. The global options row chooses Mode, view layout, projection, display and viewport budget. The Active Tool HUD controls brush parameters, semantic, color, alpha and active depth. The left side selects direct tools and generators. The center is the editable viewport. The right sidebar owns Layers, Depth, Mode, Authoring, Properties, Certificate and History. The bottom status row reports the last operation and point/layer/selection totals.
""",
        keywords=("window", "interface", "toolbar", "hud", "sidebar", "status bar"),
        main_tab="Layers",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_project_lifecycle",
        "New, Open, Save, Export and Project Lifecycle",
        "Editor Guide — Projects",
        "Move safely from a new project to a sealed export without losing the accepted source.",
        """
New and Open confirm before discarding dirty work. Save writes the editable PCP3 project, sealed cloud and certificate lineage. Export Asset writes a database bundle and only the advanced sidecars applicable to enabled systems. Keep files with the same asset stem together. Use sibling update folders for phase changes and copy tutorial starters before editing them into real assets.
""",
        keywords=("new", "open", "save", "export", "dirty", "project lifecycle"),
        main_tab="Properties",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_global_controls",
        "Environment, View, Projection, Display and Viewport Controls",
        "Editor Guide — Interface",
        "Understand the global row without confusing visualization controls with source-data edits.",
        """
Environment chooses the Mode. View selects Single, 3-Square or 4-Square. Projection selects an individual pane or an all-pane preset. Display changes how the same points are visualized: RGB, Layer, Point, Semantic or Tool. Viewport selects a bounded editor display budget. These visualization choices do not rewrite point color or semantics.
""",
        keywords=("environment", "view", "projection", "display", "viewport", "rgb"),
        main_tab="Depth",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_sidebar_pages",
        "Layers, Depth, Mode, Authoring, Properties, Certificate and History",
        "Editor Guide — Sidebar",
        "Use the right sidebar as the project control center and navigate oversized pages with the shared scrollbar.",
        """
Template, Validate and Studio remain visible above the sidebar. With Sub-Tab off, X/Y scrolls the active main page. With Sub-Tab on, it scrolls wrapped Authoring tab rows. Layers manages structure; Depth manages pane depth; Mode explains the profile; Authoring contains advanced systems; Properties stores document/runtime preview identity; Certificate owns provenance; History shows edit operations.
""",
        keywords=("layers", "depth", "mode", "authoring", "properties", "certificate", "history", "sub-tab"),
        main_tab="Layers",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_viewports",
        "Orthographic, Perspective and Native Viewports",
        "Editor Guide — Viewports",
        "Use precise 2D placement, perspective form checks and the authoritative native renderer together.",
        """
Orthographic panes are best for exact coordinates; active-pane depth supplies the hidden axis. Perspective 3D checks form and supports a camera-facing editing plane. Each pane keeps independent pan, zoom, angle and depth. Native Preview uses the SignalCloud OpenGL renderer and is authoritative for dense-cloud appearance, point radius, runtime evidence and LOD behavior.
""",
        keywords=("orthographic", "perspective", "native preview", "depth", "single", "4-square"),
        main_tab="Depth",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_layers_semantics",
        "Layer Structure, Visibility, Locks, Opacity and Semantics",
        "Editor Guide — Data",
        "Organize the cloud so both humans and runtime systems can understand it.",
        """
Layer names and groups organize editing. Visibility controls ordinary preview submission. Locks protect finished geometry. Opacity affects composition where supported. Semantic is the runtime category and is more important to execution than the layer's display name. Separate guides/effects/structure and remember that trigger-semantic points are not executable Gameplay trigger records.
""",
        keywords=("layer", "visibility", "lock", "opacity", "semantic", "group"),
        main_tab="Layers",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_validation_export",
        "Validation, Certificates, Sidecars and Export Bundles",
        "Editor Guide — Delivery",
        "Interpret error/warning/info/pass results and keep the complete asset bundle together.",
        """
Errors identify invalid current records. Warnings identify missing identity, profile structure, references or budget concerns. Info records recommendations/future metadata. Certificate proof chains preserve authorship and checksums. Core export files share one stem; advanced authoring/runtime systems add sidecars only when applicable. Never rename one sidecar alone.
""",
        keywords=("validation", "certificate", "sidecar", "checksum", "export bundle"),
        main_tab="Certificate",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_native_runtime",
        "Native Preview, Game, Stress and Guarded Runtime Boundaries",
        "Editor Guide — Runtime",
        "Know which test path to use and why preserved authoring data may remain inactive.",
        """
Runtime Playback is non-destructive inspection. Native Preview verifies the SignalCloud renderer. Game testing checks guarded integration in actual zones. Native Stress measures route, visibility, point submission, encounters and LOD. Scripts, damage, economy, save mutation, unrestricted AI and deep nesting remain blocked unless a dedicated approved service is introduced.
""",
        keywords=("native", "game", "stress", "guarded", "runtime", "blocked"),
        main_tab="Authoring",
        authoring_tab="Playback",
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_data_recovery",
        "User Data, Workspace Memory and Safe Recovery",
        "Editor Guide — Recovery",
        "Repair interface state without deleting projects, brushes, colors or certificate history.",
        """
Projects, brushes, palettes, Custom Colors, snapshots and dry runs live under user_data. Workspace layout and selected tabs live in config/pcp3_workspace.json. Use repair_pcp3_workspace.sh for malformed pane/sidebar state and reset_pcp3_workspace.sh only for a deliberate clean layout. Incremental sibling installers preserve user-owned data.
""",
        keywords=("user data", "workspace", "repair", "reset", "custom colors", "preserve"),
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
    _topic(
        "editor_shortcuts",
        "Editor Keyboard and Mouse Reference",
        "Editor Guide — Reference",
        "Remember the small set of global controls, then use the context-aware guide for tool-specific actions.",
        """
F1 opens the Complete Editor Help Center. Shift+F1 opens the best topic for the selected main tab, Authoring tab, tool and Mode. F5 opens Native Preview. Escape cancels the active curve chain or compatible transient operation. Middle-drag pans editor panes. Left/right actions depend on the active tool.
""",
        keywords=("shortcut", "keyboard", "mouse", "f1", "f5", "escape", "middle drag"),
        document="docs/PCP3_EDITOR_HELP_GUIDE.md",
    ),
)


MODE_TOPICS: tuple[base.HelpTopic, ...] = (
    _topic(
        "mode_overview",
        "Mode Guide — What Mode Controls",
        "Mode Guide — Foundations",
        "Understand Mode as the profile for the whole asset rather than a visual preset.",
        """
Mode selects the asset purpose, default canvas extent, recommended point budget, tool profile, recommended semantics, required/optional layer template, metadata expectations and preserved future systems. Mode does not automatically replace existing geometry or execute runtime behavior.
""",
        keywords=("mode", "profile", "purpose", "whole asset"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
    _topic(
        "mode_choose",
        "Mode Guide — Choosing the Correct Asset Type",
        "Mode Guide — Foundations",
        "Choose by primary runtime job: entity, object, theme, room, liquid or encounter layout.",
        """
Shape alone is not enough. A hostile humanoid is Enemy; a humanoid statue is Environment Object. Room describes one world-space package; Raid describes encounter layout. Environment Theme is a reusable semantic kit; Room is a specific connected location. Liquid Maker is for reusable surface/volume/flow assets.
""",
        keywords=("choose mode", "enemy vs object", "room vs raid", "theme vs room"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
    _topic(
        "mode_template_behavior",
        "Mode Guide — Template Behavior",
        "Mode Guide — Templates",
        "Apply an additive, idempotent starting structure without erasing custom work.",
        """
Template adds missing profile layers, reuses an empty initial Base Points layer when possible and records template metadata. It does not erase points, remove custom layers or duplicate an already matching layer name. The generated structure is a starting checklist, not a finished asset.
""",
        keywords=("template", "idempotent", "base points", "required layer", "optional layer"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
    _topic(
        "mode_profile_anatomy",
        "Mode Guide — Reading a Mode Profile",
        "Mode Guide — Profiles",
        "Interpret purpose, semantics, layers, metadata, future systems, extent and budget.",
        """
Purpose states the design intent. Recommended semantics identify runtime-readable categories. Required and optional layers form the suggested project structure. Required/recommended metadata describe identity and behavior fields. Future systems are preserved design intent, not a promise of current execution. The point budget is a per-asset recommendation and does not replace the global resident world baseline.
""",
        keywords=("profile", "required metadata", "future systems", "point budget", "extent"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
    _topic(
        "mode_switching",
        "Mode Guide — Switching an Existing Project Safely",
        "Mode Guide — Migration",
        "Preserve geometry while deliberately reconciling new layers, semantics and runtime records.",
        """
Save first, change Mode, apply Template once, review every added layer, reassign old semantics where needed, disable incompatible runtimes, validate and retest Native Preview. Do not repeatedly change Mode merely to collect every template. Existing points and custom layers are preserved rather than destructively converted.
""",
        keywords=("change mode", "switch mode", "migration", "preserve geometry"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
        checklist=("Saved first", "Template applied once", "Layers reconciled", "Semantics reviewed", "Runtimes reviewed", "Validation rerun"),
    ),
    _topic(
        "mode_validation",
        "Mode Guide — Validation Language",
        "Mode Guide — Validation",
        "Understand which profile findings block current use and which preserve future intent.",
        """
Mode validation checks identity, creator, empty/non-finite points, radius, point budget, required layers, semantic profile, mode metadata and runtime preview transform. Errors indicate invalid current data. Warnings identify important omissions or recommendations. Info preserves future/recommended fields without blocking export.
""",
        keywords=("mode validation", "error", "warning", "info", "missing layer"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
    _topic(
        "mode_budget",
        "Mode Guide — Extents, Point Budgets and Streaming",
        "Mode Guide — Performance",
        "Use mode recommendations as per-asset planning limits and Streaming for deliberate exceptions.",
        """
Enemy begins at 120K recommended points, Environment Object at 250K, Room at 4M and Raid at 6M, with mode-specific extents. Exceeding a recommendation remains valid but produces guidance. Use deterministic Streaming/LOD for dense assets rather than lowering the accepted global adaptive 8M world baseline first.
""",
        keywords=("mode budget", "points", "extent", "streaming", "lod"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
    _topic(
        "mode_semantics_runtime",
        "Mode Guide — Mode, Semantics and Runtime Roles",
        "Mode Guide — Semantics",
        "Keep whole-asset identity, point meaning and executable records separate.",
        """
Mode says what the asset is. Semantics say what point regions mean. Authoring records say what guarded behavior may occur. A Room-mode portal layer with portal semantics is visible geometry; a World portal record defines the guarded transfer. Trigger-semantic points mark/evidence a region; a Gameplay trigger record defines executable conditions and actions.
""",
        keywords=("mode semantic", "runtime role", "portal geometry", "trigger record"),
        main_tab="Mode",
        document="docs/PCP3_MODE_HELP_GUIDE.md",
    ),
)


TOOL_TOPICS: tuple[base.HelpTopic, ...] = (
    _topic(
        "tool_hud",
        "Tools Guide — Active Tool HUD",
        "Tools Guide — Foundations",
        "Set size, hardness, spacing, point radius, semantic, color, alpha and active depth before drawing.",
        """
Size controls Brush/Eraser/Recolor influence. Hardness controls falloff where supported. Spacing controls interpolated stamp density. Point px/radius controls new-point appearance. Semantic and RGBA apply to new points. Active-pane depth supplies the hidden coordinate in orthographic panes. Changing the HUD does not retroactively edit existing points.
""",
        keywords=("hud", "size", "hardness", "spacing", "point px", "alpha", "depth"),
        tool_key="brush",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_select",
        "Tools Guide — Select Region",
        "Tools Guide — Direct Editing",
        "Select a projected 3D region safely before bulk operations.",
        """
Click two opposite corners or click-drag a live rectangle. Shift adds to the existing selection. A click without a meaningful drag leaves the first corner active. Always inspect the selection from another projection because multiple 3D points can overlap in one 2D view.
""",
        keywords=("select region", "selection", "shift", "rectangle"),
        tool_key="select",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_pencil",
        "Tools Guide — Point Pencil",
        "Tools Guide — Direct Editing",
        "Draw a precise interpolated point path on the active edit plane.",
        """
Left-drag paints a continuous precision line. Interpolation fills ordinary gaps between mouse events. Orthographic strokes use active-pane depth for the hidden axis; Perspective uses the camera-facing edit plane. Use Pencil for outlines, cables, trim and small corrections.
""",
        keywords=("point pencil", "continuous", "stroke", "edit plane"),
        tool_key="pencil",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_brush",
        "Tools Guide — 3D Brush and Advanced Channels",
        "Tools Guide — Direct Editing",
        "Paint dense geometry or authoring channels in editor or native brush mode.",
        """
Orthographic panes paint a disc on their edit plane; Perspective paints on a camera-facing plane. Spacing controls stamp density. The Brush Editor supports geometry, bone_weight, flow_strength, trigger_mask, light_intensity and density. F5 opens Native Preview and B toggles the native brush bridge where supported.
""",
        keywords=("3d brush", "bone weight", "native brush", "density", "flow strength"),
        tool_key="brush",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_eraser",
        "Tools Guide — Eraser",
        "Tools Guide — Direct Editing",
        "Remove points inside a full 3D radius without assuming the cursor is only a 2D circle.",
        """
Eraser is destructive and can remove hidden/rear points inside the 3D radius. Lock protected layers, use a small size and inspect another projection after short strokes. For exact deletion, select a bounded region rather than broadly erasing.
""",
        keywords=("eraser", "delete points", "3d radius", "hidden geometry"),
        tool_key="eraser",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_recolor",
        "Tools Guide — Recolor",
        "Tools Guide — Direct Editing",
        "Change source RGBA inside the brush radius without moving points.",
        """
Recolor permanently changes point color/alpha. It differs from Display modes and runtime Theme slots, which can alter visualization without rewriting source RGB. Use a small radius and locked layers for precise corrections.
""",
        keywords=("recolor", "rgba", "alpha", "source color"),
        tool_key="recolor",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_picker",
        "Tools Guide — Attribute Picker",
        "Tools Guide — Direct Editing",
        "Sample the nearest point into the Active Tool HUD.",
        """
Picker copies compatible color, alpha, point radius and semantic attributes. Hide overlapping layers or change projection when the wrong point is sampled. After picking, return to Pencil, Brush or Recolor and verify the HUD before drawing.
""",
        keywords=("attribute picker", "sample", "nearest point", "copy color"),
        tool_key="picker",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_line_curve",
        "Tools Guide — Line / Curve",
        "Tools Guide — Direct Editing",
        "Create deterministic straight or curved paths from anchors.",
        """
Left-click starts and finishes. Right-click adds anchors. Double-right-click removes the nearest anchor. Escape cancels the active chain. Spacing controls resampling density, so very low values can create a large point count.
""",
        keywords=("line", "curve", "anchor", "catmull", "escape"),
        tool_key="line",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_rotate",
        "Tools Guide — Rotate",
        "Tools Guide — Transform",
        "Rotate selected geometry around X/Y without confusing it with camera rotation.",
        """
Rotate changes selected points. Left click adds 1 degree on X, double-click adds 5 degrees and dragging adjusts continuously; right-button behavior controls Y. Inspect all projections after each small adjustment. View-angle controls change the camera instead.
""",
        keywords=("rotate", "x y", "selected geometry", "camera"),
        tool_key="rotate",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_roll",
        "Tools Guide — Roll",
        "Tools Guide — Transform",
        "Rotate selected geometry around Z with click or drag controls.",
        """
Left applies positive Z roll and right applies negative roll. Click changes one degree, double-click five degrees and drag changes continuously. Use Undo immediately when the selected pivot/result is not what you expected.
""",
        keywords=("roll", "z rotation", "selected geometry"),
        tool_key="roll",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_pan",
        "Tools Guide — Pan",
        "Tools Guide — Navigation",
        "Move a pane camera without changing project points.",
        """
Drag with Pan active, or middle-drag at any time. Pane pan is independent, including NP Pan in the Perspective bridge. Reset Viewports restores framing when the asset is lost off-screen.
""",
        keywords=("pan", "middle drag", "camera", "np pan"),
        tool_key="pan",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_window_sync",
        "Tools Guide — Window Sync",
        "Tools Guide — Navigation",
        "Copy selected view state once after the 1.3-second buffer, then return to another tool.",
        """
Window Sync is a one-shot alignment tool, not permanent pane linkage. Choose source and targets, wait for the buffered application and switch away. Targets are clamped to the document envelope and malformed feedback-loop workspace values are repaired.
""",
        keywords=("window sync", "1.3 seconds", "pane alignment", "buffer"),
        tool_key="window_sync",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_guided_generators",
        "Tools Guide — Guided Shapes, Architecture and Room Shell",
        "Tools Guide — Generators",
        "Use region-derived, bounded generators and inspect the cyan preview before committing points.",
        """
Choose Box, Sphere, Cylinder, Room Shell, Humanoid Guide, Liquid Plane or an architecture preset; select a region; tune parameters; inspect cyan evidence; generate. Opening frames leave the center unfilled but do not subtract from an existing wall. Room Shell creates separate Walls, Floor and Ceiling layers.
""",
        keywords=("guided shape", "room shell", "wall", "fixture", "opening", "cyan preview"),
        document="docs/PCP3_TOOLS_HELP.md",
    ),
    _topic(
        "tool_undo_safety",
        "Tools Guide — Undo, Locks and Destructive-Edit Safety",
        "Tools Guide — Safety",
        "Protect accepted geometry before broad Eraser, Recolor, rotation or generator operations.",
        """
Save milestones before large destructive edits, lock protected layers, confirm selection count and inspect the result from another projection. Undo immediately after an unexpected operation rather than continuing several edits. Metadata-only authoring changes avoid copying the entire cloud into history.
""",
        keywords=("undo", "redo", "lock", "destructive", "safety", "selection count"),
        main_tab="History",
        document="docs/PCP3_TOOLS_HELP.md",
    ),
)

ALL_TOPICS: tuple[base.HelpTopic, ...] = EDITOR_TOPICS + MODE_TOPICS + TOOL_TOPICS + base.TOPICS
TOPIC_BY_KEY = {topic.key: topic for topic in ALL_TOPICS}


def _base_scopes(topic: base.HelpTopic) -> set[str]:
    scopes: set[str] = {"all"}
    if topic in EDITOR_TOPICS:
        scopes.add("editor")
    if topic in MODE_TOPICS or topic.key.startswith("mode_") or topic.category == "Nine Environment Modes":
        scopes.add("mode")
    if topic in TOOL_TOPICS or topic.category == "Core Editing" or topic.tool_key:
        scopes.add("tools")
    if topic.category in {"Advanced Authoring", "Runtime"} or topic.authoring_tab:
        scopes.add("authoring")
    if topic.category == "Troubleshooting" or topic.key in {"crash_recovery", "full_map_stability", "blocked_actions", "missing_references", "performance_troubleshooting"}:
        scopes.add("troubleshooting")
    if topic.category in {"Interface", "Files and Export", "Start Here"}:
        scopes.add("editor")
    return scopes


TOPIC_SCOPES: dict[str, frozenset[str]] = {topic.key: frozenset(_base_scopes(topic)) for topic in ALL_TOPICS}


def topics_for_scope(scope: str = "all") -> list[base.HelpTopic]:
    key = scope if scope in GUIDE_SCOPES else "all"
    return [topic for topic in ALL_TOPICS if key in TOPIC_SCOPES[topic.key]]


def categories(topics: Iterable[base.HelpTopic]) -> tuple[str, ...]:
    ordered: list[str] = []
    for topic in topics:
        if topic.category not in ordered:
            ordered.append(topic.category)
    return tuple(ordered)


def search_topics(query: str, scope: str = "all") -> list[base.HelpTopic]:
    pool = topics_for_scope(scope)
    words = [word for word in re.split(r"\s+", query.casefold().strip()) if word]
    if not words:
        return pool
    scored: list[tuple[int, base.HelpTopic]] = []
    for topic in pool:
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


def topics_for_context(context: base.HelpContext) -> list[base.HelpTopic]:
    scored: list[tuple[int, base.HelpTopic]] = []
    for topic in ALL_TOPICS:
        score = 0
        if context.authoring_tab and topic.authoring_tab == context.authoring_tab:
            score += 20
        if context.main_tab and topic.main_tab == context.main_tab:
            score += 10
        if context.tool_key and topic.tool_key == context.tool_key:
            score += 32 if context.main_tab in {"", "Layers", "Depth"} else 8
        if context.mode_key and topic.mode_key == context.mode_key:
            score += 16
        if context.main_tab == "Mode" and topic.key == "mode_overview":
            score += 8
        if score:
            scored.append((score, topic))
    scored.sort(key=lambda row: (-row[0], row[1].category, row[1].title))
    return [topic for _score, topic in scored] or [TOPIC_BY_KEY["editor_overview"]]


def topic_markdown(topic: base.HelpTopic) -> str:
    return base.topic_markdown(topic)
