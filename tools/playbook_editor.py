#!/usr/bin/env python3
"""SignalCloud Universal Playbook Lab.

A bounded JSON authoring surface shared by users, enemies, environmental
systems, props, weapons, effects, and future animator event consumers.
"""
from __future__ import annotations

import argparse
import json
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from tools.signalcloud_playbook.codec import load_playbook, save_playbook
from tools.signalcloud_playbook.compiler import compile_playbook_runtime
from tools.signalcloud_playbook.model import SUBJECT_KINDS, PlaybookValidationError


class UniversalPlaybookEditor(tk.Tk):
    def __init__(self, root_path: Path, document: Path | None = None) -> None:
        super().__init__()
        self.project_root = root_path.resolve()
        self.document = document
        self.title("SignalCloud Universal Playbook Lab")
        self.geometry("1180x760")
        self.minsize(900, 620)
        self.status = tk.StringVar(value="Bounded data-only graph authoring — no scripts")
        self.subject = tk.StringVar(value="unloaded")
        self.graph = tk.StringVar(value="No graph loaded")
        self._build()
        target = document or self.project_root / "content/core/playbooks/hash_dog_signal_investigate.playbook"
        if target.exists():
            self.load_path(target)

    def _build(self) -> None:
        toolbar = ttk.Frame(self, padding=6)
        toolbar.pack(fill="x")
        for label, callback in (
            ("Open", self.open_document), ("Save", self.save_document),
            ("Save As", self.save_as), ("Validate", self.validate_document),
            ("Compile Runtime", self.compile_runtime),
        ):
            ttk.Button(toolbar, text=label, command=callback).pack(side="left", padx=3)
        ttk.Label(toolbar, textvariable=self.status).pack(side="right", padx=8)

        facts = ttk.Frame(self, padding=(8, 2))
        facts.pack(fill="x")
        ttk.Label(facts, text="Graph:").pack(side="left")
        ttk.Label(facts, textvariable=self.graph).pack(side="left", padx=(4, 18))
        ttk.Label(facts, text="Universal subject:").pack(side="left")
        ttk.Label(facts, textvariable=self.subject).pack(side="left", padx=4)

        body = ttk.Panedwindow(self, orient="horizontal")
        body.pack(fill="both", expand=True, padx=8, pady=6)
        source_frame = ttk.Labelframe(body, text="Versioned .playbook JSON")
        summary_frame = ttk.Labelframe(body, text="Validated graph summary")
        body.add(source_frame, weight=3)
        body.add(summary_frame, weight=2)

        self.source = tk.Text(source_frame, wrap="none", undo=True, font=("TkFixedFont", 11))
        self.source.pack(fill="both", expand=True, padx=5, pady=5)
        self.summary = tk.Text(summary_frame, wrap="word", state="disabled", font=("TkFixedFont", 10))
        self.summary.pack(fill="both", expand=True, padx=5, pady=5)
        ttk.Label(
            self,
            text="A6a1 foundation: typed triggers/actions/effects, 64-node and 96-edge ceilings, "
                 "deterministic evaluation, future fields preserved.",
            padding=(8, 2),
        ).pack(fill="x")

    def open_document(self) -> None:
        chosen = filedialog.askopenfilename(
            initialdir=self.project_root / "content/core/playbooks",
            filetypes=[("SignalCloud Playbook", "*.playbook"), ("JSON", "*.json"), ("All", "*")],
        )
        if chosen:
            self.load_path(Path(chosen))

    def load_path(self, path: Path) -> None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            playbook = load_playbook(path)
        except (OSError, UnicodeError, json.JSONDecodeError, PlaybookValidationError) as exc:
            messagebox.showerror("Open Playbook", str(exc))
            return
        self.document = path.resolve()
        self.source.delete("1.0", "end")
        self.source.insert("1.0", json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        self._show(playbook)
        self.status.set(f"Loaded {path.name}")

    def _payload(self) -> dict[str, object]:
        value = json.loads(self.source.get("1.0", "end-1c"))
        if not isinstance(value, dict):
            raise PlaybookValidationError("playbook root must be an object")
        return value

    def _show(self, playbook) -> None:
        self.graph.set(f"{playbook.name} [{playbook.playbook_id}]")
        self.subject.set(f"{playbook.subject_kind}:{playbook.subject_archetype}")
        lines = [
            f"Mode: {playbook.mode}",
            f"Entry: {playbook.entry}",
            f"Nodes: {len(playbook.nodes)}/64",
            f"Edges: {len(playbook.edges)}/96",
            f"Max steps: {playbook.max_steps}/64",
            f"Max depth: {playbook.max_depth}/16",
            f"Point budget cost: {playbook.point_budget_cost}",
            "", "Nodes:",
        ]
        lines.extend(f"  {n.node_id}: {n.kind} {n.operation} -> {n.target}" for n in playbook.nodes)
        lines.extend(("", "Supported subject kinds:", "  " + ", ".join(sorted(SUBJECT_KINDS))))
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", "\n".join(lines))
        self.summary.configure(state="disabled")

    def validate_document(self):
        try:
            from tools.signalcloud_playbook.codec import validate_playbook
            playbook = validate_playbook(self._payload())
        except (json.JSONDecodeError, PlaybookValidationError) as exc:
            self.status.set("Validation failed")
            messagebox.showerror("Playbook Validation", str(exc))
            return None
        self._show(playbook)
        self.status.set("Validation PASS — data only and bounded")
        return playbook

    def save_document(self) -> None:
        if self.document is None:
            self.save_as()
            return
        try:
            playbook = save_playbook(self.document, self._payload())
        except (json.JSONDecodeError, PlaybookValidationError, OSError) as exc:
            messagebox.showerror("Save Playbook", str(exc))
            return
        self._show(playbook)
        self.status.set(f"Saved {self.document.name}")

    def save_as(self) -> None:
        chosen = filedialog.asksaveasfilename(
            initialdir=self.project_root / "content/user/playbooks",
            defaultextension=".playbook",
            filetypes=[("SignalCloud Playbook", "*.playbook")],
        )
        if chosen:
            self.document = Path(chosen).resolve()
            self.save_document()

    def compile_runtime(self) -> None:
        if self.validate_document() is None:
            return
        try:
            output = compile_playbook_runtime(self.project_root)
        except (OSError, ValueError, PlaybookValidationError) as exc:
            messagebox.showerror("Compile Playbooks", str(exc))
            return
        self.status.set(f"Compiled {output.relative_to(self.project_root)}")


def main(root_path: Path | None = None, argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SignalCloud Universal Playbook Lab")
    parser.add_argument("--root", type=Path, default=root_path or Path(__file__).resolve().parents[1])
    parser.add_argument("document", nargs="?", type=Path)
    args = parser.parse_args(argv)
    app = UniversalPlaybookEditor(args.root, args.document)
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
