from __future__ import annotations

import copy
import math
import string
import tkinter as tk
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .brush_editor import PREMADES, SimpleBrush, SimpleBrushEditor
from .color_dialog import ask_point_color
from .font_import_dialog import FontImportDialog
from .font_importer import probe_font
from .help_reader import HelpReader
from .model import (
    FontDocument, GlyphClipboard, Layer, Point, copy_glyph_snapshot,
    current_engine_font, paste_glyph_snapshot,
)
from .render_preview import RenderPreviewWindow
from .unicode_catalog import (
    EmojiEntry, load_custom_unicode, load_emoji_catalog, save_custom_unicode,
)

BG = "#0a1014"
PANEL = "#111b21"
GRID = "#263942"
GRID_MAJOR = "#3b5865"
CYAN = "#45d8ef"
GOLD = "#f0bb45"
TEXT = "#d7e9ed"
MUTED = "#78929b"

GROUPS = [
    ("Upper", string.ascii_uppercase), ("Lower", string.ascii_lowercase),
    ("Numbers", string.digits), ("Punctuation", string.punctuation),
    ("Latin", "ÀÁÂÃÄÅÆÇÈÉÊËÌÍÎÏÑÒÓÔÕÖØÙÚÛÜÝß"),
]
TOOLS = [
    ("dot", "• Dot"), ("line", "╱ Line"), ("brush", "◉ 3D Brush"),
    ("fill", "▣ Fill"), ("eraser", "⌫ Eraser"), ("select", "▱ Select"),
    ("wand", "✦ Magic Wand"),
]


@dataclass
class HistoryEntry:
    label: str
    before: FontDocument
    after: FontDocument
    muted: bool = False


def point_identity(point: Point) -> tuple[float, float, float, str, int]:
    return (*point.key(), point.color.lower(), point.group)


class ScfsEditor(ttk.Frame):
    def __init__(self, master: tk.Misc, root_path: Path) -> None:
        super().__init__(master)
        self.root_path = Path(root_path)
        self.document = current_engine_font()
        self.path: Path | None = None
        self.codepoint = ord("A")
        self.layer_index = 0
        self.tool = tk.StringVar(value="dot")
        self.view = tk.StringVar(value="XY")
        self.depth = tk.DoubleVar(value=0.0)
        self.brush_radius = tk.IntVar(value=0)
        self.point_alpha = tk.DoubleVar(value=1.0)
        self.point_color = tk.StringVar(value=CYAN)
        self.font_name = tk.StringVar(value=self.document.name)
        self.advance = tk.DoubleVar(value=5.8)
        self.preview_text = tk.StringVar(value="ALMOND SIGNAL\nLive Tape 0123!?")
        self.status = tk.StringVar(value="Legacy engine alphabet imported — select a character to begin.")
        self.layer_opacity = tk.DoubleVar(value=1.0)
        self.layer_visible = tk.BooleanVar(value=True)
        self.selected_cells: set[tuple[int, int]] = set()
        self.drag_start: tuple[int, int] | None = None
        self.last_drag_cell: tuple[int, int] | None = None
        self._gesture_before: FontDocument | None = None
        self._clipboard: GlyphClipboard | None = None
        self.history_base = self.document.clone()
        self.history: list[HistoryEntry] = []
        self.history_cursor = 0
        self._history_busy = False
        self._right_hold_job: str | None = None
        self._wand_move_active = False
        self._wand_move_last: tuple[int, int] | None = None
        self._alpha_hide_job: str | None = None
        self._advance_job: str | None = None
        self.simple_brush = SimpleBrush.load_from(PREMADES["Single Dot"])
        self.brush_editor_visible = False
        self.custom_unicode_path = self.root_path / "user_data" / "scfs" / "custom_unicode.json"
        self.color_slots_path = self.root_path / "user_data" / "scfs" / "color_slots.json"
        self.custom_codepoints = load_custom_unicode(self.custom_unicode_path)
        self.emoji_entries = load_emoji_catalog(self.root_path / "current.emoji")
        self._build()
        self._bind()
        self.refresh()

    @property
    def glyph(self) -> Glyph:
        return self.document.ensure_glyph(self.codepoint)

    @property
    def layer(self) -> Layer:
        if not self.glyph.layers:
            self.glyph.layers.append(Layer())
        self.layer_index = max(0, min(self.layer_index, len(self.glyph.layers) - 1))
        return self.glyph.layers[self.layer_index]

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(3, weight=1)
        self.configure(padding=8)

        title = ttk.Frame(self)
        title.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        ttk.Label(title, text="+SCFS+", font=("Sans", 18, "bold")).pack(side="left")
        ttk.Label(title, text="  SIGNALCLOUD FONT STUDIO  •  ALPHA A1R4", foreground=MUTED).pack(side="left")
        ttk.Label(title, textvariable=self.status, anchor="e").pack(side="right", fill="x", expand=True)

        menu = ttk.Frame(self)
        menu.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(0, 4))
        for label, command in [
            ("New", self.new), ("Open", self.open), ("Import Font", self.import_font), ("Save", self.save),
            ("Save As", self.save_as), ("Export", self.export_report),
            ("Undo", self.undo), ("Redo", self.redo), ("Validate", self.validate),
            ("Help", self.open_help),
        ]:
            ttk.Button(menu, text=label, command=command).pack(side="left", padx=(0, 3))
        ttk.Label(menu, text="Font name").pack(side="left", padx=(12, 4))
        name = ttk.Entry(menu, textvariable=self.font_name, width=28)
        name.pack(side="left")
        name.bind("<FocusOut>", lambda _e: self.change_name())

        selector = ttk.Frame(self)
        selector.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(0, 5))
        selector_top = ttk.Frame(selector)
        selector_top.pack(fill="x")
        self.group_notebook = ttk.Notebook(selector)
        self.group_notebook.pack(in_=selector_top, side="left", fill="x", expand=True)
        self.brush_toggle = ttk.Button(
            selector_top, text="Edit\n 3D \nBrush",
            command=self.toggle_brush_editor, width=7,
        )
        self.brush_toggle.pack(side="right", fill="y", padx=(5, 0))
        for name, chars in GROUPS:
            frame = ttk.Frame(self.group_notebook, padding=3)
            self.group_notebook.add(frame, text=name)
            for i, char in enumerate(chars):
                ttk.Button(frame, text=char, width=3, command=lambda c=char: self.select_char(c)).grid(
                    row=i // 26, column=i % 26, padx=1, pady=1
                )
        custom = ttk.Frame(self.group_notebook, padding=4)
        self.group_notebook.add(custom, text="Custom / Unicode")
        ttk.Label(custom, text="Character or U+ code").pack(side="left")
        self.unicode_entry = ttk.Entry(custom, width=16)
        self.unicode_entry.pack(side="left", padx=4)
        ttk.Button(custom, text="Open glyph", command=self.open_unicode).pack(side="left")
        ttk.Button(custom, text="Store Custom", command=self.store_custom_unicode).pack(side="left", padx=(3, 0))

        self.custom_store_frame = ttk.Frame(self.group_notebook, padding=4)
        self.group_notebook.add(self.custom_store_frame, text="Created Unicode")
        self.emoji_frame = ttk.Frame(self.group_notebook, padding=4)
        self.group_notebook.add(self.emoji_frame, text="Emoji")
        self.refresh_custom_tab()
        self.refresh_emoji_tab()

        self.brush_host = ttk.LabelFrame(
            selector, text="Simple single-layer +SCFS+ 3D brush", padding=2,
        )
        self.brush_editor = SimpleBrushEditor(
            self.brush_host, self.root_path, self.simple_brush, self.apply_simple_brush,
        )
        self.brush_editor.pack(fill="x")

        left = ttk.LabelFrame(self, text="Tools", padding=6)
        left.grid(row=3, column=0, sticky="ns", padx=(0, 5))
        for key, label in TOOLS:
            ttk.Radiobutton(left, text=label, value=key, variable=self.tool).pack(fill="x", pady=1)
        ttk.Separator(left).pack(fill="x", pady=7)
        ttk.Label(left, text="Brush / eraser radius").pack(anchor="w")
        ttk.Spinbox(left, from_=0, to=6, textvariable=self.brush_radius, width=8).pack(anchor="w")
        ttk.Label(left, text="Point depth (Z)", padding=(0, 6, 0, 0)).pack(anchor="w")
        ttk.Spinbox(left, from_=-16, to=16, increment=.25, textvariable=self.depth, width=8).pack(anchor="w")
        ttk.Label(left, text="Point alpha", padding=(0, 6, 0, 0)).pack(anchor="w")
        self.alpha_box = ttk.Frame(left, height=42)
        self.alpha_box.pack(fill="x")
        self.alpha_box.pack_propagate(False)
        self.alpha_scale = ttk.Scale(
            self.alpha_box, from_=0.05, to=1, variable=self.point_alpha,
            orient="horizontal", command=self.change_point_alpha,
        )
        self.alpha_scale.pack(side="bottom", fill="x")
        self.alpha_popup = tk.Label(
            self.alpha_box, text="1.00", bg="#eefcff", fg="#102127",
            bd=1, relief="solid", padx=4, pady=1,
        )
        self.alpha_scale.bind("<ButtonPress-1>", lambda _e: self.show_alpha_popup())
        self.alpha_scale.bind("<B1-Motion>", lambda _e: self.show_alpha_popup())
        self.alpha_scale.bind("<ButtonRelease-1>", lambda _e: self.hide_alpha_popup_later())
        ttk.Button(left, text="Point color", command=self.choose_color).pack(fill="x", pady=(7, 0))
        ttk.Separator(left).pack(fill="x", pady=7)
        ttk.Button(left, text="Clear layer", command=self.clear_layer).pack(fill="x")
        ttk.Button(left, text="Copy glyph", command=self.copy_glyph).pack(fill="x", pady=2)
        ttk.Button(left, text="Paste glyph", command=self.paste_glyph).pack(fill="x")
        ttk.Button(left, text="Exp glyph", command=self.load_legacy_example).pack(fill="x", pady=(2, 0))
        ttk.Button(left, text="Render", command=self.open_render_preview).pack(fill="x", pady=(2, 0))

        center = ttk.Frame(self)
        center.grid(row=3, column=1, sticky="nsew")
        center.columnconfigure(0, weight=1)
        center.rowconfigure(1, weight=1)
        controls = ttk.Frame(center)
        controls.grid(row=0, column=0, sticky="ew")
        self.glyph_title = ttk.Label(controls, font=("Sans", 12, "bold"))
        self.glyph_title.pack(side="left")
        ttk.Label(controls, text="Advance").pack(side="left", padx=(14, 3))
        self.advance_input = ttk.Spinbox(
            controls, from_=0, to=64, increment=.25, textvariable=self.advance,
            width=7, command=self.schedule_advance,
        )
        self.advance_input.pack(side="left")
        self.advance_input.bind("<KeyRelease>", lambda _e: self.schedule_advance())
        self.advance_input.bind("<ButtonRelease-1>", lambda _e: self.schedule_advance())
        self.advance_input.bind("<FocusOut>", lambda _e: self.schedule_advance())
        ttk.Label(controls, text="Projection").pack(side="left", padx=(14, 3))
        for value in ("XY", "XZ", "YZ"):
            ttk.Radiobutton(
                controls, text=value, value=value, variable=self.view,
                command=self.projection_changed,
            ).pack(side="left")
        ttk.Label(controls, text="  Advance = next character start", foreground=MUTED).pack(side="right")

        self.vertical_panes = ttk.Panedwindow(center, orient="vertical")
        self.vertical_panes.grid(row=1, column=0, sticky="nsew", pady=(3, 0))
        canvas_box = ttk.Frame(self.vertical_panes)
        canvas_box.columnconfigure(0, weight=1)
        canvas_box.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(canvas_box, bg=BG, highlightthickness=0, width=760, height=520)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        xbar = ttk.Scrollbar(canvas_box, orient="horizontal", command=self.canvas.xview)
        ybar = ttk.Scrollbar(canvas_box, orient="vertical", command=self.canvas.yview)
        xbar.grid(row=1, column=0, sticky="ew")
        ybar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(xscrollcommand=xbar.set, yscrollcommand=ybar.set)
        self.vertical_panes.add(canvas_box, weight=4)

        preview = ttk.LabelFrame(self.vertical_panes, text="Rich / simple text preview — drag divider to resize", padding=5)
        preview.columnconfigure(1, weight=1)
        preview.rowconfigure(1, weight=1)
        ttk.Label(preview, text="Text").grid(row=0, column=0, padx=(0, 4))
        entry = ttk.Entry(preview, textvariable=self.preview_text)
        entry.grid(row=0, column=1, sticky="ew")
        entry.bind("<KeyRelease>", lambda _e: self.refresh_preview())
        self.preview = tk.Canvas(preview, bg="#071014", height=120, highlightthickness=0)
        self.preview.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(4, 0))
        preview_scroll = ttk.Scrollbar(preview, orient="vertical", command=self.preview.yview)
        preview_scroll.grid(row=1, column=2, sticky="ns", pady=(4, 0))
        self.preview.configure(yscrollcommand=preview_scroll.set)
        self.preview.bind("<Configure>", lambda _e: self.refresh_preview())
        self.vertical_panes.add(preview, weight=1)

        right = ttk.Frame(self, width=270)
        right.grid(row=3, column=2, sticky="ns", padx=(5, 0))
        layers = ttk.LabelFrame(right, text="Workspace layers & opacity", padding=5)
        layers.pack(fill="both", expand=True)
        self.layer_list = tk.Listbox(layers, height=10, exportselection=False, bg=PANEL, fg=TEXT)
        self.layer_list.pack(fill="both", expand=True)
        self.layer_list.bind("<<ListboxSelect>>", self.select_layer)
        row = ttk.Frame(layers)
        row.pack(fill="x", pady=3)
        ttk.Button(row, text="+", width=3, command=self.add_layer).pack(side="left")
        ttk.Button(row, text="−", width=3, command=self.delete_layer).pack(side="left")
        ttk.Button(row, text="↑", width=3, command=lambda: self.move_layer(-1)).pack(side="left")
        ttk.Button(row, text="↓", width=3, command=lambda: self.move_layer(1)).pack(side="left")
        ttk.Button(row, text="Rename", command=self.rename_layer).pack(side="left")
        ttk.Label(layers, text="Active layer opacity").pack(anchor="w")
        ttk.Scale(
            layers, from_=0, to=1, variable=self.layer_opacity,
            command=self.change_layer_opacity,
        ).pack(fill="x")
        ttk.Checkbutton(
            layers, text="Visible", variable=self.layer_visible,
            command=self.toggle_layer_visibility,
        ).pack(anchor="w")

        history = ttk.LabelFrame(right, text="History — click to hold in purgatory", padding=5)
        history.pack(fill="both", expand=True, pady=(5, 0))
        self.history_tree = ttk.Treeview(
            history, columns=("action",), show="tree", height=10,
            style="History.Treeview",
        )
        self.history_tree.pack(fill="both", expand=True)
        self.history_tree.bind("<Button-1>", self.history_click)
        self.history_tree.bind("<Button-3>", self.history_menu)
        self.history_context = tk.Menu(self, tearoff=False)
        self.history_context.add_command(label="Toggle purgatory", command=self.history_toggle_selected)
        self.history_context.add_command(label="Delete history record", command=self.history_delete_selected)
        ttk.Label(
            history,
            text="Italic + strikeout = hidden action held in purgatory.",
            foreground=MUTED, wraplength=240,
        ).pack(fill="x")

        self.selection_menu = tk.Menu(self, tearoff=False)
        self.selection_menu.add_command(label="Group", command=self.group_selection)
        self.selection_menu.add_command(label="Erase", command=self.erase_selection)
        self.selection_menu.add_command(label="Fill Empty", command=self.fill_selection)
        self.selection_menu.add_separator()
        self.selection_menu.add_command(label="De-Select", command=self.clear_selection)

    def _bind(self) -> None:
        self.canvas.bind("<Configure>", lambda _e: self.refresh_canvas())
        self.canvas.bind("<Button-1>", self.pointer_down)
        self.canvas.bind("<B1-Motion>", self.pointer_drag)
        self.canvas.bind("<ButtonRelease-1>", self.pointer_up)
        self.canvas.bind("<Double-Button-1>", self.double_left)
        self.canvas.bind("<ButtonPress-3>", self.right_down)
        self.canvas.bind("<B3-Motion>", self.right_drag)
        self.canvas.bind("<ButtonRelease-3>", self.right_up)
        self.canvas.bind("<Double-Button-3>", self.double_right)
        self.master.bind("<Control-s>", lambda _e: self.save())
        self.master.bind("<Control-z>", lambda _e: self.undo())
        self.master.bind("<Control-y>", lambda _e: self.redo())
        self.master.bind("<F1>", lambda _e: self.open_help())
        self.master.bind_all("<ButtonPress>", self.global_pointer_press, add="+")

    def global_pointer_press(self, event: tk.Event) -> None:
        if self._advance_job is not None and event.widget is not self.advance_input:
            self.commit_advance()

    # ----- history -----

    def begin_action(self) -> None:
        self._gesture_before = self.document.clone()

    def record_action(self, label: str) -> None:
        before = self._gesture_before or self.document.clone()
        self._gesture_before = None
        if before == self.document:
            return
        if self.history_cursor < len(self.history):
            self.history = self.history[:self.history_cursor]
        self.history.append(HistoryEntry(label, before, self.document.clone()))
        if len(self.history) > 80:
            self.history_base = self.history[0].after.clone()
            self.history.pop(0)
        self.history_cursor = len(self.history)
        self.refresh_history()

    def undo(self) -> None:
        while self.history_cursor > 0:
            self.history_cursor -= 1
            entry = self.history[self.history_cursor]
            if entry.muted:
                continue
            self.document = entry.before.clone()
            self.font_name.set(self.document.name)
            self.clear_selection()
            self.refresh()
            break

    def redo(self) -> None:
        while self.history_cursor < len(self.history):
            entry = self.history[self.history_cursor]
            self.history_cursor += 1
            if entry.muted:
                continue
            self.document = entry.after.clone()
            self.font_name.set(self.document.name)
            self.clear_selection()
            self.refresh()
            break

    def refresh_history(self) -> None:
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        normal_font = ("Sans", 9)
        muted_font = ("Sans", 9, "italic", "overstrike")
        self.history_tree.tag_configure("normal", font=normal_font)
        self.history_tree.tag_configure("muted", font=muted_font, foreground=MUTED)
        self.history_tree.tag_configure("future", foreground="#59676c")
        for index, entry in enumerate(self.history):
            prefix = "▶ " if index == self.history_cursor - 1 else "  "
            tags = ["muted" if entry.muted else "normal"]
            if index >= self.history_cursor:
                tags.append("future")
            self.history_tree.insert("", "end", iid=str(index), text=prefix + entry.label, tags=tags)
        if self.history:
            self.history_tree.see(str(min(len(self.history)-1, max(0, self.history_cursor-1))))

    def _apply_entry_delta(self, entry: HistoryEntry, forward: bool) -> None:
        source, target = (entry.before, entry.after) if forward else (entry.after, entry.before)
        if source.name != target.name and self.document.name == source.name:
            self.document.name = target.name
        if source.metrics != target.metrics and self.document.metrics == source.metrics:
            self.document.metrics = copy.deepcopy(target.metrics)
        codes = set(source.glyphs) | set(target.glyphs)
        for code in codes:
            old, new = source.glyphs.get(code), target.glyphs.get(code)
            current = self.document.glyphs.get(code)
            if old is None and new is not None:
                if forward:
                    self.document.glyphs[code] = copy.deepcopy(new)
                elif current == new:
                    self.document.glyphs.pop(code, None)
                continue
            if old is not None and new is None:
                if forward:
                    self.document.glyphs.pop(code, None)
                elif current is None:
                    self.document.glyphs[code] = copy.deepcopy(old)
                continue
            if old is None or new is None:
                continue
            if current is None:
                self.document.glyphs[code] = copy.deepcopy(new)
                continue
            if old.advance != new.advance and current.advance == old.advance:
                current.advance = new.advance
            common = min(len(old.layers), len(new.layers), len(current.layers))
            for index in range(common):
                old_layer, new_layer, active = old.layers[index], new.layers[index], current.layers[index]
                if old_layer.name != new_layer.name and active.name == old_layer.name:
                    active.name = new_layer.name
                if old_layer.opacity != new_layer.opacity and active.opacity == old_layer.opacity:
                    active.opacity = new_layer.opacity
                if old_layer.visible != new_layer.visible and active.visible == old_layer.visible:
                    active.visible = new_layer.visible
                old_map = {point_identity(p): p for p in old_layer.points}
                new_map = {point_identity(p): p for p in new_layer.points}
                active_map = {point_identity(p): p for p in active.points}
                removed = set(old_map) - set(new_map)
                added = set(new_map) - set(old_map)
                active.points[:] = [p for p in active.points if point_identity(p) not in removed]
                for key in added:
                    if key not in active_map:
                        active.points.append(copy.deepcopy(new_map[key]))
            if len(new.layers) > len(old.layers):
                for layer in new.layers[len(old.layers):]:
                    if forward and not any(item.name == layer.name for item in current.layers):
                        current.layers.append(copy.deepcopy(layer))
                    elif not forward:
                        current.layers[:] = [item for item in current.layers if item.name != layer.name]
            elif len(new.layers) < len(old.layers):
                removed_layers = old.layers[len(new.layers):]
                if forward:
                    names = {layer.name for layer in removed_layers}
                    current.layers[:] = [item for item in current.layers if item.name not in names]
                else:
                    current.layers.extend(copy.deepcopy(removed_layers))

    def history_click(self, event: tk.Event) -> str:
        iid = self.history_tree.identify_row(event.y)
        if iid:
            self.history_tree.selection_set(iid)
            self.toggle_history(int(iid))
        return "break"

    def history_menu(self, event: tk.Event) -> str:
        iid = self.history_tree.identify_row(event.y)
        if iid:
            self.history_tree.selection_set(iid)
            self.history_context.tk_popup(event.x_root, event.y_root)
        return "break"

    def history_toggle_selected(self) -> None:
        selected = self.history_tree.selection()
        if selected:
            self.toggle_history(int(selected[0]))

    def toggle_history(self, index: int) -> None:
        if not 0 <= index < len(self.history):
            return
        entry = self.history[index]
        self._apply_entry_delta(entry, forward=entry.muted)
        entry.muted = not entry.muted
        self.font_name.set(self.document.name)
        self.status.set(
            f"{entry.label} {'held in purgatory' if entry.muted else 'restored from purgatory'}."
        )
        self.refresh()

    def history_delete_selected(self) -> None:
        selected = self.history_tree.selection()
        if not selected:
            return
        index = int(selected[0])
        entry = self.history[index]
        if not entry.muted:
            self._apply_entry_delta(entry, forward=False)
        del self.history[index]
        self.history_cursor = min(self.history_cursor, len(self.history))
        self.status.set(f"Deleted history record: {entry.label}")
        self.refresh()

    # ----- document / glyph -----

    def select_char(self, char: str) -> None:
        self.commit_advance()
        self.codepoint = ord(char)
        self.layer_index = 0
        self.selected_cells.clear()
        self.refresh()

    def unicode_entry_codepoint(self) -> int | None:
        text = self.unicode_entry.get().strip()
        try:
            code = (
                int(text[2:], 16) if text.upper().startswith("U+")
                else (ord(text) if len(text) == 1 else int(text, 0))
            )
            if not 0 <= code <= 0x10FFFF:
                raise ValueError
            return code
        except ValueError:
            messagebox.showerror(
                "+SCFS+", "Enter one character, U+1F600, or a numeric codepoint.",
            )
            return None

    def open_unicode(self) -> None:
        self.commit_advance()
        code = self.unicode_entry_codepoint()
        if code is None:
            return
        self.codepoint = code
        self.layer_index = 0
        self.selected_cells.clear()
        self.refresh()

    def store_custom_unicode(self) -> None:
        self.commit_advance()
        code = self.unicode_entry_codepoint()
        if code is None:
            return
        if code not in self.custom_codepoints:
            self.custom_codepoints.append(code)
            save_custom_unicode(self.custom_unicode_path, self.custom_codepoints)
        self.refresh_custom_tab()
        self.codepoint = code
        self.layer_index = 0
        self.selected_cells.clear()
        self.status.set(f"Stored {chr(code)} · U+{code:04X} in Created Unicode.")
        self.refresh()

    @staticmethod
    def clear_frame(frame: tk.Misc) -> None:
        for child in frame.winfo_children():
            child.destroy()

    def refresh_custom_tab(self) -> None:
        self.clear_frame(self.custom_store_frame)
        if not self.custom_codepoints:
            ttk.Label(
                self.custom_store_frame,
                text="Use Custom / Unicode → Store Custom to keep characters here.",
                foreground=MUTED,
            ).pack(anchor="w")
            return
        for index, code in enumerate(self.custom_codepoints):
            char = chr(code)
            ttk.Button(
                self.custom_store_frame, text=char, width=4,
                command=lambda c=char: self.select_char(c),
            ).grid(row=index//24, column=index%24, padx=1, pady=1)

    def refresh_emoji_tab(self) -> None:
        self.clear_frame(self.emoji_frame)
        if not self.emoji_entries:
            ttk.Label(
                self.emoji_frame,
                text="No entries found in current.emoji. Plain lists and forgiving JSON are accepted.",
                foreground=MUTED,
            ).pack(anchor="w")
            return
        for index, entry in enumerate(self.emoji_entries):
            button = ttk.Button(
                self.emoji_frame, text=entry.emoji, width=4,
                command=lambda item=entry: self.open_emoji(item),
            )
            button.grid(row=index//24, column=index%24, padx=1, pady=1)

    def open_emoji(self, entry: EmojiEntry) -> None:
        self.commit_advance()
        self.codepoint = ord(entry.emoji)
        self.layer_index = 0
        self.selected_cells.clear()
        details = entry.name + (f" · {entry.category}" if entry.category else "")
        self.status.set(f"Emoji {entry.emoji} · {details}")
        self.refresh()

    def toggle_brush_editor(self) -> None:
        self.brush_editor_visible = not self.brush_editor_visible
        if self.brush_editor_visible:
            self.brush_host.pack(fill="x", pady=(4, 0))
            self.brush_toggle.configure(text="Hide\n 3D \nBrush")
        else:
            self.brush_host.pack_forget()
            self.brush_toggle.configure(text="Edit\n 3D \nBrush")

    def apply_simple_brush(self, brush: SimpleBrush) -> None:
        self.simple_brush = SimpleBrush.load_from(brush)
        self.brush_radius.set(max(0, max(brush.width, brush.height)//2))
        self.tool.set("brush")
        self.status.set(
            f"Applied simple 3D brush: {brush.name} · {len(brush.active_pixels())} active cells."
        )

    def open_render_preview(self) -> None:
        self.commit_advance()
        RenderPreviewWindow(self, self.document, self.preview_text.get(), self.root_path)

    def projection_changed(self) -> None:
        self.selected_cells.clear()
        self.refresh_canvas()

    def refresh(self) -> None:
        char = chr(self.codepoint)
        self.glyph_title.configure(text=f"{char if char.isprintable() else 'control'}   U+{self.codepoint:04X}")
        self.advance.set(self.glyph.advance)
        self.layer_list.delete(0, "end")
        for layer in self.glyph.layers:
            self.layer_list.insert(
                "end",
                f"{'●' if layer.visible else '○'} {layer.name}  ({len(layer.points)} pts) [{layer.opacity:.2f}]",
            )
        if self.glyph.layers:
            self.layer_list.selection_clear(0, "end")
            self.layer_list.selection_set(self.layer_index)
            self.layer_list.activate(self.layer_index)
            self.layer_list.see(self.layer_index)
            self.sync_active_layer_controls()
        self.refresh_canvas()
        self.refresh_preview()
        self.refresh_history()

    def sync_active_layer_controls(self) -> None:
        self.layer_opacity.set(self.layer.opacity)
        self.layer_visible.set(self.layer.visible)

    # ----- canvas / selection -----

    @staticmethod
    def _canvas_geometry() -> tuple[float, float, float]:
        return 58.0, 90.0, 42.0

    def _project(self, point: Point) -> tuple[float, float]:
        if self.view.get() == "XY":
            return point.x, point.y
        if self.view.get() == "XZ":
            return point.x, point.z
        return point.z, point.y

    def _unproject(self, gx: float, gy: float) -> Point:
        values = {
            "XY": (gx, gy, self.depth.get()),
            "XZ": (gx, self.depth.get(), gy),
            "YZ": (self.depth.get(), gy, gx),
        }[self.view.get()]
        return Point(*values, self.point_alpha.get(), self.point_color.get().lower())

    def point_cell(self, point: Point) -> tuple[int, int]:
        gx, gy = self._project(point)
        return round(gx), round(gy)

    def points_in_selection(self) -> list[Point]:
        return [point for point in self.layer.points if self.point_cell(point) in self.selected_cells]

    def refresh_canvas(self) -> None:
        self.canvas.delete("all")
        width = max(600, self.canvas.winfo_width())
        height = max(420, self.canvas.winfo_height())
        cell, ox, oy = self._canvas_geometry()
        self.canvas.configure(scrollregion=(0, 0, max(width, 1250), max(height, 900)))
        for i in range(-16, 33):
            x = ox + i * cell
            self.canvas.create_line(x, 0, x, 900, fill=GRID_MAJOR if i == 0 else GRID)
        for i in range(-8, 25):
            y = oy + i * cell
            self.canvas.create_line(0, y, 1250, y, fill=GRID_MAJOR if i == 0 else GRID)
        if self.view.get() == "XY":
            guides = [
                (self.document.metrics.ascender, "ASCENDER", "#5b7782"),
                (self.document.metrics.x_height, "x-height", "#337e8c"),
                (self.document.metrics.cap_height, "CAP", "#3b93a4"),
                (self.document.metrics.baseline, "BASELINE", GOLD),
                (self.document.metrics.baseline + self.document.metrics.descender, "DESCENDER", "#996b58"),
            ]
            for value, label, color in guides:
                y = oy + value * cell
                self.canvas.create_line(0, y, 1250, y, fill=color, dash=(6, 4), width=2)
                self.canvas.create_text(8, y - 4, text=label, fill=color, anchor="sw")
        for gx, gy in self.selected_cells:
            x, y = ox + gx * cell, oy + gy * cell
            self.canvas.create_rectangle(
                x-cell*.43, y-cell*.43, x+cell*.43, y+cell*.43,
                fill="#dff8ff", stipple="gray50", outline="#ffffff", width=2,
            )
        for layer_index, layer in enumerate(self.glyph.layers):
            if not layer.visible:
                continue
            for point in layer.points:
                gx, gy = self._project(point)
                x, y = ox + gx * cell, oy + gy * cell
                radius = 5.0 + 5.0 * point.alpha * layer.opacity
                selected = layer_index == self.layer_index and self.point_cell(point) in self.selected_cells
                if selected:
                    self.canvas.create_oval(
                        x-radius-5, y-radius-5, x+radius+5, y+radius+5,
                        outline="#ffffff", width=3,
                    )
                self.canvas.create_oval(
                    x-radius, y-radius, x+radius, y+radius,
                    fill=point.color, outline="#bff7ff" if selected else "",
                )
        advance_x = ox + self.glyph.advance * cell
        self.canvas.create_line(advance_x, 0, advance_x, 900, fill="#d57b54", width=2, dash=(3, 3))
        self.canvas.create_text(advance_x + 4, 16, text="ADVANCE · NEXT CHARACTER START", fill="#d57b54", anchor="nw")

    def refresh_preview(self) -> None:
        previous_y = self.preview.yview()[0]
        self.preview.delete("all")
        scale = 7.0
        origin_x, origin_y = 12.0, 16.0
        width = max(240.0, float(self.preview.winfo_width()))
        viewport_height = max(120.0, float(self.preview.winfo_height()))
        wrap_width = max(1.0, (width - origin_x - 12.0) / scale)
        wrapped_text = self.document.wrap_text(
            self.preview_text.get(), wrap_width,
        )
        cursor_x = cursor_y = 0.0
        line_count = max(1, wrapped_text.count("\n") + 1)
        max_y = max(
            viewport_height,
            origin_y + line_count * self.document.metrics.line_height * scale + 12.0,
        )
        for char in wrapped_text:
            if char == "\n":
                cursor_x = 0
                cursor_y += self.document.metrics.line_height * scale
                continue
            if char.isspace():
                cursor_x += self.document.metrics.word_spacing * scale
                continue
            glyph = self.document.glyph_for_codepoint(ord(char))
            if glyph is None:
                cursor_x += self.document.metrics.word_spacing * scale
                continue
            for layer in glyph.layers:
                if not layer.visible:
                    continue
                for point in layer.points:
                    x = origin_x + cursor_x + point.x * scale
                    y = origin_y + cursor_y + point.y * scale
                    r = max(1.0, 2.2 * point.alpha * layer.opacity)
                    self.preview.create_oval(x-r, y-r, x+r, y+r, fill=point.color, outline="")
                    max_y = max(max_y, y + r + 12)
            cursor_x += (glyph.advance + self.document.metrics.letter_spacing) * scale
        self.preview.configure(scrollregion=(0, 0, width, max_y))
        self.preview.yview_moveto(previous_y)

    def _grid_at(self, event: tk.Event) -> tuple[int, int]:
        cell, ox, oy = self._canvas_geometry()
        return (
            round((self.canvas.canvasx(event.x) - ox) / cell),
            round((self.canvas.canvasy(event.y) - oy) / cell),
        )

    def point_at_cell(self, cell: tuple[int, int]) -> Point | None:
        return next((point for point in reversed(self.layer.points) if self.point_cell(point) == cell), None)

    def _add_point(self, gx: int, gy: int) -> None:
        existing = {point.key(): point for point in self.layer.points}
        if self.tool.get() == "brush":
            stamps = self.simple_brush.active_pixels()
        else:
            stamps = [(0, 0, 1.0)]
        for dx, dy, brush_alpha in stamps:
            made = self._unproject(gx + dx, gy + dy)
            made.alpha = max(.05, min(1.0, self.point_alpha.get()*brush_alpha))
            old = existing.get(made.key())
            if old:
                old.alpha = made.alpha
                old.color = self.point_color.get().lower()
            else:
                self.layer.points.append(made)
                existing[made.key()] = made

    def _erase_point(self, gx: int, gy: int) -> None:
        target = self._unproject(gx, gy)
        radius = max(0, self.brush_radius.get())
        self.layer.points[:] = [
            point for point in self.layer.points
            if math.dist(self._project(point), self._project(target)) > radius + .01
        ]

    def pointer_down(self, event: tk.Event) -> None:
        self.commit_advance()
        self.drag_start = self.last_drag_cell = self._grid_at(event)
        self.begin_action()
        tool = self.tool.get()
        if tool in {"dot", "brush"}:
            self._add_point(*self.drag_start)
        elif tool == "eraser":
            self._erase_point(*self.drag_start)
        elif tool == "fill":
            self.fill_selection() if self.selected_cells else self.fill_glyph_area()
        elif tool == "select":
            pass
        elif tool == "wand":
            self.magic_wand_region(self.drag_start)
        self.refresh_canvas()
        self.refresh_preview()

    def pointer_drag(self, event: tk.Event) -> None:
        cell = self._grid_at(event)
        if cell == self.last_drag_cell:
            return
        self.last_drag_cell = cell
        if self.tool.get() in {"dot", "brush"}:
            self._add_point(*cell)
        elif self.tool.get() == "eraser":
            self._erase_point(*cell)
        elif self.tool.get() == "select" and self.drag_start:
            self.select_rectangle(self.drag_start, cell)
        self.refresh_canvas()
        self.refresh_preview()

    def pointer_up(self, event: tk.Event) -> None:
        end = self._grid_at(event)
        tool = self.tool.get()
        if tool == "line" and self.drag_start:
            x0, y0 = self.drag_start
            x1, y1 = end
            steps = max(abs(x1-x0), abs(y1-y0), 1)
            for i in range(steps + 1):
                self._add_point(round(x0+(x1-x0)*i/steps), round(y0+(y1-y0)*i/steps))
        elif tool == "select" and self.drag_start:
            if end == self.drag_start:
                self.toggle_cell_or_group(end)
            else:
                self.select_rectangle(self.drag_start, end)
        self.record_action(f"{tool.title()} · {chr(self.codepoint)}")
        self.drag_start = self.last_drag_cell = None
        self.refresh()

    def double_left(self, event: tk.Event) -> str:
        if self.tool.get() == "select":
            self.clear_selection()
        elif self.tool.get() == "wand":
            self.magic_wand_all(self._grid_at(event))
        return "break"

    def select_rectangle(self, start: tuple[int, int], end: tuple[int, int]) -> None:
        left, right = sorted((start[0], end[0]))
        top, bottom = sorted((start[1], end[1]))
        self.selected_cells = {(x, y) for x in range(left, right+1) for y in range(top, bottom+1)}
        self.status.set(f"Selected {len(self.selected_cells)} grid cells.")

    def toggle_cell_or_group(self, cell: tuple[int, int]) -> None:
        point = self.point_at_cell(cell)
        if point and point.group:
            grouped = {self.point_cell(item) for item in self.layer.points if item.group == point.group}
            if grouped <= self.selected_cells:
                self.selected_cells -= grouped
            else:
                self.selected_cells |= grouped
        elif cell in self.selected_cells:
            self.selected_cells.remove(cell)
        else:
            self.selected_cells.add(cell)

    def magic_wand_region(self, cell: tuple[int, int]) -> None:
        point = self.point_at_cell(cell)
        if point is None:
            self.selected_cells = {cell}
            return
        color = point.color.lower()
        cells = {self.point_cell(item) for item in self.layer.points if item.color.lower() == color}
        selected: set[tuple[int, int]] = set()
        queue = deque([cell])
        while queue:
            current = queue.popleft()
            if current in selected or current not in cells:
                continue
            selected.add(current)
            x, y = current
            queue.extend(((x+1, y), (x-1, y), (x, y+1), (x, y-1)))
        self.selected_cells = selected
        self.status.set(f"Magic Wand selected {len(selected)} connected {color} cells.")

    def magic_wand_all(self, cell: tuple[int, int]) -> None:
        point = self.point_at_cell(cell)
        if point:
            color = point.color.lower()
            self.selected_cells = {
                self.point_cell(item) for item in self.layer.points if item.color.lower() == color
            }
            self.status.set(f"Magic Wand selected every {color} point in the work area.")
            self.refresh_canvas()

    def right_down(self, event: tk.Event) -> str:
        self._right_press_event = event
        self._wand_move_active = False
        self._wand_move_last = self._grid_at(event)
        if self.tool.get() == "wand":
            self._right_hold_job = self.after(2390, self.activate_wand_move)
        return "break"

    def activate_wand_move(self) -> None:
        self._right_hold_job = None
        self.begin_action()
        occupied = [self.point_cell(point) for point in self.layer.points]
        if occupied:
            left = min(x for x, _ in occupied)
            right = max(x for x, _ in occupied)
            top = min(y for _, y in occupied)
            bottom = max(y for _, y in occupied)
            self.selected_cells = {(x, y) for x in range(left, right+1) for y in range(top, bottom+1)}
        else:
            self.selected_cells = {self._wand_move_last or (0, 0)}
        self._wand_move_active = True
        self.status.set("Magic Wand character move active — keep holding and drag.")
        self.refresh_canvas()

    def right_drag(self, event: tk.Event) -> str:
        if self._wand_move_active:
            cell = self._grid_at(event)
            previous = self._wand_move_last or cell
            dx, dy = cell[0]-previous[0], cell[1]-previous[1]
            if dx or dy:
                selected = set(self.selected_cells)
                for point in self.layer.points:
                    if self.point_cell(point) in selected:
                        if self.view.get() in {"XY", "XZ"}:
                            point.x += dx
                        else:
                            point.z += dx
                        if self.view.get() in {"XY", "YZ"}:
                            point.y += dy
                        else:
                            point.z += dy
                self.selected_cells = {(x+dx, y+dy) for x, y in selected}
                self._wand_move_last = cell
                self.refresh_canvas()
        return "break"

    def right_up(self, event: tk.Event) -> str:
        if self._right_hold_job:
            self.after_cancel(self._right_hold_job)
            self._right_hold_job = None
        if self._wand_move_active:
            self._wand_move_active = False
            self.record_action(f"Move selected · {chr(self.codepoint)}")
            self.popup_selection_menu(event)
        else:
            cell = self._grid_at(event)
            if not self.selected_cells:
                self.selected_cells = {cell}
            self.popup_selection_menu(event)
        self.refresh_canvas()
        return "break"

    def double_right(self, event: tk.Event) -> str:
        occupied = [self.point_cell(point) for point in self.layer.points]
        if occupied:
            left, right = min(x for x, _ in occupied), max(x for x, _ in occupied)
            top, bottom = min(y for _, y in occupied), max(y for _, y in occupied)
            all_cells = {(x, y) for x in range(left, right+1) for y in range(top, bottom+1)}
        else:
            all_cells = {self._grid_at(event)}
        if all_cells and all_cells <= self.selected_cells:
            self.selected_cells.clear()
            self.status.set("Double-right-click de-selected the work area.")
        else:
            self.selected_cells = all_cells
            self.popup_selection_menu(event)
        self.refresh_canvas()
        return "break"

    def popup_selection_menu(self, event: tk.Event) -> None:
        groups = {point.group for point in self.points_in_selection() if point.group}
        self.selection_menu.entryconfigure(0, label="De-Group" if groups else "Group")
        self.selection_menu.tk_popup(event.x_root, event.y_root)

    def clear_selection(self) -> None:
        self.selected_cells.clear()
        self.refresh_canvas()

    def group_selection(self) -> None:
        points = self.points_in_selection()
        if not points:
            return
        self.begin_action()
        groups = {point.group for point in points if point.group}
        if groups:
            for point in points:
                point.group = 0
            label = "De-group selection"
        else:
            group = 1 + max((point.group for point in self.layer.points), default=0)
            for point in points:
                point.group = group
            label = "Group selection"
        self.record_action(label)
        self.refresh()

    def erase_selection(self) -> None:
        if not self.selected_cells:
            return
        self.begin_action()
        self.layer.points[:] = [
            point for point in self.layer.points if self.point_cell(point) not in self.selected_cells
        ]
        self.record_action("Erase selection")
        self.refresh()

    def fill_selection(self) -> None:
        if not self.selected_cells:
            return
        if self._gesture_before is None:
            self.begin_action()
        for cell in sorted(self.selected_cells):
            self._add_point(*cell)
        self.record_action("Fill selected cells")
        self.refresh()

    def fill_glyph_area(self) -> None:
        for x in range(max(0, math.floor(self.glyph.advance))):
            for y in range(math.floor(self.document.metrics.ascender), math.ceil(self.document.metrics.baseline)+1):
                self._add_point(x, y)

    # ----- settings / layers -----

    def show_alpha_popup(self) -> None:
        value = self.point_alpha.get()
        self.alpha_popup.configure(text=f"{value:.2f}")
        self.alpha_popup.update_idletasks()
        width = max(1, self.alpha_box.winfo_width() - self.alpha_popup.winfo_reqwidth())
        self.alpha_popup.place(x=round((value-.05)/.95*width), y=0)

    def hide_alpha_popup_later(self) -> None:
        if self._alpha_hide_job:
            self.after_cancel(self._alpha_hide_job)
        self._alpha_hide_job = self.after(1100, self.alpha_popup.place_forget)

    def change_point_alpha(self, _value=None) -> None:
        self.show_alpha_popup()
        selected = self.points_in_selection()
        if selected:
            for point in selected:
                point.alpha = self.point_alpha.get()
            self.refresh_canvas()
            self.refresh_preview()

    def choose_color(self) -> None:
        color = ask_point_color(self, self.point_color.get(), self.color_slots_path)
        if color:
            self.begin_action()
            self.point_color.set(color.lower())
            for point in self.points_in_selection():
                point.color = color.lower()
            self.record_action("Change selected point color")
            self.refresh()

    def add_layer(self) -> None:
        name = simpledialog.askstring("+SCFS+", "New layer name:", initialvalue=f"Layer {len(self.glyph.layers)+1}")
        if name:
            self.begin_action()
            self.glyph.layers.append(Layer(name))
            self.layer_index = len(self.glyph.layers)-1
            self.record_action(f"Add layer · {name}")
            self.refresh()

    def delete_layer(self) -> None:
        if len(self.glyph.layers) <= 1:
            messagebox.showinfo("+SCFS+", "A glyph keeps at least one layer.")
            return
        self.begin_action()
        name = self.layer.name
        del self.glyph.layers[self.layer_index]
        self.layer_index = max(0, self.layer_index-1)
        self.record_action(f"Delete layer · {name}")
        self.refresh()

    def move_layer(self, delta: int) -> None:
        target = self.layer_index + delta
        if 0 <= target < len(self.glyph.layers):
            self.begin_action()
            self.glyph.layers[self.layer_index], self.glyph.layers[target] = self.glyph.layers[target], self.glyph.layers[self.layer_index]
            self.layer_index = target
            self.record_action("Reorder layers")
            self.refresh()

    def rename_layer(self) -> None:
        name = simpledialog.askstring("+SCFS+", "Layer name:", initialvalue=self.layer.name)
        if name:
            self.begin_action()
            self.layer.name = name
            self.record_action("Rename layer")
            self.refresh()

    def select_layer(self, _event=None) -> None:
        selected = self.layer_list.curselection()
        if selected:
            self.layer_index = selected[0]
            self.selected_cells.clear()
            self.sync_active_layer_controls()
            self.layer_list.see(self.layer_index)
            self.refresh_canvas()

    def change_layer_opacity(self, _value=None) -> None:
        if self._history_busy:
            return
        self.layer.opacity = self.layer_opacity.get()
        if self.layer_list.size():
            self.layer_list.delete(self.layer_index)
            self.layer_list.insert(
                self.layer_index,
                f"{'●' if self.layer.visible else '○'} {self.layer.name}  ({len(self.layer.points)} pts) [{self.layer.opacity:.2f}]",
            )
            self.layer_list.selection_set(self.layer_index)
            self.layer_list.see(self.layer_index)
        self.refresh_canvas()
        self.refresh_preview()

    def toggle_layer_visibility(self) -> None:
        self.begin_action()
        self.layer.visible = self.layer_visible.get()
        self.record_action("Toggle layer visibility")
        self.refresh()

    def clear_layer(self) -> None:
        if self.layer.points and messagebox.askyesno("+SCFS+", f"Clear all points from {self.layer.name}?"):
            self.begin_action()
            self.layer.points.clear()
            self.record_action("Clear layer")
            self.refresh()

    def copy_glyph(self) -> None:
        self._clipboard = copy_glyph_snapshot(
            self.glyph, self.codepoint, self.layer_index,
        )
        self.status.set(
            f"Copied U+{self.codepoint:04X} with all layers; "
            f"source layer {self.layer_index + 1} remembered."
        )

    def paste_glyph(self) -> None:
        if not self._clipboard:
            self.status.set("Copy a glyph first.")
            return
        self.begin_action()
        mode, active_index = paste_glyph_snapshot(
            self.document, self.codepoint, self.layer_index, self._clipboard,
        )
        self.layer_index = active_index
        if mode == "layer":
            label = f"Paste copied layer into layer {active_index + 1}"
            self.status.set(
                f"Pasted source layer {self._clipboard.source_layer_index + 1} "
                f"into active layer {active_index + 1} of the same glyph."
            )
        else:
            label = f"Paste complete glyph · {chr(self.codepoint)}"
            self.status.set(
                f"Pasted all layers into U+{self.codepoint:04X}; "
                f"restored copied active layer {active_index + 1}."
            )
        self.record_action(label)
        self.refresh()

    def load_legacy_example(self) -> None:
        answer = messagebox.askyesnocancel(
            "+SCFS+ Exp glyph",
            "The main editable legacy font will replace the active workspace.\n\n"
            "Yes: save first, then continue\nNo: continue without saving\nCancel: return unchanged",
        )
        if answer is None:
            return
        if answer and not self.save():
            return
        self.document = current_engine_font()
        self.path = None
        self.font_name.set(self.document.name)
        self.history.clear()
        self.history_cursor = 0
        self.history_base = self.document.clone()
        self.selected_cells.clear()
        self.status.set("Editable legacy engine font loaded.")
        self.refresh()

    def schedule_advance(self) -> None:
        if self._advance_job is None:
            self.begin_action()
        else:
            self.after_cancel(self._advance_job)
        self._advance_job = self.after(300, self.commit_advance)

    def commit_advance(self) -> None:
        if self._advance_job is None:
            return
        self.after_cancel(self._advance_job)
        self._advance_job = None
        try:
            value = float(self.advance.get())
        except (TypeError, ValueError, tk.TclError):
            self._gesture_before = None
            return
        value = max(0.0, min(64.0, value))
        self.glyph.advance = value
        self.record_action("Change glyph Advance")
        self.refresh_canvas()
        self.refresh_preview()

    def change_name(self) -> None:
        name = self.font_name.get().strip()
        if name and name != self.document.name:
            self.begin_action()
            self.document.name = name
            self.record_action("Rename font")

    # ----- files / help -----

    def open_help(self) -> None:
        HelpReader(self)

    def new(self) -> None:
        if messagebox.askyesno("+SCFS+", "Start a blank font?"):
            self.document = FontDocument()
            self.path = None
            self.font_name.set(self.document.name)
            self.history.clear()
            self.history_cursor = 0
            self.history_base = self.document.clone()
            self.selected_cells.clear()
            self.refresh()

    def open(self) -> None:
        value = filedialog.askopenfilename(filetypes=[("SignalCloud font", "*.scfont"), ("All files", "*")])
        if not value:
            return
        try:
            self.document = FontDocument.load(Path(value))
            self.path = Path(value)
            self.font_name.set(self.document.name)
            self.history.clear()
            self.history_cursor = 0
            self.history_base = self.document.clone()
            self.selected_cells.clear()
            self.refresh()
        except Exception as exc:
            messagebox.showerror("+SCFS+ Open", str(exc))

    def import_font(self) -> None:
        value = filedialog.askopenfilename(
            title="Import an outline font as SignalCloud points",
            filetypes=[
                ("Font files", "*.ttf *.otf *.rfb"),
                ("TrueType", "*.ttf"), ("OpenType", "*.otf"),
                ("RFB project", "*.rfb"), ("All files", "*"),
            ],
        )
        if not value:
            return
        try:
            probe = probe_font(Path(value))
        except Exception as exc:
            messagebox.showerror("+SCFS+ Font Import", str(exc))
            return
        if not probe.supported:
            messagebox.showerror(
                "+SCFS+ Font Import",
                f"{Path(value).name}\n\nDetected: {probe.format}\n{probe.detail}",
            )
            return
        dialog = FontImportDialog(self, probe, self.point_color.get())
        self.wait_window(dialog)
        if dialog.result is None:
            return
        answer = messagebox.askyesnocancel(
            "+SCFS+ Font Import",
            "The converted font will replace the active workspace.\n\n"
            "Yes: save the current workspace first\n"
            "No: replace it without saving\n"
            "Cancel: keep the workspace unchanged",
        )
        if answer is None:
            return
        if answer and not self.save():
            return
        self.document = dialog.result
        self.path = None
        self.font_name.set(self.document.name)
        self.codepoint = next((code for code in self.document.glyphs if code != 0x20),
                              next(iter(self.document.glyphs)))
        self.layer_index = 0
        self.history.clear()
        self.history_cursor = 0
        self.history_base = self.document.clone()
        self.selected_cells.clear()
        points = sum(
            len(layer.points) for glyph in self.document.glyphs.values() for layer in glyph.layers
        )
        self.status.set(
            f"Imported {probe.family}: {len(self.document.glyphs)} glyphs, {points:,} points."
        )
        self.refresh()

    def save(self) -> bool:
        self.change_name()
        if self.path is None:
            return self.save_as()
        try:
            self.document.save(self.path)
            self.status.set(f"Saved {self.path.name}")
            return True
        except Exception as exc:
            messagebox.showerror("+SCFS+ Save", str(exc))
            return False

    def save_as(self) -> bool:
        value = filedialog.asksaveasfilename(defaultextension=".scfont", filetypes=[("SignalCloud font", "*.scfont")])
        if not value:
            return False
        self.path = Path(value)
        return self.save()

    def validate(self) -> None:
        errors = self.document.validate()
        if errors:
            messagebox.showerror("+SCFS+ Validation", "\n".join(errors))
        else:
            points = sum(len(layer.points) for glyph in self.document.glyphs.values() for layer in glyph.layers)
            messagebox.showinfo("+SCFS+ Validation", f"PASS\n{len(self.document.glyphs)} glyphs\n{points:,} source points")

    def export_report(self) -> None:
        value = filedialog.asksaveasfilename(defaultextension=".txt", filetypes=[("Text report", "*.txt")])
        if not value:
            return
        points = sum(len(layer.points) for glyph in self.document.glyphs.values() for layer in glyph.layers)
        Path(value).write_text(
            f"+SCFS+ FONT REPORT\nName: {self.document.name}\nGlyphs: {len(self.document.glyphs)}\n"
            f"Source points: {points}\nFormat: SCFONT 1 / A1R2 catalogs + brushes + render preview\n", encoding="utf-8",
        )
        self.status.set(f"Exported {Path(value).name}")


def apply_theme(root: tk.Tk) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure(".", background=BG, foreground=TEXT, fieldbackground=PANEL)
    style.configure("TFrame", background=BG)
    style.configure("TLabelframe", background=BG, foreground=TEXT)
    style.configure("TLabelframe.Label", background=BG, foreground=CYAN)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("TButton", background=PANEL, foreground=TEXT)
    style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT)
    style.configure("TNotebook", background=BG)
    style.configure("TNotebook.Tab", background=PANEL, foreground=TEXT)
    style.map("TNotebook.Tab", background=[("selected", "#1c3d49")])
    style.configure(
        "SCFS.TCombobox", fieldbackground=PANEL, background=PANEL,
        foreground=TEXT, arrowcolor=CYAN, bordercolor="#36515d",
        lightcolor="#36515d", darkcolor="#15272e",
    )
    style.map(
        "SCFS.TCombobox",
        fieldbackground=[("readonly", PANEL), ("disabled", "#182328")],
        foreground=[("readonly", TEXT), ("disabled", MUTED)],
        selectbackground=[("readonly", PANEL)],
        selectforeground=[("readonly", TEXT)],
    )
    root.option_add("*TCombobox*Listbox.background", PANEL)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", "#1c3d49")
    root.option_add("*TCombobox*Listbox.selectForeground", "#e8fbff")
    style.configure(
        "History.Treeview", background=PANEL, fieldbackground=PANEL,
        foreground=TEXT, bordercolor="#263942", rowheight=24,
    )
    style.map(
        "History.Treeview",
        background=[("selected", "#1c3d49")],
        foreground=[("selected", "#e8fbff")],
    )


def launch(project_root: Path) -> None:
    root = tk.Tk()
    root.title("+SCFS+ — SignalCloud Font Studio Alpha A1R4 v0.1.7")
    root.geometry("1420x900")
    root.minsize(1080, 700)
    apply_theme(root)
    editor = ScfsEditor(root, project_root)
    editor.pack(fill="both", expand=True)
    root.mainloop()
