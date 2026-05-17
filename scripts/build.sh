#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# Build phase: rbnx codegen ONLY. This package vendors no source —
# the only "artifact" it ships is `launch/static_tf.launch.xml`, which
# is consumed at runtime by `ros2 launch` and needs no compilation.
#
# We still call `rbnx codegen` so the framework can generate the
# auto-declared driver capability stub (the `*/driver` gRPC server is
# what `Driver(CMD_INIT)` lands on; without codegen the start.sh
# bridge has nothing to import).
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"
CLEAN="${RBNX_BUILD_CLEAN:-}"

if [[ "$CLEAN" == "1" ]]; then
    echo "[ranger_description/build] clean: removing rbnx-build/"
    rm -rf rbnx-build
fi
mkdir -p rbnx-build/data

FLAGS=(--out-dir "$PKG/rbnx-build/codegen")
[[ "$CLEAN" == "1" ]] && FLAGS+=(--clean)
echo "[ranger_description/build] rbnx codegen ${FLAGS[*]}"
rbnx codegen -p "$PKG" "${FLAGS[@]}"

touch "$PKG/rbnx-build/.rbnx-built"
echo "[ranger_description/build] done (no native build step — pure launch wrapper)."
