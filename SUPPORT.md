# Support and issue reporting

SignalCloud Engine `v0.1.0-alpha.1` is an experimental, source-first public
alpha. Community reports are welcome, but this release does not promise
production support, stable APIs, or compatibility with every Linux system.

## Before reporting a problem

1. Read `INSTALL.md` and `KNOWN_LIMITATIONS.md`.
2. Run `./scripts/run_selftests.sh` from the extracted project root.
3. Reproduce the issue with the smallest safe set of steps.
4. Check whether the problem also occurs with a fresh user-data directory or a
   conservative machine profile.

## Helpful report information

- operating system and desktop session;
- X11 or Wayland;
- GPU/driver summary without serial numbers;
- exact launch command;
- expected behavior and actual behavior;
- the smallest relevant log excerpt;
- whether the issue affects the game, stress tester, Studio, or a specific tool.

## Protect private information

Do not post personal absolute paths, usernames, hostnames, private saves,
wallet/key data, credentials, full machine-profile bundles, or unreviewed report
archives. Replace private path prefixes with placeholders such as
`<PROJECT_ROOT>` before sharing.

Security-sensitive reports should follow `SECURITY.md` instead of being opened
as public issues.
