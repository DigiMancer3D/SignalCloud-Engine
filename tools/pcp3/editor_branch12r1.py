from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import ttk

from tools.pcp3 import editor_branch12 as branch12
from tools.pcp3.help_center import (
    ALL_TOPICS,
    GUIDE_SCOPES,
    HELP_CENTER_SCHEMA,
    TOPIC_BY_KEY,
    categories,
    search_topics,
    topic_markdown,
    topics_for_context,
    topics_for_scope,
)
from tools.pcp3.help_guide import HelpTopic


MANAGED_HELP_LABELS = {
    "Authoring Help Guide",
    "Editor Help Center",
    "Help for Current Context",
    "Complete Authoring Guide",
    "Complete Mode Guide",
    "Detailed Tools Guide",
    "Quick Start Workflow",
    "Tools Help Guide",
}


class PCP3Editor(branch12.PCP3Editor):
    """Branch 12 R1: complete editor, Mode and Tools help-center expansion."""

    def __init__(self, root_path: Path) -> None:
        self.help_scope_var: tk.StringVar | None = None
        self.help_scope_combo: ttk.Combobox | None = None
        self.help_scope_key = "all"
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch12_R1"
        self.document.metadata["help_center_schema"] = HELP_CENTER_SCHEMA
        self.document.metadata["editor_help_guide"] = "complete"
        self.document.metadata["mode_help_guide"] = "complete"
        self.document.metadata["tools_help_guide"] = "complete_v2"
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 12 R1 Complete Help Center")
        self.update_status(
            "Branch 12 R1 active · Complete Editor Guide · Mode Guide · detailed Tools Guide · context Help"
        )

    # ---------- menu / shortcuts ----------
    def _build_menu(self) -> None:
        super()._build_menu()
        try:
            menu = self.nametowidget(self.cget("menu"))
            help_menu: tk.Menu | None = None
            end = menu.index("end")
            if end is None:
                return
            for index in range(end + 1):
                try:
                    if str(menu.entrycget(index, "label")) == "Help":
                        help_menu = self.nametowidget(menu.entrycget(index, "menu"))
                        break
                except tk.TclError:
                    continue
            if help_menu is None:
                return
            old_end = help_menu.index("end")
            if old_end is not None:
                for index in range(old_end, -1, -1):
                    try:
                        label = str(help_menu.entrycget(index, "label"))
                    except tk.TclError:
                        continue
                    if label in MANAGED_HELP_LABELS or label.startswith("Authoring Help Guide —"):
                        help_menu.delete(index)
            help_menu.insert_command(0, label="Editor Help Center", accelerator="F1", command=self.show_editor_help_guide)
            help_menu.insert_command(1, label="Help for Current Context", accelerator="Shift+F1", command=self.show_help_for_current_context)
            help_menu.insert_separator(2)
            help_menu.insert_command(3, label="Complete Authoring Guide", command=self.show_authoring_help_guide)
            help_menu.insert_command(4, label="Complete Mode Guide", command=self.show_mode_help_guide)
            help_menu.insert_command(5, label="Detailed Tools Guide", command=self.show_tools_help)
            help_menu.insert_command(6, label="Quick Start Workflow", command=lambda: self.show_help_center("quick_start", "all"))
            help_menu.insert_separator(7)
        except tk.TclError:
            pass

    def _bind_shortcuts(self) -> None:
        super()._bind_shortcuts()
        self.bind_all("<F1>", lambda _event: self.show_editor_help_guide())
        self.bind_all("<Shift-F1>", lambda _event: self.show_help_for_current_context())

    # ---------- direct guide entries ----------
    def show_editor_help_guide(self) -> None:
        self.show_help_center("editor_overview", "editor")

    def show_authoring_help_guide(self, topic_key: str | None = None) -> None:
        self.show_help_center(topic_key or "quick_start", "authoring")

    def show_mode_help_guide(self) -> None:
        mode_key = str(getattr(self.document, "environment_type", ""))
        topic_key = f"mode_{mode_key}" if f"mode_{mode_key}" in TOPIC_BY_KEY else "mode_overview"
        self.show_help_center(topic_key, "mode")

    def show_tools_help(self) -> None:
        tool_key = ""
        try:
            tool_key = str(self.tool.get())
        except (tk.TclError, AttributeError):
            pass
        topic_key = {
            "select": "tool_select",
            "pencil": "tool_pencil",
            "brush": "tool_brush",
            "eraser": "tool_eraser",
            "recolor": "tool_recolor",
            "picker": "tool_picker",
            "line": "tool_line_curve",
            "rotate": "tool_rotate",
            "roll": "tool_roll",
            "pan": "tool_pan",
            "window_sync": "tool_window_sync",
        }.get(tool_key, "tool_hud")
        self.show_help_center(topic_key, "tools")

    def show_authoring_help_plan(self) -> None:
        self.show_authoring_help_guide("quick_start")

    # ---------- complete Help Center ----------
    def show_help_center(self, topic_key: str | None = None, scope: str = "all") -> None:
        scope = scope if scope in GUIDE_SCOPES else "all"
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.deiconify()
            self.help_window.lift()
            self.help_window.focus_force()
            if topic_key and self.help_search_var is not None:
                self.help_search_var.set("")
            self._set_help_scope(scope, refresh=True)
            if topic_key:
                self._select_help_topic(topic_key)
            return

        window = tk.Toplevel(self)
        self.help_window = window
        window.title("Point Cloud Paint++ — Complete Help Center")
        window.geometry("1180x780")
        window.minsize(860, 580)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_help_window)

        self.help_search_var = tk.StringVar(master=window, value="")
        self.help_context_var = tk.StringVar(master=window, value=self._context_description())
        self.help_topic_status = tk.StringVar(master=window, value=f"{len(ALL_TOPICS)} help topics")
        self.help_scope_key = scope
        self.help_scope_var = tk.StringVar(master=window, value=GUIDE_SCOPES[scope])

        top = ttk.Frame(window, padding=(8, 8, 8, 4))
        top.pack(fill="x")
        ttk.Label(top, text="Guide", font=("Sans", 10, "bold")).pack(side="left")
        combo = ttk.Combobox(
            top,
            textvariable=self.help_scope_var,
            values=tuple(GUIDE_SCOPES.values()),
            state="readonly",
            width=19,
        )
        combo.pack(side="left", padx=(6, 12))
        combo.bind("<<ComboboxSelected>>", lambda _event: self._help_scope_changed())
        self.help_scope_combo = combo
        ttk.Label(top, text="Search", font=("Sans", 10, "bold")).pack(side="left")
        entry = ttk.Entry(top, textvariable=self.help_search_var)
        entry.pack(side="left", fill="x", expand=True, padx=6)
        entry.bind("<Return>", lambda _event: self._refresh_help_results())
        entry.bind("<KeyRelease>", lambda _event: self._schedule_help_search())
        ttk.Button(top, text="Search", command=self._refresh_help_results).pack(side="left")
        ttk.Button(top, text="Clear", command=self._clear_help_search).pack(side="left", padx=(4, 0))
        ttk.Button(top, text="Current Context", command=self._select_current_context_help).pack(side="left", padx=(8, 0))

        context_row = ttk.Frame(window, padding=(8, 0, 8, 4))
        context_row.pack(fill="x")
        ttk.Label(context_row, textvariable=self.help_context_var, wraplength=960).pack(side="left", fill="x", expand=True)
        ttk.Button(context_row, text="Refresh Context", command=self._refresh_help_context).pack(side="right")

        paned = ttk.Panedwindow(window, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=8, pady=4)
        left = ttk.Frame(paned, padding=4)
        right = ttk.Frame(paned, padding=4)
        paned.add(left, weight=1)
        paned.add(right, weight=3)

        tree = ttk.Treeview(left, show="tree", selectmode="browse")
        tree.pack(side="left", fill="both", expand=True)
        tree.bind("<<TreeviewSelect>>", self._help_tree_selected)
        scrollbar = ttk.Scrollbar(left, orient="vertical", command=tree.yview)
        scrollbar.pack(side="right", fill="y")
        tree.configure(yscrollcommand=scrollbar.set)
        self.help_topic_tree = tree

        text_frame = ttk.Frame(right)
        text_frame.pack(fill="both", expand=True)
        body = tk.Text(text_frame, wrap="word", padx=12, pady=10, state="disabled")
        body.pack(side="left", fill="both", expand=True)
        body_scroll = ttk.Scrollbar(text_frame, orient="vertical", command=body.yview)
        body_scroll.pack(side="right", fill="y")
        body.configure(yscrollcommand=body_scroll.set)
        body.tag_configure("title", font=("Sans", 18, "bold"), spacing3=8)
        body.tag_configure("category", font=("Sans", 9, "bold"), foreground="#4c7398", spacing3=6)
        body.tag_configure("summary", font=("Sans", 11, "italic"), spacing3=10)
        body.tag_configure("heading", font=("Sans", 12, "bold"), spacing1=10, spacing3=4)
        body.tag_configure("code", font=("Monospace", 10), background="#ececec", lmargin1=12, lmargin2=12)
        body.tag_configure("warning", foreground="#9a4f00", font=("Sans", 10, "bold"))
        self.help_body = body

        actions = ttk.Frame(window, padding=(8, 4))
        actions.pack(fill="x")
        ttk.Button(actions, text="Go to Related UI", command=self._go_to_help_ui).pack(side="left")
        ttk.Button(actions, text="Open Example", command=self._open_help_example).pack(side="left", padx=4)
        ttk.Button(actions, text="Open Documentation", command=self._open_help_document).pack(side="left")
        ttk.Button(actions, text="Copy Topic", command=self._copy_help_topic).pack(side="left", padx=4)
        ttk.Label(actions, textvariable=self.help_topic_status).pack(side="right")

        self._refresh_help_results()
        if topic_key:
            self._select_help_topic(topic_key)
        else:
            self._select_current_context_help()
        entry.focus_set()

    def _scope_key_from_label(self, label: str) -> str:
        for key, value in GUIDE_SCOPES.items():
            if value == label:
                return key
        return "all"

    def _set_help_scope(self, scope: str, *, refresh: bool = False) -> None:
        self.help_scope_key = scope if scope in GUIDE_SCOPES else "all"
        if self.help_scope_var is not None:
            self.help_scope_var.set(GUIDE_SCOPES[self.help_scope_key])
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.title(f"Point Cloud Paint++ — {GUIDE_SCOPES[self.help_scope_key]}")
        if refresh:
            self._refresh_help_results()

    def _help_scope_changed(self) -> None:
        label = self.help_scope_var.get() if self.help_scope_var is not None else GUIDE_SCOPES["all"]
        self._set_help_scope(self._scope_key_from_label(label), refresh=True)

    def _refresh_help_results(self) -> None:
        tree = self.help_topic_tree
        if tree is None:
            return
        query = self.help_search_var.get() if self.help_search_var is not None else ""
        selected_key = self.help_current_topic.key if self.help_current_topic is not None else ""
        results = search_topics(query, self.help_scope_key)
        self.help_visible_topics = results
        for item in tree.get_children(""):
            tree.delete(item)
        result_keys = {topic.key for topic in results}
        for category in categories(results):
            category_id = tree.insert("", "end", text=category, open=True)
            for topic in results:
                if topic.category == category:
                    tree.insert(category_id, "end", iid=f"topic:{topic.key}", text=topic.title)
        total = len(topics_for_scope(self.help_scope_key))
        if self.help_topic_status is not None:
            self.help_topic_status.set(f"{len(results)} of {total} topics · {GUIDE_SCOPES[self.help_scope_key]}")
        if selected_key in result_keys:
            self._select_help_topic(selected_key)
        elif results:
            self._select_help_topic(results[0].key)
        else:
            self._render_no_help_results(query)

    def _render_no_help_results(self, query: str) -> None:
        body = self.help_body
        if body is None:
            return
        body.configure(state="normal")
        body.delete("1.0", "end")
        body.insert("end", "No matching help topics\n", "title")
        body.insert("end", f"No topic matched {query!r} inside {GUIDE_SCOPES[self.help_scope_key]}.\n\n")
        body.insert("end", "Try fewer terms or choose All Guides. Useful terms: mode, portal, brush, selection, export, semantic, Signal Void or blocked.")
        body.configure(state="disabled")
        self.help_current_topic = None

    def _select_help_topic(self, topic_key: str) -> None:
        topic = TOPIC_BY_KEY.get(topic_key)
        if topic is None:
            return
        visible_keys = {item.key for item in self.help_visible_topics}
        if self.help_topic_tree is not None and topic.key not in visible_keys:
            self._set_help_scope("all", refresh=True)
        self.help_current_topic = topic
        tree = self.help_topic_tree
        iid = f"topic:{topic.key}"
        if tree is not None and tree.exists(iid):
            if tuple(tree.selection()) != (iid,):
                tree.selection_set(iid)
            tree.see(iid)
        self._render_help_topic(topic)

    def _select_current_context_help(self) -> None:
        self._refresh_help_context()
        self._set_help_scope("all", refresh=True)
        matches = topics_for_context(self.current_help_context())
        if matches:
            self._select_help_topic(matches[0].key)

    def show_help_for_current_context(self) -> None:
        self.show_help_center(scope="all")
        self._select_current_context_help()

    def _copy_help_topic(self) -> None:
        topic = self.help_current_topic
        if topic is None:
            return
        self.clipboard_clear()
        self.clipboard_append(topic_markdown(topic))
        self.update_status(f"Copied Help Center topic: {topic.title}")

    def _close_help_window(self) -> None:
        super()._close_help_window()
        self.help_scope_var = None
        self.help_scope_combo = None


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
