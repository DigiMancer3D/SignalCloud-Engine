from __future__ import annotations

import sys
from pathlib import Path
from tkinter import ttk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.signalcloud_studio.ui import FlowBar
from tools.signalcloud_tupd.app import TupdWorkbenchApp

app = TupdWorkbenchApp(ROOT)
for _ in range(4):
    app.update_idletasks()
    app.update()
app.open_first_recipe()
for _ in range(2):
    app.update_idletasks()
    app.update()

assert len(app.catalog_entries) >= 5
assert app.current is not None
preview = app.sandbox.preview(app.current)
assert preview.result_id
assert app.sandbox.normal_save_unchanged

flows: list[FlowBar] = []

def walk(widget) -> None:
    if isinstance(widget, FlowBar):
        flows.append(widget)
    for child in widget.winfo_children():
        walk(child)

walk(app)
assert len(flows) == 1
buttons = [
    child
    for group in flows[0].items
    for child in group.winfo_children()
    if isinstance(child, ttk.Button)
]
assert len(buttons) == 17
assert len({button.winfo_rooty() for button in buttons}) >= 2
window_right = app.winfo_rootx() + app.winfo_width()
assert max(button.winfo_rootx() + button.winfo_width() for button in buttons) <= window_right

app.redraw_graph()
app.update_idletasks()
for node in app.graph_nodes:
    items = app.graph.find_withtag(f"node:{node}")
    assert items
    bounds = app.graph.bbox(*items)
    assert bounds is not None
    x0, y0, x1, y1 = bounds
    assert x0 >= 0 and y0 >= 0
    assert x1 <= app.graph.winfo_width() + 1
    assert y1 <= app.graph.winfo_height() + 1

app.destroy()
print("SignalCloud Tupd A8a3r1 responsive Workbench and fitted graph Tk smoke PASS")
