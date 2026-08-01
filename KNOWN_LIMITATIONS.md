# Known limitations — v0.1.0-alpha.1

This release is a public alpha and intentionally exposes systems that are still
being integrated.

- The accepted target is Kubuntu/Ubuntu-family Linux. Windows and macOS are not
  claimed as supported platforms in this release.
- X11 and Wayland-aware launch paths are included, but behavior may vary by
  compositor, driver, and distribution package versions.
- File formats, authoring schemas, command IDs, and tool layouts may change
  before beta. Keep backups of authored content.
- Machine profiles are hardware-, resolution-, workload-, and content-specific.
  A profile from another machine should not be treated as validated locally.
- The native stress tester can intentionally create heavy CPU, GPU, memory, and
  thermal load. Review its limits before starting an official campaign.
- The game is a playable engine proof, not a content-complete campaign.
- Multiplayer, final persistence, complete enemy/weapon rosters, polished audio,
  and full release-platform packaging remain later work.
- Imported content is not automatically safe to redistribute. Verify every
  asset's license before publishing a pack or fork.
- Public source checksums provide integrity evidence, not identity signing. See
  `RELEASE_INTEGRITY.md`.

Reproducible defects are welcome through the repository issue templates.
