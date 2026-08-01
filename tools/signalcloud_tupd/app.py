from __future__ import annotations

import json
import subprocess
import time
import tkinter as tk
from dataclasses import asdict
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tools.asset_doctor.content_abi import scan_content
from tools.signalcloud_studio.ui import FlowBar

from .analysis import (
    PART_CATALOG, PART_BY_ID, GraphReport, analyze_recipe_graph,
    apply_suggested_connections, bump_recipe_revision, duplicate_recipe,
)
from .catalog import TupdCatalogEntry, load_catalog_recipe, scan_catalog
from .codec import load_recipe, save_recipe_atomic
from .exporter import export_managed_recipe
from .model import VALID_TEST_ACTIONS, TupdPreview, TupdRecipe, TupdResult
from .simulation import TupdSandbox

PALETTE_ITEMS = tuple((entry.item_id, entry.interface_id) for entry in PART_CATALOG)
SOCKET_CHOICES = ("grip", "body", "signal", "mount", "anchor", "duplicate")
QUICK_GUIDE = """Tupd A8a3r1 guided authoring workflow

1. SELECT, DUPLICATE, OR VERSION
   Open a starter to learn from. Duplicate as User Recipe before changing shipped content. Bump Revision when the same recipe evolves while keeping its identity and parent history.

2. BUILD THE INPUT GRAPH
   Add parts from the guided palette. The palette shows each part's interface and intended role. Mark every input Retained or Consumed; Tupd Tape must be consumed.

3. CONNECT AND VALIDATE
   Select a graph node, choose a target and socket, then connect it. Validate Graph checks missing endpoints, duplicate edges, cycles, orphan inputs, incompatible normal sockets, forced-connection rules, penalties, tests, result sockets, and tags. Auto Connect applies only deterministic starter-safe suggestions.

4. PREVIEW AND INSPECT
   Preview checks inventory, cost, condition, weight, stability, point budget, and save isolation. The Graph Check tab explains every issue and the Compare / Test tab shows before/after values.

5. COMMIT, EQUIP/SPAWN, AND TEST
   Commit creates a sandbox result but does not equip it. Equip weapon/tool results or spawn object results, then run only declared tests. Normal inventory, XAR, weapon state, and save remain untouched.

6. EXPLODED NATIVE INSPECTION
   Open Native Stage. Press G to switch assembled/exploded geometry. Press V to cycle Result, Interfaces, Sockets, and Penalties views. I still toggles readable UI information.

7. SAVE DRAFT OR EXPORT
   Save Draft writes an unindexed authoring copy under user_data/studio. Export & Reload requires a valid graph and committed result, then writes a portable managed recipe and .tupdinstance under content/user/tupd.

The complete A8 authoring reference is available from the Help/Quick Guide tab and docs/help/TUPD_A8_AUTHORING_GUIDE.md. A8a3 closes the isolated authoring track without connecting transactions to live player inventory.
"""


class TupdWorkbenchApp(tk.Tk):
    def __init__(self, root_path: Path, initial: Path | None = None) -> None:
        super().__init__()
        self.root_path = Path(root_path).resolve()
        self.catalog_entries: dict[str, TupdCatalogEntry] = {}
        self.current = TupdRecipe()
        self.sandbox = TupdSandbox()
        self.preview = TupdPreview()
        self.graph_nodes: list[str] = list(self.current.inputs)
        self.selected_node: str | None = None
        self.connection_items: dict[str, tuple[bool, str]] = {}
        self.graph_issue_items: dict[str, object] = {}
        self.graph_report = analyze_recipe_graph(self.current)

        self.title("SignalCloud Tupd Workbench — A8a3r1")
        self.geometry("1500x920")
        self.minsize(1120, 720)

        self.status = tk.StringVar(value="A8a3r1 responsive graph authoring ready")
        self.guide_step = tk.StringVar(value="STEP 1 — Select a recipe or create a draft")
        self.recipe_id = tk.StringVar(value=self.current.recipe_id)
        self.recipe_label = tk.StringVar(value=self.current.label)
        self.recipe_revision = tk.IntVar(value=self.current.recipe_revision)
        self.mode = tk.StringVar(value=self.current.mode)
        self.base_item_id = tk.StringVar(value=self.current.base_item_id)
        self.result_id = tk.StringVar(value=self.current.result.result_id)
        self.result_name = tk.StringVar(value=self.current.result.display_name)
        self.result_kind = tk.StringVar(value=self.current.result.result_kind)
        self.preview_shape = tk.StringVar(value=self.current.preview_shape)
        self.cost_xar = tk.IntVar(value=self.current.cost_xar)
        self.repair_percent = tk.DoubleVar(value=self.current.repair_percent)
        self.stability_penalty = tk.DoubleVar(value=self.current.stability_penalty)
        self.weight_penalty = tk.DoubleVar(value=self.current.weight_penalty)
        self.point_budget = tk.IntVar(value=self.current.result.point_budget)
        self.force_connection = tk.BooleanVar(value=False)
        self.connection_target = tk.StringVar(value=self.current.base_item_id)
        self.connection_socket = tk.StringVar(value="grip")
        self.test_action = tk.StringVar(value="inspect")
        self.graph_summary = tk.StringVar(value="No preview yet")
        self.inventory_summary = tk.StringVar(value="Test inventory isolated from normal save")
        self.result_state_summary = tk.StringVar(value="NO COMMITTED RESULT")

        self._build()
        self.refresh_catalog()
        if initial is not None:
            self.after(50, lambda: self.open_path(initial))
        else:
            self.after(100, self.open_first_recipe)

    def _build(self) -> None:
        header = ttk.Frame(self, padding=(12, 10))
        header.pack(fill="x")
        title_row = ttk.Frame(header)
        title_row.pack(fill="x")
        ttk.Label(title_row, text="Tupd Authoring Workbench", font=("Sans", 17, "bold")).pack(side="left")
        ttk.Label(
            title_row,
            text="A8a3r1 · responsive actions · fitted graph · world-space native inspection",
            foreground="#45616b",
        ).pack(side="right")
        ttk.Label(
            header,
            text="Duplicate/version → connect → validate → preview → commit → inspect/test → managed export/reload",
        ).pack(anchor="w")
        guide = ttk.Label(header, textvariable=self.guide_step, font=("Sans", 10, "bold"), foreground="#276f7f")
        guide.pack(anchor="w", pady=(4, 0))

        # The complete workflow must remain reachable at the normal opening size.
        # FlowBar measures each action and deterministically wraps whole buttons
        # onto additional rows instead of clipping the right side of the toolbar.
        toolbar = FlowBar(header, padding=(0, 0))
        toolbar.pack(fill="x", pady=(8, 0))
        for text, command in (
            ("Open Recipe…", self.choose_recipe),
            ("New Draft", self.new_draft),
            ("Duplicate Recipe", self.duplicate_current),
            ("Bump Revision", self.bump_revision),
            ("Save Draft", self.save_draft),
            ("Refresh Catalog", self.refresh_catalog),
            ("Validate Graph", self.validate_graph),
            ("Auto Connect", self.auto_connect_graph),
            ("Preview/Compare", self.preview_recipe),
            ("Commit Sandbox", self.commit_sandbox),
            ("Equip/Spawn Result", self.equip_result),
            ("Test Result", self.test_result),
            ("Clear Result", self.clear_result),
            ("Reset Sandbox", self.reset_sandbox),
            ("Native Stage", self.launch_native),
            ("Export & Reload", self.export_current),
            ("Asset Doctor", self.asset_doctor),
        ):
            group = toolbar.group()
            ttk.Button(group, text=text, command=command).pack()
        ttk.Label(
            header, textvariable=self.status, foreground="#45616b",
            wraplength=1380, justify="left",
        ).pack(fill="x", anchor="w", pady=(4, 0))

        main = ttk.Panedwindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        left = ttk.Frame(main, padding=(0, 8, 8, 0))
        center = ttk.Frame(main, padding=(0, 8, 8, 0))
        right = ttk.Frame(main, padding=(0, 8, 0, 0))
        main.add(left, weight=1)
        main.add(center, weight=3)
        main.add(right, weight=2)
        self._build_catalog_palette(left)
        self._build_graph(center)
        self._build_inspector(right)

    def _build_catalog_palette(self, parent: ttk.Frame) -> None:
        ttk.Label(parent, text="Recipe Catalog", font=("Sans", 11, "bold")).pack(anchor="w")
        tree_frame = ttk.Frame(parent)
        tree_frame.pack(fill="both", expand=True, pady=(5, 8))
        self.catalog_tree = ttk.Treeview(tree_frame, show="tree", selectmode="browse", height=11)
        catalog_scroll = ttk.Scrollbar(tree_frame, orient="vertical", command=self.catalog_tree.yview)
        self.catalog_tree.configure(yscrollcommand=catalog_scroll.set)
        self.catalog_tree.pack(side="left", fill="both", expand=True)
        catalog_scroll.pack(side="right", fill="y")
        self.catalog_tree.bind("<<TreeviewSelect>>", self._catalog_selected)

        ttk.Separator(parent).pack(fill="x", pady=5)
        ttk.Label(parent, text="Part Palette", font=("Sans", 11, "bold")).pack(anchor="w")
        self.palette = tk.Listbox(parent, exportselection=False, height=9)
        for entry in PART_CATALOG:
            sockets = "/".join(entry.suggested_sockets) if entry.suggested_sockets else "transaction"
            self.palette.insert("end", f"{entry.label}  [{entry.interface_id} → {sockets}]")
        self.palette.pack(fill="both", expand=True, pady=(5, 5))
        controls = ttk.Frame(parent)
        controls.pack(fill="x")
        ttk.Button(controls, text="Add Input", command=self.add_palette_input).pack(side="left", fill="x", expand=True)
        ttk.Button(controls, text="Remove", command=self.remove_selected_node).pack(side="left", fill="x", expand=True, padx=(5, 0))
        ttk.Button(parent, text="Retained / Consumed", command=self.toggle_selected_consumed).pack(fill="x", pady=(5, 0))

        connection_box = ttk.LabelFrame(parent, text="Connection Editor", padding=7)
        connection_box.pack(fill="x", pady=(8, 0))
        ttk.Label(connection_box, text="Target node").grid(row=0, column=0, sticky="w")
        self.target_combo = ttk.Combobox(connection_box, textvariable=self.connection_target, state="readonly")
        self.target_combo.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        ttk.Label(connection_box, text="Socket").grid(row=1, column=0, sticky="w", pady=(5, 0))
        ttk.Combobox(connection_box, textvariable=self.connection_socket, values=SOCKET_CHOICES, state="readonly").grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(5, 0))
        ttk.Checkbutton(connection_box, text="Forced connection", variable=self.force_connection).grid(row=2, column=0, columnspan=2, sticky="w", pady=(5, 0))
        ttk.Button(connection_box, text="Connect selected input", command=self.connect_selected).grid(row=3, column=0, columnspan=2, sticky="ew", pady=(5, 0))
        connection_box.columnconfigure(1, weight=1)

        ttk.Label(
            parent,
            text="Commit creates a sandbox result but does not equip it. Use Equip / Spawn Result before testing. Normal inventory, live weapon, XAR, and save remain untouched.",
            wraplength=290,
            foreground="#53656d",
        ).pack(fill="x", pady=(8, 0))

    def _build_graph(self, parent: ttk.Frame) -> None:
        row = ttk.Frame(parent)
        row.pack(fill="x")
        ttk.Label(row, text="Assembly Graph", font=("Sans", 11, "bold")).pack(side="left")
        ttk.Button(row, text="Auto Connect", command=self.auto_connect_graph).pack(side="right", padx=(5, 0))
        ttk.Button(row, text="Validate", command=self.validate_graph).pack(side="right")
        # Keep the status on its own line so it cannot merge into the title in a
        # narrow center pane.
        ttk.Label(parent, textvariable=self.graph_summary, foreground="#45616b").pack(
            fill="x", anchor="w", pady=(3, 0)
        )
        self.graph = tk.Canvas(parent, background="#071018", highlightthickness=1, highlightbackground="#30434b")
        self.graph.pack(fill="both", expand=True, pady=(6, 0))
        self.graph.bind("<Configure>", lambda _event: self.redraw_graph())
        self.graph.bind("<Button-1>", self._graph_click)
        ttk.Label(parent, textvariable=self.inventory_summary, foreground="#45616b").pack(anchor="w", pady=(5, 0))
        ttk.Label(parent, textvariable=self.result_state_summary, font=("Sans", 10, "bold"), foreground="#276f7f").pack(anchor="w", pady=(2, 0))

    def _build_inspector(self, parent: ttk.Frame) -> None:
        self.notebook = ttk.Notebook(parent)
        self.notebook.pack(fill="both", expand=True)
        definition = ttk.Frame(self.notebook, padding=10)
        connections = ttk.Frame(self.notebook, padding=10)
        graph_check = ttk.Frame(self.notebook, padding=10)
        evidence = ttk.Frame(self.notebook, padding=10)
        guide = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(definition, text="Definition")
        self.notebook.add(connections, text="Connections")
        self.notebook.add(graph_check, text="Graph Check")
        self.notebook.add(evidence, text="Compare / Test")
        self.notebook.add(guide, text="Authoring Guide")

        fields = (
            ("Recipe ID", self.recipe_id),
            ("Label", self.recipe_label),
            ("Base item", self.base_item_id),
            ("Result ID", self.result_id),
            ("Result name", self.result_name),
        )
        for row, (label, variable) in enumerate(fields):
            ttk.Label(definition, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Entry(definition, textvariable=variable).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row = len(fields)
        ttk.Label(definition, text="Recipe revision").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Spinbox(definition, textvariable=self.recipe_revision, from_=1, to=9999).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(definition, text="Mode").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(
            definition, textvariable=self.mode,
            values=("modification", "forced_modification", "upgrade", "repair_small", "repair_full", "assembly"),
            state="readonly",
        ).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(definition, text="Result kind").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(definition, textvariable=self.result_kind, values=("weapon-modification", "weapon-upgrade", "repair", "barrier", "interactable", "tool"), state="readonly").grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        ttk.Label(definition, text="Ghost shape").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Combobox(definition, textvariable=self.preview_shape, values=("weapon", "tool", "barrier", "assembly"), state="readonly").grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
        row += 1
        for label, variable, minimum, maximum, increment in (
            ("Test cost XAR", self.cost_xar, 0, 500, 1),
            ("Repair %", self.repair_percent, 0, 100, 1),
            ("Stability penalty", self.stability_penalty, 0, 100, 1),
            ("Weight penalty", self.weight_penalty, -10, 100, 0.1),
            ("Point budget", self.point_budget, 64, 50_000, 64),
        ):
            ttk.Label(definition, text=label).grid(row=row, column=0, sticky="w", pady=3)
            ttk.Spinbox(definition, textvariable=variable, from_=minimum, to=maximum, increment=increment).grid(row=row, column=1, sticky="ew", padx=(8, 0), pady=3)
            row += 1
        definition.columnconfigure(1, weight=1)
        ttk.Button(definition, text="Apply fields to draft", command=self.apply_fields).grid(row=row, column=0, columnspan=2, sticky="ew", pady=(10, 0))

        top = ttk.Frame(connections)
        top.pack(fill="x")
        ttk.Label(top, text="Authored connections", font=("Sans", 11, "bold")).pack(side="left")
        ttk.Button(top, text="Remove selected", command=self.remove_selected_connection).pack(side="right")
        self.connection_tree = ttk.Treeview(connections, columns=("kind", "source", "target", "socket"), show="headings", height=12)
        for key, label, width in (
            ("kind", "Kind", 80), ("source", "Source", 165), ("target", "Target", 165), ("socket", "Socket", 90),
        ):
            self.connection_tree.heading(key, text=label)
            self.connection_tree.column(key, width=width, stretch=True)
        self.connection_tree.pack(fill="both", expand=True, pady=(7, 7))
        ttk.Label(connections, text="Result interfaces (comma separated)").pack(anchor="w")
        self.result_interfaces_text = ttk.Entry(connections)
        self.result_interfaces_text.pack(fill="x", pady=(2, 6))
        ttk.Label(connections, text="Result sockets (comma separated)").pack(anchor="w")
        self.result_sockets_text = ttk.Entry(connections)
        self.result_sockets_text.pack(fill="x", pady=(2, 6))
        ttk.Label(connections, text="Result tags (comma separated)").pack(anchor="w")
        self.result_tags_text = ttk.Entry(connections)
        self.result_tags_text.pack(fill="x", pady=(2, 6))
        ttk.Label(connections, text="Declared tests (comma separated)").pack(anchor="w")
        self.test_actions_text = ttk.Entry(connections)
        self.test_actions_text.pack(fill="x", pady=(2, 6))
        ttk.Button(connections, text="Apply connection metadata", command=self.apply_connection_metadata).pack(fill="x")

        graph_header = ttk.Frame(graph_check)
        graph_header.pack(fill="x")
        ttk.Label(graph_header, text="Deterministic graph analysis", font=("Sans", 11, "bold")).pack(side="left")
        ttk.Button(graph_header, text="Auto Connect Suggestions", command=self.auto_connect_graph).pack(side="right")
        self.graph_issue_tree = ttk.Treeview(
            graph_check, columns=("severity", "code", "subject"), show="headings", height=13
        )
        for key, label, width in (("severity", "Severity", 80), ("code", "Check", 150), ("subject", "Node / Connection", 220)):
            self.graph_issue_tree.heading(key, text=label)
            self.graph_issue_tree.column(key, width=width, stretch=True)
        self.graph_issue_tree.pack(fill="both", expand=True, pady=(8, 6))
        self.graph_issue_tree.bind("<<TreeviewSelect>>", self._graph_issue_selected)
        self.graph_issue_detail = tk.Text(graph_check, height=9, wrap="word", padx=9, pady=9)
        self.graph_issue_detail.pack(fill="both", expand=True)

        action_row = ttk.Frame(evidence)
        action_row.pack(fill="x")
        ttk.Label(action_row, text="Test action").pack(side="left")
        self.test_action_combo = ttk.Combobox(action_row, textvariable=self.test_action, values=tuple(sorted(VALID_TEST_ACTIONS)), state="readonly", width=12)
        self.test_action_combo.pack(side="left", padx=(6, 6))
        ttk.Button(action_row, text="Equip / Spawn", command=self.equip_result).pack(side="left")
        ttk.Button(action_row, text="Run Test", command=self.test_result).pack(side="left", padx=(5, 0))
        self.comparison = ttk.Treeview(evidence, columns=("before", "after"), show="tree headings", height=8)
        self.comparison.heading("#0", text="Property")
        self.comparison.heading("before", text="Before")
        self.comparison.heading("after", text="After")
        self.comparison.column("#0", width=170)
        self.comparison.column("before", width=110)
        self.comparison.column("after", width=160)
        self.comparison.pack(fill="x", pady=(8, 6))
        self.evidence = tk.Text(evidence, wrap="word", padx=10, pady=10)
        self.evidence.pack(fill="both", expand=True)
        self._write_evidence("Select a recipe, then Preview / Compare. Commit creates a separate result instance; equip/spawn and test are explicit steps.\n")

        guide_text = tk.Text(guide, wrap="word", padx=10, pady=10)
        guide_text.insert("1.0", QUICK_GUIDE)
        guide_text.configure(state="disabled")
        guide_text.pack(fill="both", expand=True)

    def _write_evidence(self, text: str) -> None:
        self.evidence.delete("1.0", "end")
        self.evidence.insert("end", text)

    @staticmethod
    def _csv_values(widget: ttk.Entry) -> list[str]:
        return [value.strip() for value in widget.get().split(",") if value.strip()]

    @staticmethod
    def _set_entry(widget: ttk.Entry, values: list[str]) -> None:
        widget.delete(0, "end")
        widget.insert(0, ", ".join(values))

    def duplicate_current(self) -> None:
        self.apply_fields_without_recursive_preview()
        stamp = int(time.time())
        source_id = self.current.recipe_id.replace("starter.", "").replace("user.", "")
        self.current = duplicate_recipe(
            self.current, f"user.{source_id}-{stamp}", f"{self.current.label} User Copy"
        )
        self.graph_nodes = list(self.current.inputs)
        self.selected_node = None
        self.sandbox.reset()
        self._sync_fields()
        self.preview_recipe()
        self.status.set("Created isolated user copy at revision 1; starter content remains unchanged")

    def bump_revision(self) -> None:
        self.apply_fields_without_recursive_preview()
        self.current = bump_recipe_revision(self.current)
        self.sandbox.reset()
        self._sync_fields()
        self.preview_recipe()
        self.status.set(f"Recipe revision advanced to r{self.current.recipe_revision}; commit a fresh result")

    def save_draft(self) -> None:
        self.apply_fields_without_recursive_preview()
        draft_dir = self.root_path / "user_data" / "studio" / "tupd_drafts"
        slug = "".join(character.lower() if character.isalnum() else "_" for character in self.current.recipe_id).strip("_") or "tupd_draft"
        path = save_recipe_atomic(draft_dir / f"{slug}_r{self.current.recipe_revision}.tupd", self.current)
        self.status.set(f"Unindexed draft saved: {path.relative_to(self.root_path)}")

    def validate_graph(self) -> None:
        self.apply_fields_without_recursive_preview()
        self.graph_report = analyze_recipe_graph(self.current)
        self._refresh_graph_report()
        self.redraw_graph()
        self.notebook.select(2)
        self.status.set(
            f"Graph {'valid' if self.graph_report.valid else 'blocked'} · "
            f"{self.graph_report.error_count} errors · {self.graph_report.warning_count} warnings · "
            f"signature {self.graph_report.signature}"
        )

    def auto_connect_graph(self) -> None:
        self.apply_fields_without_recursive_preview()
        updated, report = apply_suggested_connections(self.current)
        added = len(updated.connections) - len(self.current.connections)
        self.current = updated
        self.graph_nodes = list(self.current.inputs)
        self.graph_report = report
        self._sync_fields()
        self.preview_recipe()
        self.notebook.select(2)
        self.status.set(f"Auto Connect added {added} deterministic compatible connection(s)")

    def _refresh_graph_report(self) -> None:
        if not hasattr(self, "graph_issue_tree"):
            return
        self.graph_issue_items.clear()
        self.graph_issue_tree.delete(*self.graph_issue_tree.get_children())
        for issue in self.graph_report.issues:
            subject = issue.node_id or issue.connection or self.current.recipe_id
            item = self.graph_issue_tree.insert("", "end", values=(issue.severity.upper(), issue.code, subject))
            self.graph_issue_items[item] = issue
        summary = {
            "valid": self.graph_report.valid,
            "error_count": self.graph_report.error_count,
            "warning_count": self.graph_report.warning_count,
            "orphan_nodes": self.graph_report.orphan_nodes,
            "cycle_nodes": self.graph_report.cycle_nodes,
            "suggested_connections": self.graph_report.suggested_connections,
            "signature": self.graph_report.signature,
        }
        self.graph_issue_detail.delete("1.0", "end")
        self.graph_issue_detail.insert("end", json.dumps(summary, indent=2, sort_keys=True))

    def _graph_issue_selected(self, _event: object = None) -> None:
        selection = self.graph_issue_tree.selection()
        if not selection or selection[0] not in self.graph_issue_items:
            return
        issue = self.graph_issue_items[selection[0]]
        self.graph_issue_detail.delete("1.0", "end")
        self.graph_issue_detail.insert("end", json.dumps({
            "severity": issue.severity,
            "code": issue.code,
            "message": issue.message,
            "node_id": issue.node_id,
            "connection": issue.connection,
        }, indent=2, sort_keys=True))
        if issue.node_id in self.graph_nodes:
            self.selected_node = issue.node_id
            self._refresh_targets()
            self.redraw_graph()

    def refresh_catalog(self) -> None:
        selected = self.current.recipe_id
        self.catalog_entries.clear()
        self.catalog_tree.delete(*self.catalog_tree.get_children())
        groups: dict[str, str] = {}
        for entry in scan_catalog(self.root_path):
            group = groups.setdefault(entry.pack, self.catalog_tree.insert("", "end", text=entry.pack, open=True))
            item = self.catalog_tree.insert(group, "end", text=f"{entry.label}  [{entry.mode}]", values=(entry.key,))
            self.catalog_entries[item] = entry
            if entry.key == selected:
                self.catalog_tree.selection_set(item)
                self.catalog_tree.see(item)
        self.status.set(f"Catalog: {len(self.catalog_entries)} validated recipe(s)")

    def open_first_recipe(self) -> None:
        for item, entry in self.catalog_entries.items():
            self.catalog_tree.selection_set(item)
            self.catalog_tree.see(item)
            self.load_entry(entry)
            return

    def _catalog_selected(self, _event: object = None) -> None:
        selection = self.catalog_tree.selection()
        if selection and selection[0] in self.catalog_entries:
            self.load_entry(self.catalog_entries[selection[0]])

    def load_entry(self, entry: TupdCatalogEntry) -> None:
        self.current = load_catalog_recipe(entry)
        self.graph_nodes = list(self.current.inputs)
        self.selected_node = None
        self.sandbox.reset()
        self._sync_fields()
        self.preview_recipe()
        self.status.set(f"Loaded {entry.path.relative_to(self.root_path)}")

    def choose_recipe(self) -> None:
        path = filedialog.askopenfilename(parent=self, title="Open Tupd recipe", filetypes=(("Tupd recipe", "*.tupd"), ("JSON", "*.json"), ("All files", "*")))
        if path:
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        try:
            self.current = load_recipe(path)
        except (OSError, ValueError) as exc:
            messagebox.showerror("Open failed", str(exc), parent=self)
            return
        self.graph_nodes = list(self.current.inputs)
        self.sandbox.reset()
        self._sync_fields()
        self.preview_recipe()
        self.status.set(f"Opened {path}")

    def new_draft(self) -> None:
        self.current = TupdRecipe(
            recipe_id=f"user.tupd-draft-{int(time.time())}",
            label="New Tupd Draft",
            result=TupdResult(result_id="user.tupd-result", display_name="New Tupd Result"),
        )
        self.graph_nodes = list(self.current.inputs)
        self.sandbox.reset()
        self._sync_fields()
        self.preview_recipe()
        self.status.set("New isolated draft created")

    def _sync_fields(self) -> None:
        self.recipe_id.set(self.current.recipe_id)
        self.recipe_label.set(self.current.label)
        self.recipe_revision.set(self.current.recipe_revision)
        self.mode.set(self.current.mode)
        self.base_item_id.set(self.current.base_item_id)
        self.result_id.set(self.current.result.result_id)
        self.result_name.set(self.current.result.display_name)
        self.result_kind.set(self.current.result.result_kind)
        self.preview_shape.set(self.current.preview_shape)
        self.cost_xar.set(self.current.cost_xar)
        self.repair_percent.set(self.current.repair_percent)
        self.stability_penalty.set(self.current.stability_penalty)
        self.weight_penalty.set(self.current.weight_penalty)
        self.point_budget.set(self.current.result.point_budget)
        self._set_entry(self.result_interfaces_text, self.current.result.interfaces)
        self._set_entry(self.result_sockets_text, self.current.result.sockets)
        self._set_entry(self.result_tags_text, self.current.result.tags)
        self._set_entry(self.test_actions_text, self.current.test_actions)
        if self.test_action.get() not in self.current.test_actions:
            self.test_action.set(self.current.test_actions[0] if self.current.test_actions else "inspect")
        self.test_action_combo.configure(values=self.current.test_actions or ("inspect",))
        self._refresh_targets()
        self._refresh_connection_tree()
        self.redraw_graph()
        self._update_state_summary()

    def _refresh_targets(self) -> None:
        targets = [value for value in self.graph_nodes if value != self.selected_node]
        self.target_combo.configure(values=targets)
        if self.connection_target.get() not in targets:
            self.connection_target.set(self.current.base_item_id if self.current.base_item_id in targets else (targets[0] if targets else ""))

    def apply_fields(self) -> None:
        self.apply_fields_without_recursive_preview()
        self._sync_fields()
        self.preview_recipe()

    def apply_fields_without_recursive_preview(self) -> None:
        self.current.recipe_id = self.recipe_id.get().strip()
        self.current.label = self.recipe_label.get().strip()
        self.current.recipe_revision = self.recipe_revision.get()
        self.current.mode = self.mode.get()
        self.current.base_item_id = self.base_item_id.get().strip()
        self.current.result.result_id = self.result_id.get().strip()
        self.current.result.display_name = self.result_name.get().strip()
        self.current.result.result_kind = self.result_kind.get()
        self.current.preview_shape = self.preview_shape.get()
        self.current.cost_xar = self.cost_xar.get()
        self.current.repair_percent = self.repair_percent.get()
        self.current.stability_penalty = self.stability_penalty.get()
        self.current.weight_penalty = self.weight_penalty.get()
        self.current.result.point_budget = self.point_budget.get()
        self.current.inputs = list(self.graph_nodes)
        self.current.result.interfaces = self._csv_values(self.result_interfaces_text)
        self.current.result.sockets = self._csv_values(self.result_sockets_text)
        self.current.result.tags = self._csv_values(self.result_tags_text)
        self.current.test_actions = self._csv_values(self.test_actions_text)
        self.current.normalize()
        self.graph_report = analyze_recipe_graph(self.current)
        self.current.extensions["authoring_graph_signature"] = self.graph_report.signature
        self.current.extensions["authoring_track"] = "A8a3"
        self.graph_nodes = list(self.current.inputs)

    def apply_connection_metadata(self) -> None:
        self.apply_fields_without_recursive_preview()
        self._sync_fields()
        self.preview_recipe()
        self.status.set("Connection/result metadata applied")

    def add_palette_input(self) -> None:
        selection = self.palette.curselection()
        if not selection:
            return
        item_id, interface = PALETTE_ITEMS[selection[0]]
        definition = PART_BY_ID.get(item_id)
        if item_id not in self.graph_nodes:
            self.graph_nodes.append(item_id)
            self.current.inputs.append(item_id)
        if interface not in self.current.required_interfaces:
            self.current.required_interfaces.append(interface)
        if item_id != self.current.base_item_id and item_id not in self.current.consumed_inputs:
            self.current.consumed_inputs.append(item_id)
        self.selected_node = item_id
        if definition is not None and definition.suggested_sockets:
            self.connection_socket.set(definition.suggested_sockets[0])
        self._refresh_targets()
        self.redraw_graph()
        self.preview_recipe()

    def remove_selected_node(self) -> None:
        if not self.selected_node or self.selected_node == self.current.base_item_id:
            return
        value = self.selected_node
        self.graph_nodes = [node for node in self.graph_nodes if node != value]
        self.current.inputs = [node for node in self.current.inputs if node != value]
        self.current.consumed_inputs = [node for node in self.current.consumed_inputs if node != value]
        self.current.connections = [edge for edge in self.current.connections if not edge.startswith(value + ">") and f">{value}@" not in edge]
        self.current.forced_connections = [edge for edge in self.current.forced_connections if not edge.startswith(value + ">") and f">{value}@" not in edge]
        self.selected_node = None
        self._refresh_targets()
        self._refresh_connection_tree()
        self.preview_recipe()

    def toggle_selected_consumed(self) -> None:
        if not self.selected_node or self.selected_node == self.current.base_item_id:
            return
        if self.selected_node in self.current.consumed_inputs:
            self.current.consumed_inputs.remove(self.selected_node)
            self.status.set(f"{self.selected_node} retained by result")
        else:
            self.current.consumed_inputs.append(self.selected_node)
            self.status.set(f"{self.selected_node} consumed by transaction")
        self.redraw_graph()

    def connect_selected(self) -> None:
        source = self.selected_node
        target_id = self.connection_target.get().strip()
        socket = self.connection_socket.get().strip()
        if not source or source == target_id or not target_id or not socket:
            self.status.set("Select a source node, a different target, and a socket")
            return
        encoded = f"{source}>{target_id}@{socket}"
        target = self.current.forced_connections if self.force_connection.get() else self.current.connections
        other = self.current.connections if self.force_connection.get() else self.current.forced_connections
        if encoded not in target:
            target.append(encoded)
        if encoded in other:
            other.remove(encoded)
        if self.force_connection.get():
            self.current.mode = "forced_modification"
            self.current.stability_penalty = max(18.0, self.current.stability_penalty)
            self.current.weight_penalty = max(0.45, self.current.weight_penalty)
            if "allow_forced_connection" not in self.current.validation_rules:
                self.current.validation_rules.append("allow_forced_connection")
        self._sync_fields()
        self.preview_recipe()

    def _refresh_connection_tree(self) -> None:
        self.connection_items.clear()
        if not hasattr(self, "connection_tree"):
            return
        self.connection_tree.delete(*self.connection_tree.get_children())
        for forced, values in ((False, self.current.connections), (True, self.current.forced_connections)):
            for encoded in values:
                source, target, socket = self._parse_connection(encoded)
                item = self.connection_tree.insert("", "end", values=("FORCED" if forced else "NORMAL", source, target, socket))
                self.connection_items[item] = (forced, encoded)

    @staticmethod
    def _parse_connection(encoded: str) -> tuple[str, str, str]:
        source, _, remainder = encoded.partition(">")
        target, _, socket = remainder.partition("@")
        return source, target, socket

    def remove_selected_connection(self) -> None:
        selection = self.connection_tree.selection()
        if not selection or selection[0] not in self.connection_items:
            return
        forced, encoded = self.connection_items[selection[0]]
        values = self.current.forced_connections if forced else self.current.connections
        if encoded in values:
            values.remove(encoded)
        self._refresh_connection_tree()
        self.preview_recipe()

    def _graph_click(self, event: tk.Event) -> None:
        nearest = self.graph.find_closest(event.x, event.y)
        if not nearest:
            return
        for tag in self.graph.gettags(nearest[0]):
            if tag.startswith("node:"):
                self.selected_node = tag.split(":", 1)[1]
                self._refresh_targets()
                self.redraw_graph()
                break

    def redraw_graph(self) -> None:
        if not hasattr(self, "graph"):
            return
        import math

        self.graph.delete("all")
        # Use the real visible canvas size. A8a3 used a fictitious 640px minimum,
        # which placed nodes outside a narrow center pane even though the graph
        # was mathematically centered in that larger invisible area.
        width = max(280, self.graph.winfo_width())
        height = max(260, self.graph.winfo_height())
        info_height = 58.0
        graph_height = max(160.0, height - info_height)
        cx = width * 0.5
        cy = info_height + graph_height * 0.5
        nodes = self.graph_nodes or [self.current.base_item_id]
        positions: dict[str, tuple[float, float]] = {}
        base = self.current.base_item_id if self.current.base_item_id in nodes else nodes[0]

        # Fit node cards and their orbit to the current pane on every resize.
        node_half_width = min(108.0, max(64.0, width * 0.19))
        node_half_height = 36.0
        x_radius = max(0.0, min(225.0, cx - node_half_width - 18.0))
        y_radius = max(0.0, min(150.0, graph_height * 0.5 - node_half_height - 18.0))
        positions[base] = (cx, cy)
        others = [value for value in nodes if value != base]
        for index, item_id in enumerate(others):
            angle = (index / max(1, len(others))) * math.tau - math.pi / 2
            positions[item_id] = (cx + x_radius * math.cos(angle), cy + y_radius * math.sin(angle))

        for forced, edges in ((False, self.current.connections), (True, self.current.forced_connections)):
            for encoded in edges:
                source, target_id, socket = self._parse_connection(encoded)
                if source not in positions or target_id not in positions:
                    continue
                x0, y0 = positions[source]
                x1, y1 = positions[target_id]
                self.graph.create_line(
                    x0, y0, x1, y1,
                    fill="#e78b3f" if forced else "#40b8cf",
                    width=3 if forced else 2, arrow="last",
                )
                self.graph.create_text(
                    (x0 + x1) / 2, (y0 + y1) / 2 - 10,
                    text=("FORCED " if forced else "") + socket,
                    fill="#ffb24d" if forced else "#7dd9e8", font=("Sans", 9, "bold"),
                )

        orphan_nodes = set(self.graph_report.orphan_nodes) if self.graph_report else set()
        for item_id, (x, y) in positions.items():
            selected = item_id == self.selected_node
            base_node = item_id == base
            orphan = item_id in orphan_nodes
            fill = "#4b2020" if orphan else "#204b57" if base_node else "#18313b"
            outline = "#f2d36b" if selected else "#ef746f" if orphan else "#45d8ef" if base_node else "#6aa7b5"
            self.graph.create_rectangle(
                x - node_half_width, y - node_half_height,
                x + node_half_width, y + node_half_height,
                fill=fill, outline=outline, width=3 if selected else 2,
                tags=(f"node:{item_id}",),
            )
            short = item_id.replace("consumable.", "").replace("weapon.", "").replace("part.", "")
            max_chars = max(8, int((node_half_width * 2.0 - 18.0) / 7.2))
            if len(short) > max_chars:
                short = short[:max_chars]
            self.graph.create_text(
                x, y - 8, text=short, fill="#e6f7fb",
                font=("Sans", 10, "bold"), tags=(f"node:{item_id}",),
            )
            consumed = item_id in self.current.consumed_inputs
            label = "BASE / RETAINED" if base_node else "ORPHAN" if orphan else "consumed" if consumed else "retained"
            label_color = "#ff7f79" if orphan else "#ffbe6b" if consumed else "#7ed6a5"
            self.graph.create_text(
                x, y + 14, text=label, fill=label_color,
                font=("Sans", 9), tags=(f"node:{item_id}",),
            )

        self.graph.create_text(
            12, 12, anchor="nw",
            text=(f"{self.current.label}  r{self.current.recipe_revision}\n"
                  f"{len(nodes)} inputs · {len(self.current.connections)} normal · "
                  f"{len(self.current.forced_connections)} forced"),
            fill="#ccebf2", font=("Sans", 10, "bold"),
        )

    def preview_recipe(self) -> None:
        self.apply_fields_without_recursive_preview()
        self.graph_report = analyze_recipe_graph(self.current)
        self.preview = self.sandbox.preview(self.current)
        graph_state = "GRAPH OK" if self.graph_report.valid else f"GRAPH {self.graph_report.error_count} ERROR"
        self.graph_summary.set(
            f"{graph_state} · {'PREVIEW VALID' if self.preview.valid else 'PREVIEW BLOCKED'} · stability {self.preview.stability_percent:.0f}%"
        )
        payload = {
            "preview": asdict(self.preview),
            "comparison": asdict(self.preview.comparison()),
            "test_inventory": self._inventory_payload(),
            "graph_report": {
                "valid": self.graph_report.valid,
                "errors": self.graph_report.error_count,
                "warnings": self.graph_report.warning_count,
                "orphans": self.graph_report.orphan_nodes,
                "suggested_connections": self.graph_report.suggested_connections,
                "signature": self.graph_report.signature,
            },
            "assembly": {
                "base_item": self.current.base_item_id,
                "inputs": self.current.inputs,
                "consumed_inputs": self.current.consumed_inputs,
                "connections": self.current.connections,
                "forced_connections": self.current.forced_connections,
                "result_sockets": self.current.result.sockets,
                "test_actions": self.current.test_actions,
            },
        }
        self._write_evidence(json.dumps(payload, indent=2, sort_keys=True))
        self._update_comparison()
        self._refresh_graph_report()
        self._update_state_summary()
        self.redraw_graph()
        ready = self.preview.valid and self.graph_report.valid
        self.guide_step.set("STEP 4 — Graph and preview are valid; Commit Sandbox next" if ready else "STEP 3/4 — Resolve graph or preview issues before committing")

    def _inventory_payload(self) -> dict[str, object]:
        inv = self.sandbox.inventory
        return {
            "xar": inv.xar,
            "weapon_condition": inv.weapon_condition,
            "weapon_weight": inv.weapon_weight,
            "tupd_tape": inv.items.get("consumable.tupd-tape", 0),
            "normal_save_unchanged": self.sandbox.normal_save_unchanged,
        }

    def _update_comparison(self) -> None:
        self.comparison.delete(*self.comparison.get_children())
        rows = (
            ("Condition", f"{self.preview.condition_before:.0f}%", f"{self.preview.condition_after:.0f}%"),
            ("Weight", f"{self.preview.weight_before:.2f}", f"{self.preview.weight_after:.2f}"),
            ("Stability", "100%", f"{self.preview.stability_percent:.0f}%"),
            ("Point budget", "base", str(self.preview.point_budget)),
            ("Interfaces", "existing", ", ".join(self.preview.added_interfaces) or "none"),
            ("Sockets", "existing", ", ".join(self.preview.added_sockets) or "none"),
            ("Connections", "0", f"{self.preview.connection_count} normal / {self.preview.forced_connection_count} forced"),
        )
        for property_name, before, after in rows:
            self.comparison.insert("", "end", text=property_name, values=(before, after))

    def commit_sandbox(self) -> None:
        self.apply_fields_without_recursive_preview()
        receipt = self.sandbox.commit(self.current)
        self.preview = self.sandbox.last_preview
        payload = {
            "receipt": asdict(receipt),
            "preview": asdict(self.preview),
            "result_instance": asdict(self.sandbox.result_instance) if self.sandbox.result_instance else None,
            "normal_save_unchanged": self.sandbox.normal_save_unchanged,
            "remaining_inventory": self.sandbox.inventory.items,
            "important": "A committed result is not equipped or spawned until the next explicit step.",
        }
        self._write_evidence(json.dumps(payload, indent=2, sort_keys=True))
        if receipt.committed:
            self.status.set("Sandbox committed; result created but NOT equipped/spawned")
            self.guide_step.set("STEP 6 — Commit succeeded. Press Equip / Spawn Result")
        else:
            self.status.set("Commit rejected; no inputs consumed")
            self.guide_step.set("STEP 4 — Fix validation; failed commit consumed nothing")
        self._update_state_summary()

    def equip_result(self) -> None:
        if not self.sandbox.equip_or_spawn():
            self.status.set("No committed result. Preview and Commit Sandbox first")
            self.guide_step.set("STEP 5 — Commit a valid recipe before equipping/spawning")
            return
        instance = self.sandbox.result_instance
        assert instance is not None
        self.status.set(f"Sandbox result {instance.state.lower()}; live weapon and normal save unchanged")
        self.guide_step.set("STEP 7 — Choose a declared action and press Test Result")
        self._write_evidence(json.dumps({
            "result_instance": asdict(instance),
            "state": instance.state,
            "normal_save_unchanged": self.sandbox.normal_save_unchanged,
        }, indent=2, sort_keys=True))
        self._update_state_summary()

    def test_result(self) -> None:
        test = self.sandbox.test_result(self.test_action.get())
        self.status.set(("Test passed: " if test.accepted else "Test blocked: ") + test.outcome)
        self.guide_step.set("STEP 8 — Export & Reload the tested result" if test.accepted else "STEP 7 — Select a declared action or equip/spawn first")
        self._write_evidence(json.dumps({
            "test": asdict(test),
            "result_instance": asdict(self.sandbox.result_instance) if self.sandbox.result_instance else None,
            "normal_save_unchanged": self.sandbox.normal_save_unchanged,
        }, indent=2, sort_keys=True))
        self._update_state_summary()

    def clear_result(self) -> None:
        self.sandbox.clear_result()
        self.status.set("Sandbox result cleared; committed recipe draft remains")
        self.guide_step.set("STEP 5 — Commit again to create a fresh result instance")
        self._update_state_summary()

    def _update_state_summary(self) -> None:
        inv = self.sandbox.inventory
        self.inventory_summary.set(
            f"Sandbox: {inv.xar} XAR · {inv.items.get('consumable.tupd-tape', 0)} Tupd Tape · condition {inv.weapon_condition:.0f}% · normal save {'unchanged' if self.sandbox.normal_save_unchanged else 'ERROR'}"
        )
        instance = self.sandbox.result_instance
        if instance is None:
            self.result_state_summary.set("RESULT STATE: NO COMMITTED RESULT")
        else:
            self.result_state_summary.set(
                f"RESULT STATE: {instance.state} · tests {instance.test_count} · last {instance.last_action or 'none'}"
            )

    def reset_sandbox(self) -> None:
        self.sandbox.reset()
        self.preview_recipe()
        self.status.set("Sandbox reset; normal save was never opened")
        self.guide_step.set("STEP 4 — Preview, then commit the fresh sandbox")

    def launch_native(self) -> None:
        self.apply_fields_without_recursive_preview()
        draft_dir = self.root_path / "user_data" / "studio" / "tupd_drafts"
        draft_path = save_recipe_atomic(draft_dir / "current_workbench.tupd", self.current)
        script = self.root_path / "scripts" / "launch_tupd_native.sh"
        try:
            subprocess.Popen([str(script), str(draft_path)], cwd=self.root_path)
            self.status.set("Opening native Tupd A8a3r1 world-space inspection stage")
        except OSError as exc:
            messagebox.showerror("Native stage failed", str(exc), parent=self)

    def export_current(self) -> None:
        self.preview_recipe()
        if not self.graph_report.valid:
            messagebox.showwarning("Graph blocked", f"Resolve {self.graph_report.error_count} graph error(s) before export. No sandbox or normal-save data were changed.", parent=self)
            self.notebook.select(2)
            return
        if not self.preview.valid:
            messagebox.showwarning("Validation blocked", "The recipe must pass Preview before export. No inputs or normal save data were changed.", parent=self)
            return
        if self.sandbox.result_instance is None:
            messagebox.showwarning("No committed result", "Commit Sandbox first. A8a3r1 exports a concrete result instance so it can be indexed, reloaded, and spawned.", parent=self)
            return
        try:
            destination = export_managed_recipe(
                self.current,
                self.preview,
                self.root_path,
                self.sandbox.result_instance,
                self.sandbox.test_history,
            )
            recipe_path = next(destination.glob("*.tupd"))
            self.open_path(recipe_path)
            self.refresh_catalog()
            self.status.set(f"Exported and reloaded tested package {destination.relative_to(self.root_path)}")
            self.guide_step.set("COMPLETE — Managed recipe and .tupdinstance reloaded through content/user")
        except (OSError, ValueError) as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)

    def asset_doctor(self) -> None:
        report = scan_content(self.root_path / "content")
        self.status.set(f"Asset Doctor: {report.valid_count} valid · {report.error_count} errors · {report.warning_count} warnings")
        self._write_evidence(json.dumps(report.to_dict()["summary"], indent=2, sort_keys=True))


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="SignalCloud Tupd Workbench")
    parser.add_argument("initial", nargs="?")
    parser.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    initial = Path(args.initial).resolve() if args.initial else None
    app = TupdWorkbenchApp(Path(args.root), initial)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
