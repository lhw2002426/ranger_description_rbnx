#!/usr/bin/env bash
# SPDX-License-Identifier: MulanPSL-2.0
#
# Spawn the static-TF launch directly. This package owns
# `robonix/primitive/tf/*` only in the deploy-manifest sense —
# functionally it's a tiny `ros2 launch` wrapper, and we deliberately
# DON'T plug into robonix's lifecycle gRPC machinery (no atlas_bridge,
# no @on_init, no codegen, no contract toml). Reasons:
#
#   * The "contract" we'd need is robonix/primitive/tf/driver, which
#     doesn't exist in the global capabilities tree. Adding it means
#     either patching the robonix repo or shipping a per-package
#     overlay AND triggering codegen — both heavier than the work
#     this package is supposed to do.
#   * TF in ROS 2 is already a global side-channel (every tf2-aware
#     node joins /tf + /tf_static automatically), so atlas-routing
#     it would be pure indirection.
#   * The whole package will be deleted once `system.soma` ships
#     in robonix v0.2 (URDF + robot_state_publisher will own these
#     edges natively).
#
# So: this script IS the package. It execs `ros2 launch` as PID 1 of
# the spawned process group. rbnx boot's SIGTERM-on-PGID teardown
# kills ros2 launch + every static_transform_publisher child it
# spawned. CMD_INIT never fires (rbnx boot just registers the cap on
# atlas without a Driver(CMD_INIT) handshake — the framework treats
# packages with no `*/driver` Servicer as "up the moment they
# register").

set -euo pipefail

PKG="${RBNX_PACKAGE_ROOT:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$PKG"

ROS_DISTRO="${ROS_DISTRO:-humble}"
# shellcheck disable=SC1091
set +u; source "/opt/ros/${ROS_DISTRO}/setup.bash"; set -u

LAUNCH_FILE="${PKG}/launch/static_tf.launch.xml"
if [[ ! -f "$LAUNCH_FILE" ]]; then
    echo "[ranger_description/start] ERR: launch file missing: $LAUNCH_FILE" >&2
    exit 2
fi

echo "[ranger_description/start] ros2 launch ${LAUNCH_FILE}"
exec ros2 launch "$LAUNCH_FILE"
