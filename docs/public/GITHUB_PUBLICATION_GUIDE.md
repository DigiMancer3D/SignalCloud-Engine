# Publish SignalCloud Engine v0.1.0-alpha.1 on GitHub

The public release can be published with GitHub CLI or entirely in the browser.
The repository name selected for this release is `SignalCloud-Engine` under the
`DigiMancer3D` account.

## One-command GitHub CLI path

Install and authenticate GitHub CLI, then run from the accepted source tree:

```bash
gh auth login
./scripts/publish_github_alpha.sh DigiMancer3D/SignalCloud-Engine
```

The helper:

1. runs the strict public audit;
2. builds and verifies the deterministic tar/zip release assets;
3. initializes Git only inside the clean staged public tree;
4. creates a new public repository;
5. pushes `main` and the `v0.1.0-alpha.1` tag;
6. creates a GitHub prerelease with the release assets attached.

It refuses to overwrite an existing repository.

## Browser-only path

First build the release locally:

```bash
./scripts/build_public_alpha_release.sh
```

Then:

1. Create a new **public** repository named `SignalCloud-Engine`.
2. Do not pre-create a README, `.gitignore`, or license; the staged tree already
   contains them.
3. Open the generated `stage/SignalCloud-Engine` folder and upload its contents
   to the repository root.
4. Commit the upload to `main`.
5. Create a new release with tag `v0.1.0-alpha.1` and title
   `SignalCloud Engine v0.1.0-alpha.1`.
6. Mark it as a **pre-release**.
7. Paste the generated release-notes Markdown.
8. Attach every file from the generated `assets/` folder.
9. Publish the release.

## Final visual check

Confirm the repository front page shows:

- the MIT license;
- the public-alpha README;
- `INSTALL.md`, `CONTRIBUTING.md`, `SECURITY.md`, and third-party notices;
- no `build/`, `reports/`, `user_data/`, machine profiles, caches, private paths,
  archives, prompt history, or conversation exports;
- a visible `v0.1.0-alpha.1` prerelease with both source archives and checksums.
