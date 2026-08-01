# Public release audit tool

`tools/public_release_audit.py` is the A10 public-source staging authority.

## Design rules

- The input source tree is read-only.
- Output must be outside the source root.
- Exclusions come from `config/public_release_policy.json`.
- High-confidence credential matches are withheld and block release.
- UTF-8 source text receives project/home path normalization only in the stage.
- Generated objects, libraries, caches, reports, saves, and machine profiles are prohibited.
- The public manifest does not hash itself or the two generated audit reports.
- Tar and ZIP metadata is normalized for deterministic output.
- `--strict-release` fails when a required document, license, privacy boundary, or content gate is unresolved.

## Direct use

```bash
python3 tools/public_release_audit.py . \
  --output /tmp/signalcloud-public \
  --archive /tmp/SignalCloud-Engine_source.tar.gz \
  --zip /tmp/SignalCloud-Engine_source.zip \
  --replace \
  --strict-release
```

The generated JSON supports release automation. The Markdown report is the human acceptance record.
