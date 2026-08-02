#!/usr/bin/env bash
# Shared path resolution and clock-safety helpers for SignalCloud shell tools.
# This file is sourced; it does not enable or alter shell options.

SC_SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SC_PROJECT_ROOT="$(cd "$SC_SCRIPT_DIR/.." && pwd)"
SC_LIVE_TAPE_PARENT="$(dirname "$SC_PROJECT_ROOT")"
SC_SIGNALCLOUD_ROOT="$(dirname "$SC_LIVE_TAPE_PARENT")"
SC_GAME_ENGINE_ROOT="$(dirname "$SC_SIGNALCLOUD_ROOT")"

# The private development workspace nests the project beneath:
#   SignalCloud Engine/Almond Signal: Live Tape/<project>
# Public source extractions are normally standalone. In that layout, keep all
# reusable state in user-owned XDG locations rather than guessing parent paths.
if [[ "$(basename "$SC_LIVE_TAPE_PARENT")" == "Almond Signal: Live Tape" ]]; then
  SC_LAYOUT_MODE="development-workspace"
  SC_SHARED_DEPS="$SC_SIGNALCLOUD_ROOT/.signalcloud_shared_deps"
  SC_SHARED_ENVS="$SC_SIGNALCLOUD_ROOT/.signalcloud_envs"
else
  SC_LAYOUT_MODE="standalone-public"
  SC_CACHE_HOME="${XDG_CACHE_HOME:-${HOME:?HOME is not set}/.cache}"
  SC_DATA_HOME="${XDG_DATA_HOME:-${HOME:?HOME is not set}/.local/share}"
  SC_SHARED_DEPS="$SC_CACHE_HOME/signalcloud-engine/deps"
  SC_SHARED_ENVS="$SC_DATA_HOME/signalcloud-engine/envs"
fi
SC_PYTHON_ENV="$SC_SHARED_ENVS/tools-py3"

# Avoid unbounded Ninja fan-out on high-thread-count systems and CI containers.
if [[ -z "${SC_BUILD_JOBS:-}" ]]; then
  SC_BUILD_JOBS="$(nproc 2>/dev/null || printf '4')"
  if ((SC_BUILD_JOBS > 8)); then SC_BUILD_JOBS=8; fi
  if ((SC_BUILD_JOBS < 1)); then SC_BUILD_JOBS=1; fi
fi
export SC_BUILD_JOBS

# Python's venv rejects ':' because it is the Unix PATH separator.
if [[ "$SC_PYTHON_ENV" == *:* ]]; then
  SC_DATA_HOME="${XDG_DATA_HOME:-${HOME:?HOME is not set}/.local/share}"
  SC_PYTHON_ENV="$SC_DATA_HOME/signalcloud-engine/envs/tools-py3"
fi
SC_PYTHON="$SC_PYTHON_ENV/bin/python"

sc_repair_future_timestamps() {
  local root="${1:-$SC_PROJECT_ROOT}"
  local probe
  local future_file
  SC_CLOCK_SKEW_REPAIRED=0

  probe="$(mktemp "${TMPDIR:-/tmp}/signalcloud-clock.XXXXXX")"
  touch "$probe"

  future_file="$(find "$root"     -path "$root/build" -prune -o     -path "$root/build-core" -prune -o     -path "$root/.venv" -prune -o     -path "$root/.deps" -prune -o     -path "$root/arch" -prune -o     -type f -newer "$probe" -print -quit 2>/dev/null || true)"

  if [[ -n "$future_file" ]]; then
    echo "Detected source timestamps newer than this machine's clock."
    echo "First future-dated file: $future_file"
    find "$root"       -path "$root/build" -prune -o       -path "$root/build-core" -prune -o       -path "$root/.venv" -prune -o       -path "$root/.deps" -prune -o       -path "$root/arch" -prune -o       -type f -exec touch -r "$probe" {} +
    rm -rf "$root/build" "$root/build-core"
    SC_CLOCK_SKEW_REPAIRED=1
    echo "Normalized project timestamps and removed stale Ninja/CMake caches."
  fi

  rm -f "$probe"
  export SC_CLOCK_SKEW_REPAIRED
}

sc_force_normalize_timestamps() {
  local root="${1:-$SC_PROJECT_ROOT}"
  local probe
  probe="$(mktemp "${TMPDIR:-/tmp}/signalcloud-clock.XXXXXX")"
  touch "$probe"
  find "$root"     -path "$root/build" -prune -o     -path "$root/build-core" -prune -o     -path "$root/.venv" -prune -o     -path "$root/.deps" -prune -o     -path "$root/arch" -prune -o     -type f -exec touch -r "$probe" {} +
  rm -f "$probe"
  rm -rf "$root/build" "$root/build-core"
}

sc_prepare_cmake_build_dir() {
  local root="${1:-$SC_PROJECT_ROOT}"
  local build_dir="${2:?build directory is required}"
  local expected_generator="${3:-Ninja}"
  local cache="$build_dir/CMakeCache.txt"
  local cached_home=""
  local cached_binary=""
  local cached_generator=""
  local expected_root=""
  local expected_binary=""
  local reason=""

  expected_root="$(realpath -m "$root")"
  expected_binary="$(realpath -m "$build_dir")"

  if [[ -L "$build_dir" ]]; then
    echo "Refusing to replace symlinked CMake build directory: $build_dir" >&2
    return 2
  fi

  if [[ -f "$cache" ]]; then
    cached_home="$(sed -n 's/^CMAKE_HOME_DIRECTORY:INTERNAL=//p' "$cache" | head -n 1)"
    cached_binary="$(sed -n 's/^CMAKE_CACHEFILE_DIR:INTERNAL=//p' "$cache" | head -n 1)"
    cached_generator="$(sed -n 's/^CMAKE_GENERATOR:INTERNAL=//p' "$cache" | head -n 1)"

    if [[ "$cached_generator" != "$expected_generator" ]]; then
      reason="generator ${cached_generator:-unknown} instead of $expected_generator"
    elif [[ -n "$cached_home" && "$(realpath -m "$cached_home")" != "$expected_root" ]]; then
      reason="source moved from $cached_home"
    elif [[ -n "$cached_binary" && "$(realpath -m "$cached_binary")" != "$expected_binary" ]]; then
      reason="build directory moved from $cached_binary"
    fi

    if [[ -n "$reason" ]]; then
      echo "Discarding stale CMake cache in $build_dir ($reason)."
      rm -rf -- "$build_dir"
    fi
  elif [[ -d "$build_dir/CMakeFiles" ]]; then
    echo "Discarding incomplete CMake build directory without a cache: $build_dir"
    rm -rf -- "$build_dir"
  fi
}

sc_ensure_portable_core() {
  local builder="$SC_PROJECT_ROOT/scripts/build_core.sh"
  if [[ ! -f "$builder" ]]; then
    echo "SignalCloud portable core builder is missing: $builder" >&2
    return 2
  fi
  bash "$builder"
}
