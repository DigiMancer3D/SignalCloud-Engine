# SignalCloud portable core builder

## Purpose

The public SignalCloud repository intentionally does not track `content/core/`.
Older development cores could contain machine-specific paths, so publishing that
directory directly would risk exposing usernames, home directories, hostnames,
serials, workspace locations, and stale development configuration.

The portable core builder creates a deterministic public baseline locally from
repository-owned schemas, preserved inventory records, and safe defaults.

## Components

| Path | Role |
| --- | --- |
| `scripts/build_core.sh` | Stable user-facing wrapper |
| `tools/core_builder.py` | Generator, checksum receipt, and verifier |
| `content/manifest.csv` | Preserved inventory of required core paths |
| `content/core/` | Generated runtime core; ignored by Git |
| `user_data/core_builder/core_receipt.json` | Local integrity receipt; ignored by Git |

## First run

From the repository root:

```bash
chmod +x scripts/*.sh tests/*.sh
./scripts/build_core.sh
./scripts/build_core.sh --verify-only
```

Normal setup and launch scripts also call the builder automatically, including:

- setup and self-tests
- game and control panel
- Studio and +SCFS+
- Light Lab and Playbook editor
- PCP3, Showcase, Tupd, and native stress tools

An explicit first build is still recommended because it separates core-generation
errors from compiler or graphics problems.

## Commands

Build or reuse the current core:

```bash
./scripts/build_core.sh
```

Verify required files, sidecars, checksums, schema version, and privacy boundary:

```bash
./scripts/build_core.sh --verify-only
```

Delete and deterministically regenerate the core:

```bash
./scripts/build_core.sh --force
```

Use a particular Python interpreter when diagnosing environment problems:

```bash
SC_PYTHON=/usr/bin/python3 ./scripts/build_core.sh --force
```

## Generated data

The builder creates managed baseline resources for required systems, including:

- Illuminosity lights
- material and jitter maps
- audio-interference profiles
- Universal Playbooks
- SCUI control surfaces and registry data
- machine-profile and workload defaults
- runtime rules and configuration documents
- a readable SCFONT fallback
- deterministic `.asset.udata` envelopes

The exact generated inventory comes from `content/manifest.csv`. Generic safe
payloads are used only where the runtime contract requires a file but no richer
portable authored default exists.

## Privacy boundary

The builder:

- rejects `/home/...` and `C:\\Users\\...` paths;
- stores `<PROJECT_ROOT>` when a root identity is required;
- does not copy old developer paths;
- does not record usernames, hostnames, serial numbers, or benchmark profiles;
- writes its receipt under ignored `user_data/`;
- writes its generated core under ignored `content/core/`.

Before publication, verify that neither generated location is staged:

```bash
git diff --cached --name-only | grep -E \
  '^(content/core/|user_data/|build/|build-core/|reports/|release_build/)'
```

The correct result is no output.

## Integrity receipt

`user_data/core_builder/core_receipt.json` records:

- builder schema and version
- portable project-root placeholder
- generated relative paths
- file sizes
- SHA-256 hashes
- generated asset count

On a normal launch, a valid receipt allows the builder to reuse the existing core.
A stale schema, missing file, or checksum mismatch triggers replacement rather
than silently accepting a damaged baseline.

## User-authored content

Do not permanently edit generated files under `content/core/`. A forced rebuild
will replace them.

Use these boundaries instead:

```text
content/user/       managed authoring copies and custom content
user_data/          runtime state, receipts, profiles, reports, and sidecars
content/core/       generated public baseline only
```

A future custom font override should live under `content/user/fonts/` and be
selected through managed configuration rather than replacing the generated
fallback directly.

## Recovery

When verification reports a stale receipt or modified asset:

```bash
./scripts/build_core.sh --force
./scripts/build_core.sh --verify-only
```

Then rebuild and retest:

```bash
./scripts/setup_dev_environment.sh
./scripts/run_selftests.sh
```

When only the native build is stale, preserve the core and clean the build output:

```bash
rm -rf build build-core
./scripts/setup_dev_environment.sh
```

## Expected first-run sequence

```bash
chmod +x scripts/*.sh tests/*.sh
./scripts/build_core.sh
./scripts/build_core.sh --verify-only
./scripts/setup_dev_environment.sh
./scripts/run_selftests.sh
./scripts/launch_control_panel.sh
```

For KDE Wayland, the game can be launched explicitly with:

```bash
./scripts/launch_game.sh wayland
```
