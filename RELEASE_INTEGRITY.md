# Release integrity and verification

SignalCloud Engine public source releases include several independent pieces of
integrity evidence.

## Included evidence

- `PUBLIC_SOURCE_AUDIT.md` and `.json` describe the public-stage audit result.
- `PUBLIC_SOURCE_MANIFEST.sha256` records the SHA-256 digest of each published
  source file.
- Release assets include `SHA256SUMS.txt` and a release manifest describing the
  downloadable files.
- The source ZIP and tar.gz are built from the same audited public stage.

## Verify an extracted source archive

From inside the extracted `SignalCloud-Engine` directory:

```bash
sha256sum -c PUBLIC_SOURCE_MANIFEST.sha256
```

Every listed file should report `OK`.

## Verify downloaded release assets

Place the release files and `SHA256SUMS.txt` in the same directory, then run:

```bash
sha256sum -c SHA256SUMS.txt
```

## What checksums do and do not prove

A matching SHA-256 digest shows that the file matches the referenced checksum.
It does not, by itself, prove who published the checksum. Obtain checksums from
the official repository release page or another trusted channel.

This alpha does not claim a separate cryptographic signing key or signed binary
installer. Any future signed release will document its signing method and
verification steps explicitly.
