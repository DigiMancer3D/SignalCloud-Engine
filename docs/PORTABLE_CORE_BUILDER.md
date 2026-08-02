# SignalCloud Portable Core Builder

The public repository intentionally does not track `content/core/`. That directory is generated locally by `scripts/build_core.sh` from deterministic repository-owned defaults.

## Privacy boundary

The builder rejects `/home/...` and `C:\Users\...` paths, stores `<PROJECT_ROOT>` placeholders where a root identity is needed, and writes machine-local receipts under ignored `user_data/`. It does not copy old developer paths, hostnames, serial numbers, or benchmark profiles.

## Commands

```bash
./scripts/build_core.sh
./scripts/build_core.sh --verify-only
./scripts/build_core.sh --force
```

Setup, self-tests, the game launcher, Studio, SCFS, Light Lab, Playbook, Showcase, Tupd, PCP3, and stress launchers call the builder automatically. Managed authoring copies belong under `content/user/`; generated runtime sidecars and profiles belong under `user_data/`.
