# Installation and first-run guide

This guide covers the `v0.1.0-alpha.1` public source release.

## Supported public target

- Kubuntu/Ubuntu-family Linux
- C++20 compiler
- CMake 3.20 or newer
- Ninja
- Python 3 with venv and Tk
- OpenGL development libraries
- X11 and/or Wayland development libraries

The setup script checks and installs the Ubuntu-family package prerequisites.

## Install

```bash
tar -xzf SignalCloud-Engine_v0.1.0-alpha.1_source.tar.gz
cd SignalCloud-Engine
chmod +x scripts/*.sh tests/*.sh
./scripts/setup_dev_environment.sh
```

A ZIP extraction works as well. The setup process stores reusable dependencies
and the Python environment in user-owned XDG data/cache locations when the
repository is not inside the original development workspace.

## Validate

```bash
./scripts/run_selftests.sh
```

The complete self-test gate validates source literals, embedded GLSL, authored
runtimes, the Asset Doctor, headless C++ tests, Python tests, Studio/SCUI smoke
surfaces, the Showcase and Tupd tools, and the stress launch bridge.

## Launch

```bash
./scripts/launch_control_panel.sh
```

The control panel is the recommended first entry. Direct commands are listed in
`README.md`.

## First machine profile

The game can start with a conservative capability fallback. To create an active
profile:

```bash
./scripts/launch_native_stress_gui.sh
```

Use an exploratory test first. Review thermal sensors and thresholds. Then run
**Official + Promote** at the resolution/FPS target you intend to use. The game
loads the active profile on its next launch.

## Common recovery commands

```bash
./scripts/show_machine_profile.sh
./scripts/recover_native_stress_runs.sh
./scripts/repair_clock_skew.sh
./scripts/repair_pcp3_workspace.sh
./scripts/run_asset_doctor.sh
```

## Clean rebuild

Generated build directories can be removed safely:

```bash
rm -rf build build-core
./scripts/setup_dev_environment.sh
```

Do not delete `content/`, `config/`, authored `.udata`/`.scfont`/`.pcp3*` files,
or other managed source content when cleaning generated state.

## Reporting a problem

Include the public release version, Linux distribution, X11/Wayland session,
GPU/driver, the command used, and the smallest relevant terminal excerpt. Do not
upload `user_data/`, machine-profile bundles, private paths, keys, tokens, or
personal save data.


## Portable core builder

A public clone generates its privacy-safe `content/core` locally. Run `./scripts/build_core.sh`, or use the normal setup/launch scripts, which invoke it automatically. See `docs/PORTABLE_CORE_BUILDER.md`.
