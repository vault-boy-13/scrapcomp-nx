#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DEVKITPRO="${DEVKITPRO:-/opt/devkitpro}"
export DEVKITA64="$DEVKITPRO/devkitA64"
cd "$ROOT"
BUILD=build/switch-workspace
CONFIG=(--fresh)
TARGET=()
if [[ $# -gt 0 ]]; then
  BUILD=build/switch-game
  CONFIG=(-DSCRAP_BUILD_GAME_SWITCH=ON "-DSCRAP_GENERATED_DIR:STRING=$1"
    "-DSCRAP_SWITCH_TRACE_XPP=${2:-OFF}")
  TARGET=(--target scrapcomp_switch_nro)
fi
rtk proxy cmake -S . -B "$BUILD" -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/switch-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo "${CONFIG[@]}"
rtk proxy cmake --build "$BUILD" "${TARGET[@]}" --parallel 4
