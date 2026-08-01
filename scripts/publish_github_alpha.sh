#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common_paths.sh
source "$SCRIPT_DIR/common_paths.sh"
ROOT="$SC_PROJECT_ROOT"
VERSION="$(tr -d '[:space:]' < "$ROOT/VERSION")"
TAG="$VERSION"
REPO="${1:-DigiMancer3D/SignalCloud-Engine}"
RELEASE_ROOT="${2:-$SC_LIVE_TAPE_PARENT/SignalCloud-Engine_${VERSION}_release}"
STAGE="$RELEASE_ROOT/stage/SignalCloud-Engine"
ASSETS="$RELEASE_ROOT/assets"

for command in git gh; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "Missing required command: $command" >&2
    exit 2
  }
done

gh auth status >/dev/null 2>&1 || {
  echo "GitHub CLI is not authenticated. Run: gh auth login" >&2
  exit 3
}

if gh repo view "$REPO" >/dev/null 2>&1; then
  echo "Refusing to overwrite an existing GitHub repository: $REPO" >&2
  echo "Use the browser guide or choose a new OWNER/REPO argument." >&2
  exit 4
fi

"$ROOT/scripts/build_public_alpha_release.sh" "$RELEASE_ROOT"

rm -rf -- "$STAGE/.git"
git -C "$STAGE" init -b main
git -C "$STAGE" config user.name "${GIT_AUTHOR_NAME:-DigiMancer3D}"
git -C "$STAGE" config user.email "${GIT_AUTHOR_EMAIL:-DigiMancer3D@users.noreply.github.com}"
git -C "$STAGE" add --all
git -C "$STAGE" commit -m "Public alpha $VERSION"
git -C "$STAGE" tag -a "$TAG" -m "SignalCloud Engine $VERSION"

gh repo create "$REPO" \
  --public \
  --source "$STAGE" \
  --remote origin \
  --push \
  --description "Point-cloud game engine, authoring tools, and ALMOND SIGNAL: LIVE TAPE public alpha"

git -C "$STAGE" push origin "$TAG"

gh release create "$TAG" \
  "$ASSETS"/* \
  --repo "$REPO" \
  --title "SignalCloud Engine $VERSION" \
  --notes-file "$ASSETS/SignalCloud-Engine_${VERSION}_RELEASE_NOTES.md" \
  --prerelease

printf '\nPublished public prerelease: %s tag %s\n' "$REPO" "$TAG"
