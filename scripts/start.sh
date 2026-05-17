#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# Spawn the ranger_description atlas bridge. The bridge itself does
# nothing until `Driver(CMD_INIT)` lands — at that point it spawns
# `ros2 launch <pkg>/launch/static_tf.launch.xml` as a managed
# subprocess and atlas-declares the `primitive/tf/driver` capability.
set -euo pipefail
PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

ROS_DISTRO="${ROS_DISTRO:-humble}"
# shellcheck disable=SC1091
set +u; source "/opt/ros/${ROS_DISTRO}/setup.bash"; set -u

if ROBONIX_API="$(rbnx path robonix-api 2>/dev/null)"; then
    export PYTHONPATH="$ROBONIX_API:$PKG:${PYTHONPATH:-}"
fi

exec python3 -m ranger_description.main
