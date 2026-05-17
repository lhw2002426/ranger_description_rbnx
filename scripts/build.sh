#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# Build phase: NO-OP. This package is a `ros2 launch` wrapper — there
# is no Python module to import codegen output into, no native code
# to compile, no `*/driver` capability to register on atlas. The
# whole job at runtime is `exec ros2 launch launch/static_tf.launch.xml`,
# which only needs the .launch.xml file already on disk.
#
# We still write the rbnx-build/.rbnx-built stamp so `rbnx boot`'s
# inline-build heuristic (deploy.rs's `needs_build` set) considers
# this package "built" and doesn't try to re-run build.sh on every
# boot.

set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

mkdir -p "$PKG/rbnx-build"
touch    "$PKG/rbnx-build/.rbnx-built"

echo "[ranger_description/build] no-op (pure ros2 launch wrapper)."
