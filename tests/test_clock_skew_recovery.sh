#!/usr/bin/env bash
set -euo pipefail
SOURCE_ROOT="${1:?project root is required}"
TMP_ROOT="$(mktemp -d "${TMPDIR:-/tmp}/signalcloud-clock-test.XXXXXX")"
trap 'rm -rf "$TMP_ROOT"' EXIT
mkdir -p "$TMP_ROOT/scripts" "$TMP_ROOT/build" "$TMP_ROOT/build-core"
cp "$SOURCE_ROOT/scripts/common_paths.sh" "$TMP_ROOT/scripts/common_paths.sh"
printf '%s\n' 'clock-skew probe' > "$TMP_ROOT/CMakeLists.txt"
printf '%s\n' 'stale' > "$TMP_ROOT/build/build.ninja"
printf '%s\n' 'stale' > "$TMP_ROOT/build-core/build.ninja"
touch -d '+4 hours' "$TMP_ROOT/CMakeLists.txt"
# shellcheck source=/dev/null
source "$TMP_ROOT/scripts/common_paths.sh"
sc_repair_future_timestamps "$SC_PROJECT_ROOT"
[[ "$SC_CLOCK_SKEW_REPAIRED" == 1 ]]
[[ ! -e "$TMP_ROOT/build" ]]
[[ ! -e "$TMP_ROOT/build-core" ]]
probe="$(mktemp "${TMPDIR:-/tmp}/signalcloud-clock-verify.XXXXXX")"
touch "$probe"
if [[ "$TMP_ROOT/CMakeLists.txt" -nt "$probe" ]]; then
  echo "Clock-skew repair left a future-dated source file."
  exit 1
fi
rm -f "$probe"
echo "SignalCloud future-timestamp recovery test passed."
