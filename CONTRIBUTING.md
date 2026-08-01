# Contributing to SignalCloud Engine

The first public Alpha is a tightly integrated C++20/SDL3/OpenGL engine, ALMOND SIGNAL: LIVE TAPE test game, Python/Tk Studio, native stress tester, and data-only authoring pipeline.

## Development gate

Run from the project root:

```bash
./scripts/setup_dev_environment.sh
./scripts/run_selftests.sh
```

Changes must preserve the verified 8M resident environment baseline with the protected 4M fallback, data-only content safety, deterministic manifests, and the previous-known-good machine-profile boundary.

## Public-source gate

```bash
./scripts/audit_public_source.sh
./scripts/build_public_source_bundle.sh
```

Never commit generated build trees, runtime reports, machine profiles, saves, Python caches, private paths, credentials, prompt histories, or local development archives.

## Content and tool safety

- Content formats may preserve unknown future fields but may not contain executable Python, shell, C++, JavaScript, or unbounded expressions.
- New commands must be explicitly allowlisted in both desktop and native dispatchers.
- Malformed user/mod content must fail safely or enter quarantine.
- Preserve authored IDs, provenance, redistribution metadata, and deterministic seeds.
- Keep mouse-first operation and keyboard equivalents available.

## Scope

A public contribution should state which engine/tool/content contract it changes, the tests added, and the native acceptance still required. Compilation alone is not phase acceptance.
