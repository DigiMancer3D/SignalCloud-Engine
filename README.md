# SignalCloud Engine + ALMOND SIGNAL: LIVE TAPE

SignalCloud Engine is a point-cloud game and authoring environment built around
**ALMOND SIGNAL: LIVE TAPE**. This release exposes the working engine, the game,
the engine-native stress and machine-profile system, Point Cloud Paint++, the
SignalCloud Studio tool host, +SCFS+ font authoring, Illuminosity Light Lab,
Jitter & Material Lab, Universal Playbook authoring, the 3D Environment &
Physics Showcase, and the Tupd recipe workbench.

This is a real alpha, not a finished game. Expect rough edges, evolving file
formats, Linux-focused setup, and internal names inherited from the development
track.

## What is included

- C++20 point-cloud runtime and SDL3/OpenGL applications
- ALMOND SIGNAL: LIVE TAPE Pivot 13 gameplay proof
- adaptive 8M environment profile with a protected 4M fallback
- engine-native workload/stress testing with machine-profile promotion
- thermal, memory, watchdog, interruption, recovery, and truthful final-HUD controls
- Point Cloud Paint++ layered asset authoring and native preview
- SignalCloud Studio and managed authoring tools
- +SCFS+ layered point-font authoring and native SCFONT runtime
- Illuminosity, material/jitter, audio-interference, Playbook, Showcase, and Tupd systems
- repository-safe public-source audit, deterministic release manifests, and privacy boundaries

## Tested environment

The accepted development system is Kubuntu 24 on Intel/Mesa with SDL3/OpenGL,
using both X11-oriented and Wayland-aware launch paths. Other Linux systems may
work but are not yet accepted targets. Windows and macOS are not claimed in this
alpha.

## First installation on Kubuntu/Ubuntu

Extract the release, open a terminal in the `SignalCloud-Engine` folder, then run:

```bash
chmod +x scripts/*.sh tests/*.sh
./scripts/setup_dev_environment.sh
./scripts/run_selftests.sh
./scripts/launch_control_panel.sh
```

The setup script installs missing build prerequisites with `apt`, creates a
private SignalCloud Python environment under your user data directory, and
fetches the pinned SDL3 source only when a compatible SDL3 installation is not
already available.

## Direct launch commands

```bash
./scripts/launch_game.sh auto
./scripts/launch_native_stress_gui.sh
./scripts/launch_studio.sh
./scripts/launch_pcp3.sh
./scripts/launch_scfs.sh
./scripts/launch_light_lab.sh
./scripts/launch_showcase.sh
./scripts/launch_tupd_workbench.sh
```

## Machine profile and stress workflow

1. Launch `./scripts/launch_native_stress_gui.sh`.
2. Review the run target, workload, RAM, CPU/GPU advisory limits, thermal sensor,
   and safe/fail/force-stop thresholds.
3. Run an exploratory campaign first when testing a new machine.
4. Use **Official + Promote** only when the selected target and protection policy
   are correct for that system.
5. Launch the game again. A valid active profile supplies the target resolution,
   FPS, environment budget, and protected fallback.

Thermal telemetry can be monitor-only. Profile failure and sustained force-stop
remain explicit user-controlled choices. Do not override limits beyond what is
safe for the hardware being tested.

## Public alpha verification

```bash
./scripts/check_public_release_ready.sh
./scripts/build_public_alpha_release.sh
```

The release builder creates deterministic `.tar.gz` and `.zip` source archives,
release notes, an audit report, and SHA-256 checksums. Generated builds, reports,
machine profiles, saves, caches, private paths, and conversation exports are not
included.

## Known alpha limitations

- Linux is the only supported public target in this release.
- The first full setup can take time because SDL3 may be downloaded and built.
- The PCP3 implementation still contains historical `editor_branch*.py` modules
  behind the stable public launch script.
- Physics Showcase behavior is a bounded engine proof, not a final production
  rigid-body stack.
- Public binary packages, CI-built AppImages, and Windows/macOS packages are not
  included yet.
- APIs, schemas, content formats, and save compatibility can change before beta.

## Trust, licensing, and release integrity

- `CONTENT_LICENSES.md` explains the MIT/CC0/third-party boundary.
- `content/starter/LICENSE.md` scopes public starter-pack data.
- `RELEASE_INTEGRITY.md` explains audits, manifests, and checksum verification.
- `KNOWN_LIMITATIONS.md` states what this alpha does not yet promise.
- `SUPPORT.md` explains how to report problems without exposing private data.

## License

Unless a file or managed asset declares another license, this repository's code,
tools, documentation, and original ALMOND SIGNAL: LIVE TAPE content are licensed
under the **MIT License**. See `LICENSE`.

Showcase starter assets and records marked `CC0-1.0` remain under **CC0 1.0
Universal**. See `LICENSES/CC0-1.0.txt` and each asset's provenance metadata.
External dependencies are not vendored into this source release and retain their
upstream licenses.

## Project owner

Created and directed by **DigiMancer3D** || **Z0M8I3D** || **3D**.
