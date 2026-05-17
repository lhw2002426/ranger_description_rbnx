#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# Build phase: rbnx codegen ONLY. We need the generated atlas_pb2 +
# atlas_pb2_grpc Python stubs so scripts/atlas_register_and_launch.py
# can RegisterPrimitive on atlas (which is what unblocks rbnx boot's
# wait_for_registration loop). Beyond that this package vendors no
# source — the actual TF publishing is done by `ros2 launch`'s own
# tf2_ros/static_transform_publisher nodes at runtime.
#
# Why we can't go fully no-op like before: with capabilities: [] AND
# no provider registration, rbnx boot sits in wait_for_registration
# until DRIVER_REGISTER_TIMEOUT and reports "package never appeared
# in atlas". The fix is one RegisterPrimitive RPC at start, which
# needs atlas_pb2 stubs, which need codegen. That's the whole reason
# build.sh is no longer a pure no-op.
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
echo "[ranger_description/build] done."
