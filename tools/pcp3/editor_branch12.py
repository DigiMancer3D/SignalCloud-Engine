from __future__ import annotations

import shutil
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any

from tools.pcp3 import editor_branch11 as branch11
from tools.pcp3.help_guide import (
    HELP_SCHEMA,
    TOPICS,
    HelpContext,
    HelpTopic,
    categories,
    resolve_resource,
    search_topics,
    topic_markdown,
    topics_for_context,
)
from tools.pcp3.io import load_project


class PCP3Editor(branch11.PCP3Editor):
    """Branch 12: searchable in-application authoring documentation."""

    def __init__(self, root_path: Path) -> None:
        self.help_window: tk.Toplevel | None = None
        self.help_search_var: tk.StringVar | None = None
        self.help_context_var: tk.StringVar | None = None
        self.help_topic_tree: ttk.Treeview | None = None
        self.help_body: tk.Text | None = None
        self.help_topic_status: tk.StringVar | None = None
        self.help_current_topic: HelpTopic | None = None
        self.help_visible_topics: list[HelpTopic] = []
        super().__init__(root_path)
        self.document.metadata["editor_branch"] = "ISL_plus_branch12"
        self.document.metadata["authoring_help_schema"] = HELP_SCHEMA
        self.document.metadata["documentation_phase_authoring_help_guide"] = "complete"
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 12 Documentation & Authoring Help")
        self.update_status(
            "Branch 12 active · searchable Authoring Help · context guidance · nine mode tutorials · troubleshooting"
        )

    # ---------- menu / shortcuts ----------
    def _build_menu(self) -> None:
        super()._build_menu()
        try:
            menu = self.nametowidget(self.cget("menu"))
            end = menu.index("end")
            if end is None:
                return
            help_menu: tk.Menu | None = None
            for index in range(end + 1):
                try:
                    if menu.entrycget(index, "label") == "Help":
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
                    if label.startswith("Authoring Help Guide"):
                        help_menu.delete(index)
            help_menu.insert_command(0, label="Authoring Help Guide", accelerator="F1", command=self.show_authoring_help_guide)
            help_menu.insert_command(1, label="Help for Current Context", accelerator="Shift+F1", command=self.show_help_for_current_context)
            help_menu.insert_command(2, label="Quick Start Workflow", command=lambda: self.show_authoring_help_guide("quick_start"))
            help_menu.insert_separator(3)
        except tk.TclError:
            pass

    def _bind_shortcuts(self) -> None:
        super()._bind_shortcuts()
        self.bind_all("<F1>", lambda _event: self.show_authoring_help_guide())
        self.bind_all("<Shift-F1>", lambda _event: self.show_help_for_current_context())

    def show_authoring_help_plan(self) -> None:
        """Compatibility entry retained for inherited Branch 5 calls."""
        self.show_authoring_help_guide("quick_start")

    # ---------- context ----------
    def current_help_context(self) -> HelpContext:
        main_tab = ""
        authoring_tab = ""
        try:
            main_tab = str(self.right_notebook.tab(self.right_notebook.select(), "text"))
        except (tk.TclError, AttributeError):
            pass
        if main_tab == "Authoring":
            try:
                authoring_tab = str(self.authoring_notebook.tab(self.authoring_notebook.select(), "text"))
            except (tk.TclError, AttributeError):
                pass
        tool_key = ""
        try:
            tool_key = str(self.tool.get())
        except (tk.TclError, AttributeError):
            pass
        return HelpContext(
            main_tab=main_tab,
            authoring_tab=authoring_tab,
            tool_key=tool_key,
            mode_key=str(self.document.environment_type),
        )

    def _context_description(self) -> str:
        context = self.current_help_context()
        pieces = [f"Main: {context.main_tab or 'unknown'}"]
        if context.authoring_tab:
            pieces.append(f"Authoring: {context.authoring_tab}")
        pieces.append(f"Mode: {context.mode_key}")
        if context.tool_key:
            pieces.append(f"Tool: {context.tool_key}")
        return " · ".join(pieces)

    # ---------- help window ----------
    def show_authoring_help_guide(self, topic_key: str | None = None) -> None:
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.deiconify()
            self.help_window.lift()
            self.help_window.focus_force()
            if topic_key:
                self._select_help_topic(topic_key)
            return

        window = tk.Toplevel(self)
        self.help_window = window
        window.title("Point Cloud Paint++ — Authoring Help Guide")
        window.geometry("1120x760")
        window.minsize(820, 560)
        window.transient(self)
        window.protocol("WM_DELETE_WINDOW", self._close_help_window)

        self.help_search_var = tk.StringVar(master=window, value="")
        self.help_context_var = tk.StringVar(master=window, value=self._context_description())
        self.help_topic_status = tk.StringVar(master=window, value=f"{len(TOPICS)} help topics")

        top = ttk.Frame(window, padding=(8, 8, 8, 4))
        top.pack(fill="x")
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
        ttk.Label(context_row, textvariable=self.help_context_var, wraplength=920).pack(side="left", fill="x", expand=True)
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

    def _close_help_window(self) -> None:
        if self.help_window is not None and self.help_window.winfo_exists():
            self.help_window.destroy()
        self.help_window = None
        self.help_topic_tree = None
        self.help_body = None
        self.help_current_topic = None

    def _schedule_help_search(self) -> None:
        if self.help_window is None:
            return
        prior = getattr(self, "_help_search_after", None)
        if prior:
            try:
                self.after_cancel(prior)
            except tk.TclError:
                pass
        self._help_search_after = self.after(160, self._refresh_help_results)

    def _clear_help_search(self) -> None:
        if self.help_search_var is not None:
            self.help_search_var.set("")
        self._refresh_help_results()

    def _refresh_help_results(self) -> None:
        tree = self.help_topic_tree
        if tree is None:
            return
        query = self.help_search_var.get() if self.help_search_var is not None else ""
        selected_key = self.help_current_topic.key if self.help_current_topic is not None else ""
        results = search_topics(query)
        self.help_visible_topics = results
        for item in tree.get_children(""):
            tree.delete(item)
        result_keys = {topic.key for topic in results}
        for category in categories(results):
            category_id = tree.insert("", "end", text=category, open=True)
            for topic in results:
                if topic.category == category:
                    tree.insert(category_id, "end", iid=f"topic:{topic.key}", text=topic.title)
        if self.help_topic_status is not None:
            self.help_topic_status.set(f"{len(results)} of {len(TOPICS)} topics")
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
        body.insert("end", f"No topic matched: {query!r}\n\n")
        body.insert("end", "Try fewer terms such as portal, trigger, brush, streaming, certificate, Signal Void, or blocked.")
        body.configure(state="disabled")
        self.help_current_topic = None

    def _help_tree_selected(self, _event: tk.Event | None = None) -> None:
        tree = self.help_topic_tree
        if tree is None:
            return
        selected = tree.selection()
        if not selected:
            return
        item = selected[0]
        if item.startswith("topic:"):
            self._select_help_topic(item.split(":", 1)[1])

    def _select_help_topic(self, topic_key: str) -> None:
        topic = next((row for row in TOPICS if row.key == topic_key), None)
        if topic is None:
            return
        self.help_current_topic = topic
        tree = self.help_topic_tree
        iid = f"topic:{topic.key}"
        if tree is not None and tree.exists(iid):
            if tuple(tree.selection()) != (iid,):
                tree.selection_set(iid)
            tree.see(iid)
        self._render_help_topic(topic)

    def _render_help_topic(self, topic: HelpTopic) -> None:
        body = self.help_body
        if body is None:
            return
        body.configure(state="normal")
        body.delete("1.0", "end")
        body.insert("end", topic.title + "\n", "title")
        body.insert("end", topic.category.upper() + "\n", "category")
        body.insert("end", topic.summary + "\n", "summary")
        body.insert("end", topic.body.strip() + "\n")
        if topic.checklist:
            body.insert("end", "\nChecklist\n", "heading")
            for item in topic.checklist:
                body.insert("end", f"☐ {item}\n")
        if topic.blocked_reason:
            body.insert("end", "\nWhy blocked\n", "heading")
            body.insert("end", topic.blocked_reason + "\n", "warning")
        if topic.example:
            body.insert("end", "\nExample project\n", "heading")
            body.insert("end", topic.example + "\n", "code")
        if topic.document:
            body.insert("end", "\nRelated documentation\n", "heading")
            body.insert("end", topic.document + "\n", "code")
        if topic.key.startswith("mode_"):
            body.insert("end", "\nStarter note\n", "heading")
            body.insert(
                "end",
                "The tutorial starter contains mode-template layers and documentation metadata, but intentionally contains no finished geometry. Use it as a safe copy, not as a replacement for your accepted project.\n",
            )
        body.configure(state="disabled")
        body.yview_moveto(0.0)
        if self.help_topic_status is not None:
            self.help_topic_status.set(f"{topic.title} · {len(self.help_visible_topics)} visible topics")

    def _refresh_help_context(self) -> None:
        if self.help_context_var is not None:
            self.help_context_var.set(self._context_description())

    def show_help_for_current_context(self) -> None:
        self.show_authoring_help_guide()
        self._select_current_context_help()

    def _select_current_context_help(self) -> None:
        self._refresh_help_context()
        matches = topics_for_context(self.current_help_context())
        if matches:
            self._select_help_topic(matches[0].key)

    # ---------- topic actions ----------
    def _go_to_help_ui(self) -> None:
        topic = self.help_current_topic
        if topic is None:
            return
        if topic.authoring_tab:
            self.show_authoring_studio()
            self.update_idletasks()
            self._select_notebook_tab(self.authoring_notebook, topic.authoring_tab)
            if self.authoring_wrapped_tabs is not None:
                self.authoring_wrapped_tabs.refresh()
            try:
                self._authoring_subtab_changed()
            except (tk.TclError, AttributeError):
                pass
        elif topic.main_tab:
            self._select_notebook_tab(self.right_notebook, topic.main_tab)
        if topic.mode_key:
            try:
                self.environment_type.set(topic.mode_key)
                self.document.environment_type = topic.mode_key
                self.document.author.asset_type = topic.mode_key
                self.mark_dirty(f"Selected {topic.mode_key} mode from Authoring Help")
                self._select_notebook_tab(self.right_notebook, "Mode")
            except (tk.TclError, AttributeError):
                pass
        if topic.tool_key:
            try:
                self.tool.set(topic.tool_key)
                self.tool_changed()
            except (tk.TclError, AttributeError):
                pass
        self.lift()
        self.focus_force()
        self.update_status(f"Authoring Help opened related UI: {topic.title}")

    @staticmethod
    def _select_notebook_tab(notebook: ttk.Notebook, label: str) -> bool:
        try:
            for index in range(notebook.index("end")):
                if str(notebook.tab(index, "text")) == label:
                    notebook.select(index)
                    return True
        except tk.TclError:
            pass
        return False

    def _open_help_example(self) -> None:
        topic = self.help_current_topic
        if topic is None or not topic.example:
            messagebox.showinfo("Authoring Help", "This topic has no project example.", parent=self.help_window or self)
            return
        path = resolve_resource(self.root_path, topic.example)
        if path is None:
            messagebox.showwarning("Example unavailable", f"Example not found:\n{topic.example}", parent=self.help_window or self)
            return
        if not self.confirm_discard():
            return
        try:
            self.document = load_project(path)
            self.project_path = path
            self.history.clear()
            self.future.clear()
            self.push_history("Opened help example")
            self._sync_all_from_document()
            self.frame_all()
            self.update_status(f"Opened Authoring Help example: {path.name}")
            self.lift()
        except Exception as exc:
            messagebox.showerror("Example open failed", str(exc), parent=self.help_window or self)

    def _open_help_document(self) -> None:
        topic = self.help_current_topic
        if topic is None or not topic.document:
            messagebox.showinfo("Authoring Help", "This topic has no separate documentation file.", parent=self.help_window or self)
            return
        path = resolve_resource(self.root_path, topic.document)
        if path is None:
            messagebox.showwarning("Documentation unavailable", f"File not found:\n{topic.document}", parent=self.help_window or self)
            return
        opener = shutil.which("xdg-open")
        if opener is None:
            messagebox.showinfo("Documentation path", str(path), parent=self.help_window or self)
            return
        try:
            subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except OSError as exc:
            messagebox.showwarning("Open documentation failed", str(exc), parent=self.help_window or self)

    def _copy_help_topic(self) -> None:
        topic = self.help_current_topic
        if topic is None:
            return
        self.clipboard_clear()
        self.clipboard_append(topic_markdown(topic))
        self.update_status(f"Copied help topic: {topic.title}")

    def show_tools_help(self) -> None:
        before = set(self.winfo_children())
        super().show_tools_help()
        created = [child for child in self.winfo_children() if child not in before and isinstance(child, tk.Toplevel)]
        if not created:
            return

        def find_text(widget: tk.Misc) -> tk.Text | None:
            for child in widget.winfo_children():
                if isinstance(child, tk.Text):
                    return child
                found = find_text(child)
                if found is not None:
                    return found
            return None

        text = find_text(created[-1])
        if text is not None:
            text.configure(state="normal")
            obsolete = (
                "DOCUMENTATION PHASE NOTE\nThe future Authoring Help Guide must include a complete worked Encounter workflow, wave limits, boss phases, friendly placement, reset policies, completion conditions, reward-hook approval, and troubleshooting missing references.\n",
                "DOCUMENTATION PHASE NOTE\nThe future Authoring Help Guide must include Streaming profiles, LOD distances/ratios, chunk audits, semantic preservation, dry-run files, live telemetry, pop-in troubleshooting, and the distinction between bounded loading intent and currently active deterministic LOD execution.\n",
                "The documentation phase must add a dedicated Authoring Help Guide to the Help dropdown with complete workflows and examples.\n\n",
            )
            for phrase in obsolete:
                while True:
                    start = text.search(phrase, "1.0", stopindex="end")
                    if not start:
                        break
                    end = f"{start}+{len(phrase)}c"
                    text.delete(start, end)
            text.insert(
                "end",
                "\n\nBRANCH 12 — COMPLETE AUTHORING HELP GUIDE\n"
                "Press F1 or choose Help → Authoring Help Guide for searchable workflows, context guidance, all nine environment-mode tutorials, file/sidecar explanations, guarded-runtime boundaries, and troubleshooting. Shift+F1 opens the topic most closely related to the current sidebar, Authoring sub-tab, tool, and environment mode.\n",
            )
            text.configure(state="disabled")

    def on_close(self) -> None:
        self._close_help_window()
        super().on_close()


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
