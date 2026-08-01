from __future__ import annotations

import json
import subprocess
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from typing import Any

from tools.pcp3 import editor_branch2 as branch2
from tools.pcp3 import editor_branch2r3r1 as accepted
from tools.pcp3.brushes import BrushEditorWindow, BrushPreset
from tools.pcp3.environment_profiles import (
    ModeProfile,
    ValidationIssue,
    apply_mode_template,
    point_budget,
    profile_for,
    validate_document,
    validation_counts,
    write_validation_report,
)
from tools.pcp3.io import export_asset, slugify
from tools.pcp3.model import ENVIRONMENT_LABELS, SEMANTIC_FLAGS


class ModeAwareBrushEditorWindow(BrushEditorWindow):
    """Adds environment/semantic metadata without changing the .3dbrush schema."""

    def __init__(self, master: tk.Misc, root_path: Path, initial: BrushPreset, on_apply: Any, current_environment: str) -> None:
        self.current_environment = current_environment
        super().__init__(master, root_path, initial, on_apply)
        self.brush_semantic = tk.StringVar(value=str(self.brush.metadata.get("semantic", "generic")))
        modes = self.brush.metadata.get("environment_types", [current_environment])
        if not isinstance(modes, list):
            modes = [current_environment]
        self.brush_modes = tk.StringVar(value=", ".join(str(item) for item in modes))
        tags = self.brush.metadata.get("tags", [])
        if not isinstance(tags, list):
            tags = []
        self.brush_tags = tk.StringVar(value=", ".join(str(item) for item in tags))
        self._build_mode_metadata()

    def _build_mode_metadata(self) -> None:
        frame = ttk.LabelFrame(self, text="3D Brush mode metadata", padding=5)
        frame.pack(side="bottom", fill="x", padx=8, pady=(0, 8))
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Semantic:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(frame, textvariable=self.brush_semantic, values=tuple(SEMANTIC_FLAGS), state="readonly", width=18).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Label(frame, text="Compatible modes:").grid(row=1, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.brush_modes).grid(row=1, column=1, sticky="ew", padx=4)
        ttk.Button(frame, text="Use current mode", command=lambda: self.brush_modes.set(self.current_environment)).grid(row=1, column=2, padx=3)
        ttk.Label(frame, text="Tags:").grid(row=2, column=0, sticky="w")
        ttk.Entry(frame, textvariable=self.brush_tags).grid(row=2, column=1, columnspan=2, sticky="ew", padx=4)

    def _sync_mode_metadata(self) -> None:
        self.brush.metadata["semantic"] = self.brush_semantic.get().strip() or "generic"
        self.brush.metadata["environment_types"] = [value.strip() for value in self.brush_modes.get().split(",") if value.strip()]
        self.brush.metadata["tags"] = [value.strip() for value in self.brush_tags.get().split(",") if value.strip()]
        self.brush.metadata["editor"] = "PCP3 Branch 3 Mode Studio"

    def _load_mode_metadata(self) -> None:
        self.brush_semantic.set(str(self.brush.metadata.get("semantic", "generic")))
        modes = self.brush.metadata.get("environment_types", [self.current_environment])
        self.brush_modes.set(", ".join(str(item) for item in modes) if isinstance(modes, list) else self.current_environment)
        tags = self.brush.metadata.get("tags", [])
        self.brush_tags.set(", ".join(str(item) for item in tags) if isinstance(tags, list) else "")

    def load_selected(self) -> None:
        super().load_selected()
        self._load_mode_metadata()

    def save(self) -> None:
        self._sync_mode_metadata()
        super().save()

    def apply(self) -> None:
        self._sync_mode_metadata()
        super().apply()


class PCP3Editor(accepted.PCP3Editor):
    """Branch 3: mode-aware authoring templates, validation, and export readiness."""

    def __init__(self, root_path: Path) -> None:
        self.mode_validation_after: str | None = None
        self.mode_issues: list[ValidationIssue] = []
        self.mode_tab: ttk.Frame | None = None
        self.mode_budget_text: tk.StringVar | None = None
        self.mode_profile_text: tk.StringVar | None = None
        self.mode_validation_text: tk.StringVar | None = None
        super().__init__(root_path)
        self.title("Point Cloud Paint++ · +PCP+ · #PCP3 · Branch 3 Environment Mode Studio")
        self.document.metadata["editor_branch"] = "ISL_plus_branch3"
        self.refresh_mode_studio(full=False)
        self.update_status("Branch 3 active · Environment Mode Studio · mode templates · forgiving validation")

    # ---------- UI ----------
    def _build_toolbar(self) -> None:
        super()._build_toolbar()
        shell = getattr(self, "command_toolbar", None)
        if shell is None:
            return
        children = shell.winfo_children()
        if not children:
            return
        command_row = children[0]
        ttk.Button(command_row, text="Mode Template", command=self.prompt_apply_mode_template).pack(side="left", padx=2)
        ttk.Button(command_row, text="Validate", command=self.validate_mode_asset).pack(side="left", padx=2)

    def _build_workspace(self) -> None:
        super()._build_workspace()
        self._insert_mode_studio_tab()

    def _insert_mode_studio_tab(self) -> None:
        notebook = getattr(self, "right_notebook", None)
        if notebook is None:
            return
        tab = ttk.Frame(notebook, padding=6)
        notebook.insert(2, tab, text="Mode")
        self.mode_tab = tab
        self.mode_budget_text = tk.StringVar(master=self, value="Mode budget pending")
        self.mode_profile_text = tk.StringVar(master=self, value="")
        self.mode_validation_text = tk.StringVar(master=self, value="Not validated")

        ttk.Label(tab, textvariable=self.mode_profile_text, font=("Sans", 10, "bold"), wraplength=300).pack(fill="x")
        ttk.Label(tab, textvariable=self.mode_budget_text, wraplength=300).pack(fill="x", pady=(3, 2))
        self.mode_budget_bar = ttk.Progressbar(tab, mode="determinate", maximum=100.0)
        self.mode_budget_bar.pack(fill="x", pady=(0, 6))

        semantic_frame = ttk.LabelFrame(tab, text="Mode semantic palette", padding=4)
        semantic_frame.pack(fill="x", pady=(0, 5))
        self.mode_semantic_frame = semantic_frame

        ttk.Label(tab, text="Mode layer template", font=("Sans", 9, "bold")).pack(anchor="w")
        self.mode_layer_tree = ttk.Treeview(tab, columns=("required", "semantic", "present"), show="tree headings", height=8)
        self.mode_layer_tree.heading("#0", text="Layer")
        self.mode_layer_tree.heading("required", text="Required")
        self.mode_layer_tree.heading("semantic", text="Semantic")
        self.mode_layer_tree.heading("present", text="Present")
        self.mode_layer_tree.column("#0", width=125)
        self.mode_layer_tree.column("required", width=60, anchor="center")
        self.mode_layer_tree.column("semantic", width=90)
        self.mode_layer_tree.column("present", width=55, anchor="center")
        self.mode_layer_tree.pack(fill="x", pady=(2, 5))

        button_row = ttk.Frame(tab)
        button_row.pack(fill="x")
        ttk.Button(button_row, text="Apply template", command=self.prompt_apply_mode_template).pack(side="left", fill="x", expand=True)
        ttk.Button(button_row, text="Validate", command=self.validate_mode_asset).pack(side="left", fill="x", expand=True, padx=3)

        ttk.Label(tab, text="Mode metadata", font=("Sans", 9, "bold")).pack(anchor="w", pady=(7, 0))
        self.mode_metadata_tree = ttk.Treeview(tab, columns=("value", "kind"), show="tree headings", height=7)
        self.mode_metadata_tree.heading("#0", text="Field")
        self.mode_metadata_tree.heading("value", text="Value")
        self.mode_metadata_tree.heading("kind", text="Use")
        self.mode_metadata_tree.column("#0", width=120)
        self.mode_metadata_tree.column("value", width=125)
        self.mode_metadata_tree.column("kind", width=90)
        self.mode_metadata_tree.pack(fill="x", pady=(2, 3))
        self.mode_metadata_tree.bind("<Double-Button-1>", lambda _event: self.edit_selected_mode_field())
        field_row = ttk.Frame(tab)
        field_row.pack(fill="x")
        ttk.Button(field_row, text="Edit selected", command=self.edit_selected_mode_field).pack(side="left", fill="x", expand=True)
        ttk.Button(field_row, text="Clear", command=self.clear_selected_mode_field).pack(side="left", padx=(3, 0))

        ttk.Label(tab, text="Validation", font=("Sans", 9, "bold")).pack(anchor="w", pady=(7, 0))
        self.mode_issue_tree = ttk.Treeview(tab, columns=("severity", "message"), show="headings", height=9)
        self.mode_issue_tree.heading("severity", text="Level")
        self.mode_issue_tree.heading("message", text="Finding")
        self.mode_issue_tree.column("severity", width=65, anchor="center")
        self.mode_issue_tree.column("message", width=250)
        self.mode_issue_tree.pack(fill="both", expand=True, pady=(2, 2))
        ttk.Label(tab, textvariable=self.mode_validation_text, wraplength=300).pack(fill="x")

    # ---------- mode profile ----------
    def current_mode_profile(self) -> ModeProfile:
        return profile_for(self.document.environment_type)

    def refresh_mode_studio(self, *, full: bool = False) -> None:
        if self.mode_tab is None or not hasattr(self, "mode_layer_tree"):
            return
        profile = self.current_mode_profile()
        count = len(self.document.points)
        budget = max(1, point_budget(self.document))
        ratio = count / budget
        assert self.mode_profile_text is not None and self.mode_budget_text is not None and self.mode_validation_text is not None
        self.mode_profile_text.set(f"{profile.label}: {profile.purpose}")
        self.mode_budget_text.set(f"Point budget: {count:,} / {budget:,} ({ratio:.1%})")
        self.mode_budget_bar["value"] = min(100.0, ratio * 100.0)

        for child in self.mode_semantic_frame.winfo_children():
            child.destroy()
        for index, semantic in enumerate(profile.recommended_semantics):
            ttk.Button(
                self.mode_semantic_frame,
                text=semantic,
                command=lambda value=semantic: self.set_mode_semantic(value),
            ).grid(row=index // 3, column=index % 3, sticky="ew", padx=1, pady=1)
        for column in range(3):
            self.mode_semantic_frame.columnconfigure(column, weight=1)

        self.mode_layer_tree.delete(*self.mode_layer_tree.get_children())
        existing = {layer.name.casefold() for layer in self.document.layers}
        for template in profile.layers:
            present = template.name.casefold() in existing
            self.mode_layer_tree.insert(
                "", "end", text=template.name,
                values=("yes" if template.required else "recommended", template.semantic, "yes" if present else "no"),
            )

        self.mode_metadata_tree.delete(*self.mode_metadata_tree.get_children())
        required = set(profile.required_metadata)
        for key in profile.required_metadata + profile.recommended_metadata:
            value = self.document.metadata.get(key, "")
            self.mode_metadata_tree.insert("", "end", iid=key, text=key, values=(json.dumps(value) if value not in ("", None) else "", "required" if key in required else "future-ready"))

        if full:
            self.validate_mode_asset(show_dialog=False)

    def set_mode_semantic(self, semantic: str) -> None:
        if semantic in SEMANTIC_FLAGS:
            self.semantic.set(semantic)
            self.document.active_layer().semantic = semantic
            self.document.dirty = True
            self.refresh_layers()
            self.update_tool_hud()
            self.update_status(f"Active semantic set to {semantic} for {self.current_mode_profile().label}")

    def prompt_apply_mode_template(self) -> None:
        profile = self.current_mode_profile()
        include_optional = messagebox.askyesnocancel(
            "Apply mode template",
            f"Add the {profile.label} layer template?\n\nYes: required and optional layers\nNo: required layers only\nCancel: make no changes",
            parent=self,
        )
        if include_optional is None:
            return
        self.push_history("Apply mode template")
        created = apply_mode_template(self.document, include_optional=bool(include_optional))
        self.refresh_layers()
        self.refresh_mode_studio(full=False)
        self.finish_edit(f"{profile.label} mode template applied · {len(created)} layer(s) added or repurposed")

    def edit_selected_mode_field(self) -> None:
        selection = self.mode_metadata_tree.selection()
        if not selection:
            return
        key = selection[0]
        current = self.document.metadata.get(key, "")
        value = simpledialog.askstring("Mode metadata", f"Value for {key}:", initialvalue=str(current), parent=self)
        if value is None:
            return
        self.push_history("Mode metadata")
        stripped = value.strip()
        parsed: Any = stripped
        if stripped:
            try:
                parsed = json.loads(stripped)
            except json.JSONDecodeError:
                parsed = stripped
        self.document.metadata[key] = parsed
        self.document.dirty = True
        self.finish_edit(f"Mode metadata updated: {key}")
        self.refresh_mode_studio(full=False)

    def clear_selected_mode_field(self) -> None:
        selection = self.mode_metadata_tree.selection()
        if not selection:
            return
        key = selection[0]
        if key in self.document.metadata:
            self.push_history("Clear mode metadata")
            del self.document.metadata[key]
            self.document.dirty = True
            self.finish_edit(f"Mode metadata cleared: {key}")
            self.refresh_mode_studio(full=False)

    def validate_mode_asset(self, *, show_dialog: bool = True) -> list[ValidationIssue]:
        self.update_status("Validating mode profile and point records…")
        self.update_idletasks()
        issues = validate_document(self.document)
        self.mode_issues = issues
        self.mode_issue_tree.delete(*self.mode_issue_tree.get_children())
        for issue in issues:
            self.mode_issue_tree.insert("", "end", values=(issue.severity.upper(), issue.message))
        counts = validation_counts(issues)
        assert self.mode_validation_text is not None
        self.mode_validation_text.set(
            f"{counts.get('error', 0)} errors · {counts.get('warning', 0)} warnings · {counts.get('info', 0)} notes"
        )
        self.update_status("Mode validation complete · " + self.mode_validation_text.get())
        if show_dialog:
            lines = [f"{issue.severity.upper()}: {issue.message}" for issue in issues[:14]]
            if len(issues) > 14:
                lines.append(f"…and {len(issues) - 14} more")
            messagebox.showinfo("Mode validation", "\n".join(lines), parent=self)
        return issues

    # ---------- lifecycle hooks ----------
    def change_environment_type(self) -> None:
        previous = self.document.environment_type
        super().change_environment_type()
        if self.document.environment_type != previous:
            self.document.metadata["mode_profile"] = self.document.environment_type
            self.document.metadata["mode_profile_version"] = 1
        self.refresh_mode_studio(full=False)

    def _sync_all_from_document(self) -> None:
        super()._sync_all_from_document()
        if hasattr(self, "mode_layer_tree"):
            self.refresh_mode_studio(full=False)

    def finish_edit(self, label: str) -> None:
        super().finish_edit(label)
        if hasattr(self, "mode_layer_tree"):
            self.refresh_mode_studio(full=False)

    # ---------- export ----------
    def export_to_database(self) -> None:
        issues = self.validate_mode_asset(show_dialog=False)
        counts = validation_counts(issues)
        if counts.get("error", 0) or counts.get("warning", 0):
            proceed = messagebox.askyesno(
                "Export with validation findings?",
                f"Mode validation found {counts.get('error', 0)} errors and {counts.get('warning', 0)} warnings.\n\n"
                "The PCP3 pipeline is forgiving and can preserve unsupported future data. Continue export and include a validation sidecar?",
                parent=self,
            )
            if not proceed:
                return
        if not self.save():
            return
        try:
            self._sync_document_from_ui()
            asset_dir = export_asset(self.document, self.root_path, self.project_path, self.editor_name.get())
            validation_path = asset_dir / f"{slugify(self.document.asset_id)}.pcp3validation.json"
            write_validation_report(validation_path, self.document, issues)
            python = self.python_executable()
            subprocess.run([python, str(self.root_path / "tools" / "asset_doctor" / "asset_doctor.py"), str(self.root_path)], check=True, cwd=self.root_path)
            subprocess.run([python, str(self.root_path / "tools" / "stress_content_catalog.py"), str(self.root_path)], check=True, cwd=self.root_path)
            self.update_status(f"Exported {self.current_mode_profile().label} asset with validation sidecar")
            messagebox.showinfo(
                "Export complete",
                f"Asset exported to:\n{asset_dir}\n\nValidation sidecar:\n{validation_path.name}\n\nThe manifest and stress catalog were refreshed.",
                parent=self,
            )
        except Exception as exc:
            messagebox.showerror("Export failed", str(exc), parent=self)

    # ---------- 3D Brush Editor extension ----------
    def open_brush_editor(self) -> None:
        if self.brush_editor_window is None or not self.brush_editor_window.winfo_exists():
            self.brush_editor_window = ModeAwareBrushEditorWindow(
                self, self.root_path, self.current_brush, self.apply_3d_brush, self.document.environment_type
            )
        else:
            self.brush_editor_window.current_environment = self.document.environment_type
            self.brush_editor_window.deiconify()
            self.brush_editor_window.lift()
            self.brush_editor_window.focus_force()

    def apply_3d_brush(self, brush: BrushPreset, path: Path | None) -> None:
        super().apply_3d_brush(brush, path)
        semantic = str(brush.metadata.get("semantic", "generic"))
        compatible = brush.metadata.get("environment_types", [])
        if semantic in SEMANTIC_FLAGS:
            self.semantic.set(semantic)
        if isinstance(compatible, list) and compatible and self.document.environment_type not in compatible:
            self.update_status(
                f"3D Brush active: {brush.name} · semantic {semantic} · note: preset lists {', '.join(map(str, compatible))}"
            )
        else:
            self.update_status(f"3D Brush active: {brush.name} · mode-aware semantic {semantic}")

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
        if text is None:
            return
        text.configure(state="normal")
        text.insert("end", "Environment Mode Studio\n", "heading")
        text.insert("end", "The Mode tab shows point budget, recommended semantic buttons, layer templates, future-ready metadata, and forgiving validation.\n\n")
        text.insert("end", "Mode-aware 3D Brush Editor\n", "heading")
        text.insert("end", "Brush presets can now store a semantic, compatible environment modes, and tags. Applying a preset can switch the active semantic automatically.\n\n")
        text.configure(state="disabled")


def main(root_path: Path) -> int:
    app = PCP3Editor(root_path)
    app.mainloop()
    return 0
