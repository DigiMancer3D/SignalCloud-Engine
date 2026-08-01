# SignalCloud Engine — ALMOND SIGNAL: LIVE TAPE (alpha)

Fast summary
- A C++20 point‑cloud game engine and authoring toolkit with Python management scripts and editors.
- Ships ALMOND SIGNAL: LIVE TAPE gameplay proof, Point Cloud Paint++ (PCP3) authoring, SCFONT font runtime, studio tools, and engine‑native stress/profile utilities.
- Linux‑focused alpha (tested on Kubuntu 24 / Intel + Mesa). Not production‑ready.

Quick highlights
- Core runtime: C++20 engine (rendering, physics, AI/playbooks, audio interference, materials).
- Authoring: Point Cloud Paint++ examples (.pcp3), SignalCloud Studio tooling, layered SCFONT support.
- Profiles & stress: native machine‑profile and workload stress tools with protected fallbacks.
- Deterministic release tooling and audit‑ready source release manifests.

Requirements
- Linux (Kubuntu 24 recommended). SDL3/OpenGL supported; SDL3 is fetched automatically as a fallback if not installed.
- Build tools: CMake >= 3.20, modern C++ toolchain (g++/clang++ supporting C++20), Python 3 used by scripts.
- See INSTALL.md for full environment details and troubleshooting.

Quick start (from a cloned repo)
```bash
# make authoring scripts executable and set up a dev environment (installs apt packages where needed)
chmod +x scripts/*.sh tests/*.sh
./scripts/setup_dev_environment.sh

# run repository self-tests
./scripts/run_selftests.sh

# launch the control panel / studio / quick demos
./scripts/launch_control_panel.sh
./scripts/launch_game.sh auto
./scripts/launch_studio.sh
```

Build from source (CMake)
```bash
mkdir build && cd build
cmake -S .. -B .
cmake --build . -- -j$(nproc)
# GUI targets require SDL3 (auto-fetched if not present and SC_FETCH_SDL3=ON)
```

Useful direct launch scripts (in repo root)
- ./scripts/launch_game.sh auto
- ./scripts/launch_native_stress_gui.sh
- ./scripts/launch_studio.sh
- ./scripts/launch_pcp3.sh
- ./scripts/launch_scfs.sh
- ./scripts/launch_light_lab.sh
- ./scripts/launch_showcase.sh
- ./scripts/launch_tupd_workbench.sh

What you’ll find in the source
- C++ core engine under engine/ (render, world, physics, AI/playbook, materials, audio, ui)
- Executables under app/ (diagnostics, game, previews, stress, showcase)
- Authoring examples under examples/pcp3
- Deterministic packaging tooling and release integrity docs

Documentation & support
- INSTALL.md — setup, first launch, and troubleshooting
- docs/user — tool and gameplay guides
- CONTRIBUTING.md — how to contribute
- SECURITY.md — vulnerability reporting guidance
- RELEASE_INTEGRITY.md, CONTENT_LICENSES.md, THIRD_PARTY_NOTICES.md

Alpha limitations (short)
- Linux-only in this alpha (Kubuntu 24 tested).
- File formats and internal APIs may change before beta.
- Windows/macOS binaries and CI-built AppImages are not included yet.

License
- Code and engine tools: MIT (see LICENSE).
- Starter showcase assets marked CC0 remain CC0 (see LICENSES/).

Contact / project lead
- Maintained by DigiMancer3D — see SUPPORT.md for problem reports and privacy guidance.
