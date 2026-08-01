# Security policy

## Supported line

Security work currently targets the active public-Alpha integration line. Historical development siblings are retained for provenance but are not separately maintained.

## Reporting

Use the repository host's private vulnerability-reporting feature when it is enabled. Do not place secrets, private machine data, exploit details, or personal paths in a public issue.

## Project safety boundaries

SignalCloud public content is data-only. The engine does not automatically execute code from imported packs, `.script` metadata, SCUI documents, Playbooks, Tupd recipes, or user assets. Unknown commands remain blocked or telemetry-only until explicitly implemented and allowlisted.

The public staging audit blocks high-confidence credential patterns and excludes generated/private state, but it is not a substitute for human review before each release.
