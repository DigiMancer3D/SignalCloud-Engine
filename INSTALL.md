# SignalCloud Engine installation and first-run guide

This guide covers the public portable-core source line prepared for
`v0.1.0-alpha.2`. The last published historical release is
`v0.1.0-alpha.1`.

## Supported public target

SignalCloud currently supports Linux source builds. The portable-core recovery
has been validated on CachyOS/Arch-family KDE Wayland and the original development
line was validated on Kubuntu 24 with SDL3/OpenGL.

Required capabilities:

- C++20 compiler
- CMake 3.20 or newer
- Ninja
- Python 3 with `venv` support and Tk
- OpenGL development files
- X11 and/or Wayland development files
- Git and standard archive utilities

## 1. Install prerequisites

### CachyOS / Arch Linux

```bash
sudo pacman -S --needed \
  base-devel cmake ninja python tk git pkgconf mesa \
  libx11 libxext libxrandr libxcursor libxi libxfixes libxss libxtst \
  libxkbcommon wayland wayland-protocols libdecor
```

The setup script does not use Pacman automatically. Install these packages before
running setup.

### Kubuntu / Ubuntu

```bash
sudo apt update
sudo apt install -y \
  build-essential cmake ninja-build python3 python3-venv python3-tk \
  git pkg-config tar libgl1-mesa-dev \
  libx11-dev libxext-dev libxrandr-dev libxcursor-dev libxi-dev \
  libxfixes-dev libxss-dev libxtst-dev libxkbcommon-dev \
  libwayland-dev wayland-protocols libdecor-0-dev
```

The setup script can install missing Ubuntu-family packages when `dpkg-query` and
`apt-get` are available.

## 2. Obtain the source

Using Git:

```bash
git clone https://github.com/DigiMancer3D/SignalCloud-Engine.git
cd SignalCloud-Engine
```

A source ZIP or TAR archive works as well. Extract it and open a terminal inside
the `SignalCloud-Engine` directory.

## 3. Prepare the scripts

```bash
chmod +x scripts/*.sh tests/*.sh
```

The scripts use Bash internally. They can be launched from Fish, Zsh, or another
interactive shell because each script has its own Bash shebang.

## 4. Generate the privacy-safe runtime core

A public clone intentionally has no tracked `content/core/` directory. Generate
it locally:

```bash
./scripts/build_core.sh
```

Verify it:

```bash
./scripts/build_core.sh --verify-only
```

Generated locations:

```text
content/core/
user_data/core_builder/core_receipt.json
```

Both are machine-local and ignored by Git. The receipt records relative paths and
checksums without storing the user's home directory, username, hostname, serial
number, or absolute project path.

## 5. Build the engine and tools

```bash
./scripts/setup_dev_environment.sh
```

The script:

1. verifies required commands;
2. creates or reuses the private SignalCloud Python environment;
3. generates or verifies the portable core;
4. compiles Illuminosity, material, audio, and Playbook runtimes;
5. validates SCFONT and managed assets;
6. configures CMake/Ninja;
7. reuses cached SDL3 or fetches the pinned fallback;
8. builds the game, stress system, PCP3 preview, Showcase, Tupd preview, and tests.

## 6. Run the acceptance gate

```bash
./scripts/run_selftests.sh
```

Do not treat the installation as accepted until this completes successfully.
Warnings may be present, but the final Python, native CTest, authored-runtime,
SCUI/Tk, Asset Doctor, and public-source gates must pass.

## 7. Launch

Recommended launcher:

```bash
./scripts/launch_control_panel.sh
```

Game launch with automatic display backend selection:

```bash
./scripts/launch_game.sh auto
```

Explicit KDE Wayland launch:

```bash
./scripts/launch_game.sh wayland
```

Explicit X11 launch:

```bash
./scripts/launch_game.sh x11
```

## Direct tools

```bash
./scripts/launch_native_stress_gui.sh
./scripts/launch_studio.sh
./scripts/launch_pcp3.sh
./scripts/launch_scfs.sh
./scripts/launch_light_lab.sh
./scripts/launch_playbook_editor.sh
./scripts/launch_showcase.sh
./scripts/launch_tupd_workbench.sh
```

## Content packs

Inspect before installation:

```bash
./scripts/inspect_content_pack.sh /path/to/Pack_Name.scpack.zip
```

Install atomically:

```bash
./scripts/install_content_pack.sh /path/to/Pack_Name.scpack.zip
```

Validate afterward:

```bash
./scripts/run_asset_doctor.sh
```

The pack filename must end exactly in `.scpack.zip`.

## Portable-core recovery

Verify only:

```bash
./scripts/build_core.sh --verify-only
```

Force a deterministic rebuild:

```bash
./scripts/build_core.sh --force
```

A forced rebuild deletes and recreates generated `content/core/`. It does not
replace managed user content under `content/user/`.

If a custom core file was intentionally edited, move the authored replacement to
`content/user/` before forcing a rebuild. Generated core content is not an
appropriate permanent authoring location.

## Clean native rebuild

```bash
rm -rf build build-core
./scripts/setup_dev_environment.sh
```

Do not delete `content/user/`, managed source assets, custom SCFONT files, or
machine profiles unless you intentionally want to reset them.

## Machine profile

The game can start from a conservative fallback. To characterize the machine:

```bash
./scripts/launch_native_stress_gui.sh
```

Run an exploratory test first. Review thermal sensors and policy. Use
**Official + Promote** only after the selected resolution/FPS target and safety
limits are confirmed. The next game launch consumes the active profile.

## Troubleshooting

### Missing `content/core` or missing `.slight`, `.scfont`, or `.scui`

```bash
./scripts/build_core.sh --force
./scripts/build_core.sh --verify-only
```

### Stale or interrupted build

```bash
rm -rf build build-core
./scripts/setup_dev_environment.sh
```

### Content validation problems

```bash
./scripts/run_asset_doctor.sh
```

### Other recovery helpers

```bash
./scripts/show_machine_profile.sh
./scripts/recover_native_stress_runs.sh
./scripts/repair_clock_skew.sh
./scripts/repair_pcp3_workspace.sh
```

## Reporting a problem

Include:

- SignalCloud version or commit
- Linux distribution
- X11 or Wayland session
- GPU and driver
- exact command used
- smallest relevant terminal excerpt

Do not upload `user_data/`, machine-profile bundles, private paths, credentials,
tokens, browser sessions, or personal save data.
