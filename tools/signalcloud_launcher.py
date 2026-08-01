#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from machine_profile_manager import status_text


class Launcher(tk.Tk):
    def __init__(self, root: Path) -> None:
        super().__init__()
        self.root_path = root
        self.title("ALMOND SIGNAL: LIVE TAPE — ISL+ Session Launcher")
        self.geometry("980x700")
        self.minsize(780, 540)
        self.backend = tk.StringVar(value="auto")
        self.points = tk.StringVar(value="profile")
        self.session = tk.StringVar(value="game")
        self.status = tk.StringVar(value="A9a1 machine-profile foundation, game, stress, seven-tool Studio, Tupd, Showcase, and +SCFS+ paths ready")

        top = ttk.Frame(self, padding=12)
        top.pack(fill="x")
        ttk.Label(top, text="ALMOND SIGNAL: LIVE TAPE", font=("Sans", 16, "bold")).pack(anchor="w")
        ttk.Label(top, text="SignalCloud Engine — Game / Stress / Studio Authoring Tools").pack(anchor="w")

        choice = ttk.LabelFrame(self, text="Loadup option", padding=10)
        choice.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Radiobutton(choice, text="Play the game", variable=self.session, value="game").grid(
            row=0, column=0, sticky="w", padx=6
        )
        ttk.Radiobutton(choice, text="Engine-Native Stress Test", variable=self.session, value="native").grid(
            row=0, column=1, sticky="w", padx=6
        )
        ttk.Radiobutton(choice, text="Point Cloud Paint++ (+PCP+)", variable=self.session, value="pcp3").grid(
            row=0, column=2, sticky="w", padx=6
        )
        ttk.Radiobutton(choice, text="SignalCloud Studio Hub", variable=self.session, value="studio").grid(
            row=1, column=0, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Radiobutton(choice, text="Illuminosity Light Lab", variable=self.session, value="light-lab").grid(
            row=1, column=1, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Radiobutton(choice, text="SignalCloud Font Studio (+SCFS+)", variable=self.session, value="font-studio").grid(
            row=1, column=2, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Radiobutton(choice, text="3D Environment & Physics Showcase", variable=self.session, value="showcase").grid(
            row=2, column=0, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Radiobutton(choice, text="Tupd Authoring Workbench", variable=self.session, value="tupd-workbench").grid(
            row=2, column=1, columnspan=2, sticky="w", padx=6, pady=(6, 0)
        )
        ttk.Button(choice, text="Launch selected", command=self.launch_selected).grid(row=0, column=3, padx=10)
        ttk.Button(choice, text="Refresh content catalog", command=self.refresh_catalog).grid(row=0, column=4, padx=4)
        ttk.Label(choice, textvariable=self.status).grid(row=3, column=0, columnspan=5, sticky="w", padx=6, pady=(8, 0))

        controls = ttk.LabelFrame(self, text="Game launch settings", padding=10)
        controls.pack(fill="x", padx=12, pady=(0, 8))
        ttk.Label(controls, text="Video backend:").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            controls, textvariable=self.backend, values=("auto", "x11", "wayland"),
            state="readonly", width=10
        ).grid(row=0, column=1, padx=6)
        ttk.Label(controls, text="Initial points:").grid(row=0, column=2, sticky="w", padx=(12, 0))
        ttk.Combobox(
            controls, textvariable=self.points,
            values=("profile", "adaptive", "100000", "500000", "1000000", "2000000", "3000000", "4000000", "8000000"),
            state="readonly", width=12
        ).grid(row=0, column=3, padx=6)
        ttk.Button(controls, text="Launch Game", command=self.launch_game).grid(row=0, column=4, padx=4)
        ttk.Button(controls, text="Engine-Native Stress", command=self.launch_native_stress).grid(row=0, column=5, padx=4)
        ttk.Button(controls, text="Point Cloud Paint++", command=self.launch_pcp3).grid(row=0, column=6, padx=4)
        ttk.Button(controls, text="Studio Hub", command=self.launch_studio).grid(row=1, column=4, padx=4, pady=(6, 0))
        ttk.Button(controls, text="Light Lab", command=self.launch_light_lab).grid(row=1, column=5, padx=4, pady=(6, 0))
        ttk.Button(controls, text="Font Studio", command=self.launch_font_studio).grid(row=1, column=6, padx=4, pady=(6, 0))
        ttk.Button(controls, text="3D Showcase", command=self.launch_showcase).grid(row=2, column=4, padx=4, pady=(6, 0), sticky="ew")
        ttk.Button(controls, text="Tupd Workbench", command=self.launch_tupd_workbench).grid(row=2, column=5, padx=4, pady=(6, 0), sticky="ew")
        ttk.Button(controls, text="Build / Repair Native", command=self.build_native_targets).grid(row=2, column=6, padx=4, pady=(6, 0))

        reports = ttk.Frame(self, padding=(12, 0, 12, 8))
        reports.pack(fill="x")
        for text, command in (
            ("Quick Validation", self.tests),
            ("PCP3 Validation", self.pcp3_tests),
            ("Full Regression…", self.full_tests),
            ("Capabilities", lambda: self.show_file("reports/capability_report.txt")),
            ("Budget", lambda: self.show_file("reports/pivot13_budget.txt")),
            ("Layout", lambda: self.show_file("reports/pivot13_layout.txt")),
            ("Stress Catalog", lambda: self.show_file("reports/stress_content_catalog.md")),
            ("Machine Profile", self.show_machine_profile),
            ("Combat Log", lambda: self.show_file("reports/combat_trace.csv")),
            ("Economy Log", lambda: self.show_file("reports/economy_trace.csv")),
        ):
            ttk.Button(reports, text=text, command=command).pack(side="left", padx=3)

        self.output = tk.Text(self, wrap="word", padx=10, pady=10)
        self.output.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        self.write(
            "The obsolete compatibility StressLab launch path has been removed.\n"
            "The Engine-Native Stress Test uses the actual SignalCloud rooms, renderer, water, lighting,\n"
            "enemies, kiosks, AR, and doorway-preview systems. The content catalog is still refreshed\n"
            "before testing so newly added data records are discovered and classified.\n\n"
        )

    def write(self, text: str) -> None:
        self.output.insert("end", text)
        self.output.see("end")

    def show_machine_profile(self) -> None:
        self.write("\n" + status_text(self.root_path) + "\n")

    def launch_selected(self) -> None:
        if self.session.get() == "native":
            self.launch_native_stress()
        elif self.session.get() == "pcp3":
            self.launch_pcp3()
        elif self.session.get() == "studio":
            self.launch_studio()
        elif self.session.get() == "light-lab":
            self.launch_light_lab()
        elif self.session.get() == "font-studio":
            self.launch_font_studio()
        elif self.session.get() == "showcase":
            self.launch_showcase()
        elif self.session.get() == "tupd-workbench":
            self.launch_tupd_workbench()
        else:
            self.launch_game()

    def launch_game(self) -> None:
        if not (self.root_path / "build" / "almond_signal_live_tape").exists():
            messagebox.showerror("Not built", "Run setup_dev_environment.sh first.")
            return
        args = [str(self.root_path / "scripts" / "launch_game.sh"), self.backend.get()]
        if self.points.get() not in {"profile", "adaptive"}:
            args.append(self.points.get())
        subprocess.Popen(args, cwd=self.root_path)
        self.write(f"Launched game: backend={self.backend.get()} points={self.points.get()}\n")

    def launch_native_stress(self) -> None:
        binary = self.root_path / "build" / "almond_signal_native_stress"
        if not binary.exists():
            messagebox.showerror(
                "Not built",
                "Run setup_dev_environment.sh first. The engine-native stress target was not found.",
            )
            return
        try:
            subprocess.Popen([str(self.root_path / "scripts" / "launch_native_stress_gui.sh")], cwd=self.root_path)
            self.write("Opening engine-native stress control using the real SignalCloud renderer and game systems…\n")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))


    def launch_pcp3(self) -> None:
        preview = self.root_path / "build" / "almond_signal_pcp_preview"
        try:
            subprocess.Popen([str(self.root_path / "scripts" / "launch_pcp3.sh")], cwd=self.root_path)
            if preview.exists():
                self.write("Opening Point Cloud Paint++ with the optional native preview available…\n")
            else:
                self.write(
                    "Opening Point Cloud Paint++ in authoring-only mode. "
                    "Build native targets later only when 3D preview is needed.\n"
                )
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))

    def launch_studio(self) -> None:
        try:
            subprocess.Popen([str(self.root_path / "scripts" / "launch_studio.sh")], cwd=self.root_path)
            self.write("Opening the canonical SignalCloud Studio tool host…\n")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))

    def build_native_targets(self) -> None:
        script = self.root_path / "scripts" / "setup_dev_environment.sh"
        try:
            subprocess.Popen(["konsole", "-e", str(script)], cwd=self.root_path)
            self.write("Opened native build/repair in Konsole. Studio authoring remains available while it runs.\n")
        except OSError as exc:
            messagebox.showerror("Build launch failed", str(exc))


    def launch_light_lab(self) -> None:
        try:
            subprocess.Popen(
                [str(self.root_path / "scripts" / "launch_light_lab.sh")],
                cwd=self.root_path,
            )
            self.write("Opening Illuminosity Light Lab through the canonical Studio context…\n")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))

    def launch_font_studio(self) -> None:
        try:
            subprocess.Popen(
                [str(self.root_path / "scripts" / "launch_scfs.sh")],
                cwd=self.root_path,
            )
            self.write("Opening integrated SignalCloud Font Studio (+SCFS+)…\n")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))

    def launch_showcase(self) -> None:
        try:
            subprocess.Popen(
                [str(self.root_path / "scripts" / "launch_showcase.sh")],
                cwd=self.root_path,
            )
            self.write("Opening 3D Environment & Physics Showcase through the canonical Studio context…\n")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))


    def launch_tupd_workbench(self) -> None:
        try:
            subprocess.Popen(
                [str(self.root_path / "scripts" / "launch_tupd_workbench.sh")],
                cwd=self.root_path,
            )
            self.write("Opening A8a3r1 Tupd Workbench with responsive actions, fitted graph validation, world-space native inspection, and isolated test inventory…\n")
        except OSError as exc:
            messagebox.showerror("Launch failed", str(exc))

    def refresh_catalog(self) -> None:
        python = sys.executable
        try:
            subprocess.run(
                [python, str(self.root_path / "tools" / "asset_doctor" / "asset_doctor.py"), str(self.root_path)],
                cwd=self.root_path, check=True,
            )
            result = subprocess.run(
                [python, str(self.root_path / "tools" / "stress_content_catalog.py"), str(self.root_path)],
                cwd=self.root_path, check=True, text=True, capture_output=True,
            )
            self.write(f"Content catalog refreshed: {result.stdout.strip()}\n")
            self.show_file("reports/stress_content_catalog.md")
        except subprocess.CalledProcessError as exc:
            messagebox.showerror("Catalog failed", str(exc))

    def tests(self) -> None:
        self.write("Running quick native route/launcher validation…\n")
        subprocess.Popen(
            ["konsole", "-e", str(self.root_path / "scripts" / "run_native_stress_quick_tests.sh")],
            cwd=self.root_path,
        )

    def pcp3_tests(self) -> None:
        self.write("Running Point Cloud Paint++ format/editor/loader validation…\n")
        subprocess.Popen(
            ["konsole", "-e", str(self.root_path / "scripts" / "run_pcp3_quick_tests.sh")],
            cwd=self.root_path,
        )

    def full_tests(self) -> None:
        if not messagebox.askyesno(
            "Full regression suite",
            "This rebuilds and runs all Pivot 0–13 tests and can heavily use the machine for several minutes. Continue?",
        ):
            return
        self.write("Running the full regression suite in Konsole…\n")
        subprocess.Popen(["konsole", "-e", str(self.root_path / "scripts" / "run_selftests.sh")], cwd=self.root_path)

    def show_file(self, relative: str) -> None:
        path = self.root_path / relative
        self.output.delete("1.0", "end")
        if path.exists():
            self.write(path.read_text(encoding="utf-8", errors="replace"))
        else:
            self.write(f"Not generated yet: {path}\n")


def main() -> int:
    root = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()
    Launcher(root).mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
