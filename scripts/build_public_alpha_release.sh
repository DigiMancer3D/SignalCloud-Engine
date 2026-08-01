#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
PYTHON="$SC_PYTHON"
[[ -x "$PYTHON" ]] || PYTHON="$(command -v python3)"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
BASE="SignalCloud-Engine_${VERSION}"
RELEASE_ROOT="${1:-$SC_LIVE_TAPE_PARENT/${BASE}_release}"
STAGE_PARENT="$RELEASE_ROOT/stage"
ASSETS="$RELEASE_ROOT/assets"
TAR="$ASSETS/${BASE}_source.tar.gz"
ZIP="$ASSETS/${BASE}_source.zip"

rm -rf -- "$RELEASE_ROOT"
mkdir -p -- "$ASSETS"

"$PYTHON" "$ROOT/tools/public_release_audit.py" "$ROOT" \
  --output "$STAGE_PARENT" \
  --archive "$TAR" \
  --zip "$ZIP" \
  --replace \
  --strict-release

STAGE="$STAGE_PARENT/SignalCloud-Engine"
cp "$ROOT/RELEASE_NOTES_v0.1.0-alpha.1.md" "$ASSETS/${BASE}_RELEASE_NOTES.md"
cp "$ROOT/SignalCloud-Engine_v0.1.0-alpha.1_VALIDATION_REPORT.md" "$ASSETS/${BASE}_VALIDATION_REPORT.md"
cp "$STAGE/PUBLIC_SOURCE_AUDIT.md" "$ASSETS/${BASE}_PUBLIC_SOURCE_AUDIT.md"
cp "$STAGE/PUBLIC_SOURCE_AUDIT.json" "$ASSETS/${BASE}_PUBLIC_SOURCE_AUDIT.json"
cp "$STAGE/PUBLIC_SOURCE_MANIFEST.sha256" "$ASSETS/${BASE}_PUBLIC_SOURCE_MANIFEST.sha256"

"$PYTHON" - "$ASSETS" "$VERSION" <<'PY'
from __future__ import annotations
import hashlib, json, sys
from pathlib import Path
assets=Path(sys.argv[1])
version=sys.argv[2]
items=[]
for path in sorted(assets.iterdir(), key=lambda p:p.name.casefold()):
    if not path.is_file() or path.name in {"SHA256SUMS.txt", "SignalCloud-Engine_"+version+"_RELEASE_MANIFEST.json"}:
        continue
    items.append({"name":path.name,"bytes":path.stat().st_size,"sha256":hashlib.sha256(path.read_bytes()).hexdigest()})
manifest={
    "schema_version":1,
    "project":"SignalCloud Engine + ALMOND SIGNAL: LIVE TAPE",
    "version":version,
    "release_type":"public source alpha",
    "license":"MIT",
    "asset_exceptions":["CC0-1.0 where declared"],
    "files":items,
}
out=assets/f"SignalCloud-Engine_{version}_RELEASE_MANIFEST.json"
out.write_text(json.dumps(manifest,indent=2,sort_keys=True)+"\n",encoding="utf-8")
PY

(
  cd "$ASSETS"
  sha256sum -- * | grep -v '  SHA256SUMS.txt$' > SHA256SUMS.txt
)

VERIFY="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-public-release-verify.XXXXXX")"
trap 'rm -rf -- "$VERIFY"' EXIT
mkdir -p "$VERIFY/tar" "$VERIFY/zip"
tar -xzf "$TAR" -C "$VERIFY/tar"
"$PYTHON" -m zipfile -e "$ZIP" "$VERIFY/zip"
(
  cd "$VERIFY/tar/SignalCloud-Engine"
  sha256sum -c PUBLIC_SOURCE_MANIFEST.sha256 >/dev/null
)
(
  cd "$VERIFY/zip/SignalCloud-Engine"
  sha256sum -c PUBLIC_SOURCE_MANIFEST.sha256 >/dev/null
)

printf '\nSignalCloud public alpha release built successfully.\n'
printf 'Version : %s\n' "$VERSION"
printf 'Stage   : %s\n' "$STAGE"
printf 'Assets  : %s\n' "$ASSETS"
printf 'Tarball : %s\n' "$TAR"
printf 'ZIP     : %s\n' "$ZIP"
printf 'Checks  : %s\n' "$ASSETS/SHA256SUMS.txt"
