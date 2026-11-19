#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
export DEVKITPRO="${DEVKITPRO:-/opt/devkitpro}"
export DEVKITA64="$DEVKITPRO/devkitA64"
cd "$ROOT"
rtk proxy cmake --fresh -S . -B build/switch-workspace -G Ninja \
  -DCMAKE_TOOLCHAIN_FILE=cmake/switch-toolchain.cmake \
  -DCMAKE_BUILD_TYPE=RelWithDebInfo
rtk proxy cmake --build build/switch-workspace --parallel 4
