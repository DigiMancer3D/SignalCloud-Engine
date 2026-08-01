from __future__ import annotations

import tkinter as tk
from dataclasses import dataclass
from tkinter import ttk


@dataclass(frozen=True)
class HelpTopic:
    category: str
    title: str
    text: str
    keywords: str = ""


TOPICS = [
    HelpTopic("Start Here", "+SCFS+ workspace", "The center grid edits one character at a time. The character selector changes the active glyph; layers and History at the right affect the open font document.", "overview"),
    HelpTopic("Glyph Geometry", "Advance", "Advance is the horizontal distance from the start of this character to the start of the next character. The orange ADVANCE line is therefore the right-side spacing boundary; it does not move the glyph center or its points.", "spacing width"),
    HelpTopic("Glyph Geometry", "Alignment guides", "Ascender, cap height, x-height, baseline, and descender guides keep letters aligned. They are shared font measurements; Advance is the separate per-character width.", "baseline cap"),
    HelpTopic("Glyph Geometry", "XY / XZ / YZ", "Projection chooses which two point coordinates the canvas displays. XY is the ordinary front of a character; XZ and YZ expose SignalCloud depth.", "projection depth"),
    HelpTopic("Tools", "Dot", "Adds one point at the clicked grid location. Existing selected points receive the current alpha and color when clicked again.", "pencil"),
    HelpTopic("Tools", "Line", "Drag from one grid location to another to add an interpolated point line. New points use the current alpha and color.", "stroke"),
    HelpTopic("Tools", "3D Brush", "Paints a circular stamp around the pointer. Radius 0 is one point; larger radii cover progressively wider grid regions.", "radius paint"),
    HelpTopic("Tools", "Fill", "Without a selection, fills the glyph area from the origin through its Advance and baseline. With a selection, it fills selected empty cells and updates selected points to the current color and alpha.", "empty"),
    HelpTopic("Tools", "Eraser", "Removes active-layer points under the brush. Radius 0 removes only the exact grid point; radius 1 covers the center and neighboring cells.", "delete"),
    HelpTopic("Tools", "Select", "Drag to select a rectangular grid region, including empty cells. A single click toggles a cell or selects its group; double-click clears the selection. Right-click opens Group/De-Group, Erase, Fill Empty, and De-Select.", "box group menu"),
    HelpTopic("Tools", "Magic Wand", "Single-click selects the connected region of the clicked point color. Double-click selects that color everywhere. Hold right-click for 2.39 seconds to capture the character region, then drag it before releasing.", "color region move"),
    HelpTopic("Point Settings", "Point Alpha", "Alpha is the point's individual transparency from 0.05 to 1.00. Changing it updates selected filled points live; later painting and filling use the displayed value.", "opacity"),
    HelpTopic("Point Settings", "Point Color", "Color belongs to every filled SignalCloud point and appears in both the workspace and text preview. Changing color updates selected filled points immediately.", "preview"),
    HelpTopic("Layers", "Layer opacity", "Layer opacity multiplies the alpha of every visible point on that layer without rewriting individual point alpha. The value appears in brackets beside the layer's point count.", "transparency"),
    HelpTopic("Layers", "Visible", "Visible hides or shows only the active layer without deleting it. The checkbox is synchronized whenever the active layer changes, moves, or is renamed.", "hide"),
    HelpTopic("Glyph Actions", "Copy / Paste glyph", "Copy stores the active glyph; Paste replaces the current character's glyph with that copy while retaining the current character code.", "duplicate"),
    HelpTopic("Glyph Actions", "Exp glyph", "Loads the complete editable legacy engine font as an example workspace. It replaces the active font, so +SCFS+ first offers Save, continue without saving, or Cancel.", "legacy example"),
    HelpTopic("Glyph Actions", "Store Custom", "Stores the character from the Custom / Unicode input in the persistent Created Unicode tab. Opening a glyph alone does not store it; this keeps experimental and intentionally cataloged characters separate.", "unicode tab"),
    HelpTopic("Glyph Actions", "Emoji tab", "Emoji buttons come only from current.emoji. The reader accepts the supplied whitespace list or forgiving JSON with optional name/category metadata, and ignores unknown metadata.", "catalog json"),
    HelpTopic("Tools", "Edit 3D Brush", "Shows or hides the themed single-layer brush-mask editor. Create a New 1×1, 4×4, 6×6, 8×8, or 9×9 brush; or load, save, choose a premade, paint strength cells, and Apply it before using the 3D Brush tool.", "simple brush size"),
    HelpTopic("Point Settings", "Brush Paint Strength", "Controls the strength written into newly painted simple-brush mask cells. Its value bubble appears away from the pointer during mouse/touch adjustment and toward screen center for keyboard adjustment.", "popup touch"),
    HelpTopic("Preview", "Render", "Opens the SignalCloud engine-style point preview adapted from +PCP+ camera projection. Rich uses world-space depth and orbit controls; Simple flattens depth into a GUI/menu presentation. Both modes smart-wrap to the visible width, grow only downward, and use the vertical scrollbar; wheel scrolls and Ctrl+wheel zooms.", "rich simple yaw pitch wrap scrollbar"),
    HelpTopic("History", "Undo / Redo", "Toolbar Undo and Redo move backward or forward through the normal chronological document states. Making a new action after Undo removes ordinary rolled-out future actions.", "linear"),
    HelpTopic("History", "Purgatory", "Click a History row to strike it out and italicize it: the action is held in purgatory and hidden without moving the Undo cursor. Click it again to restore it; right-click can also toggle or permanently delete that history record.", "mute strikeout"),
    HelpTopic("Preview", "Rich / simple text preview", "This preview lays out saved point colors, alpha, layer opacity, Advance, word spacing, and line spacing. Text smart-wraps by the current glyph widths, overwide single words break safely by character, and overflow is vertical only. Drag the divider to change its height and use the vertical scrollbar for new lines.", "resize wrap no horizontal overflow"),
    HelpTopic("Files", ".scfont", "SCFONT 1 is the native text asset containing font measurements, Unicode glyphs, layers, points, colors, alpha, depth, and groups. The C++ runtime consumes it without Python or Tk.", "format"),
    HelpTopic("Files", "Import Font", "Imports readable .ttf and .otf outline fonts as editable SignalCloud glyphs through the system FreeType library, including OpenType/CFF without requiring Pillow. Choose a 5–64 cell grid height, threshold, Unicode range, and edge alpha; source Advance and alignment metrics are retained.", "truetype opentype cff rasterize convert"),
    HelpTopic("Files", "RFB2 / custom TTF", "RFB2 is a separate custom raster-font project format. The supplied custom TTF uses widened nonstandard table records and incompatible glyph data; both are identified and refused without changing the workspace. Re-export the source from FontForge as a validated standard TrueType/OpenType font when possible.", "rfb extended invalid safe"),
]


class HelpReader(tk.Toplevel):
    def __init__(self, master: tk.Misc) -> None:
        super().__init__(master)
        self.title("+SCFS+ Help Reader")
        self.geometry("980x700")
        self.minsize(720, 500)
        self.search = tk.StringVar()
        self.category = tk.StringVar(value="All")
        self.zoom = tk.IntVar(value=11)
        self.filtered: list[HelpTopic] = []
        self._build()
        self.refresh_topics()

    def _build(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        bar = ttk.Frame(self, padding=8)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Label(bar, text="Search").pack(side="left")
        entry = ttk.Entry(bar, textvariable=self.search, width=34)
        entry.pack(side="left", padx=5)
        entry.bind("<KeyRelease>", lambda _e: self.refresh_topics())
        ttk.Label(bar, text="Filter").pack(side="left", padx=(10, 3))
        categories = ["All", *sorted({topic.category for topic in TOPICS})]
        ttk.Combobox(bar, values=categories, state="readonly", textvariable=self.category, width=18).pack(side="left")
        self.category.trace_add("write", lambda *_: self.refresh_topics())
        ttk.Button(bar, text="A−", command=lambda: self.set_zoom(-1)).pack(side="right")
        ttk.Button(bar, text="A+", command=lambda: self.set_zoom(1)).pack(side="right")
        self.zoom_label = ttk.Label(bar)
        self.zoom_label.pack(side="right", padx=6)

        side = ttk.Frame(self, padding=(8, 0, 4, 8))
        side.grid(row=1, column=0, sticky="ns")
        self.navigation = tk.Listbox(side, width=30, exportselection=False)
        self.navigation.pack(side="left", fill="y")
        scroll = ttk.Scrollbar(side, orient="vertical", command=self.navigation.yview)
        scroll.pack(side="left", fill="y")
        self.navigation.configure(yscrollcommand=scroll.set)
        self.navigation.bind("<<ListboxSelect>>", self.show_selected)

        body = ttk.Frame(self, padding=(4, 0, 8, 8))
        body.grid(row=1, column=1, sticky="nsew")
        body.columnconfigure(0, weight=1)
        body.rowconfigure(0, weight=1)
        self.text = tk.Text(body, wrap="word", padx=24, pady=20, state="disabled")
        self.text.grid(row=0, column=0, sticky="nsew")
        text_scroll = ttk.Scrollbar(body, orient="vertical", command=self.text.yview)
        text_scroll.grid(row=0, column=1, sticky="ns")
        self.text.configure(yscrollcommand=text_scroll.set)

    def set_zoom(self, change: int) -> None:
        self.zoom.set(max(8, min(24, self.zoom.get() + change)))
        self.show_selected()

    def refresh_topics(self) -> None:
        query = self.search.get().strip().lower()
        category = self.category.get()
        self.filtered = [
            topic for topic in TOPICS
            if (category == "All" or topic.category == category)
            and (not query or query in f"{topic.category} {topic.title} {topic.text} {topic.keywords}".lower())
        ]
        self.navigation.delete(0, "end")
        for topic in self.filtered:
            self.navigation.insert("end", f"{topic.category}  ›  {topic.title}")
        if self.filtered:
            self.navigation.selection_set(0)
        self.show_selected()

    def show_selected(self, _event=None) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        selected = self.navigation.curselection()
        if selected and selected[0] < len(self.filtered):
            topic = self.filtered[selected[0]]
            self.text.tag_configure("category", foreground="#78929b", font=("Sans", max(8, self.zoom.get()-1), "bold"))
            self.text.tag_configure("title", foreground="#45d8ef", font=("Sans", self.zoom.get()+6, "bold"), spacing3=14)
            self.text.tag_configure("body", font=("Sans", self.zoom.get()), spacing3=10)
            self.text.insert("end", topic.category.upper() + "\n", "category")
            self.text.insert("end", topic.title + "\n", "title")
            self.text.insert("end", topic.text + "\n", "body")
        else:
            self.text.insert("end", "No help topics match this search and filter.")
        self.text.configure(state="disabled")
        self.zoom_label.configure(text=f"{self.zoom.get()} pt")
