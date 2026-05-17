#!/usr/bin/env python3
# SPDX-License-Identifier: MulanPSL-2.0
"""Tiny rbnx-boot adapter for ranger_description.

What this script does, in order:
    1. RegisterPrimitive(id=ranger_description, namespace=robonix/primitive/tf)
       on atlas — so rbnx boot's wait_for_registration loop unblocks and
       prints `OK  ACTIVE (no driver)`.
    2. Spawn `ros2 launch <pkg>/launch/static_tf.launch.xml` as a child
       process group. ros2 launch publishes /tf_static and stays up.
    3. Heartbeat atlas every 30s in a daemon thread so we don't get
       evicted to TERMINATED after the 90s default timeout.
    4. Forward SIGTERM/SIGINT to the launch process group so rbnx boot's
       teardown is clean.

What this script intentionally does NOT do (this is the whole point of
the rewrite):
    - Declare any capability over gRPC/ROS/MCP. TF is a global ROS 2
      side-channel; atlas-routing it would only add indirection.
    - Bind a Driver(CMD_INIT) Servicer. With no `*/driver` capability
      registered, rbnx boot sees `driver_contract=None` and skips the
      CMD_INIT/CMD_ACTIVATE handshake entirely (deploy.rs:1247-1253:
      "no driver contract — system providers auto-promote to ACTIVE").
    - Use robonix_api.Capability or any of its lifecycle machinery —
      that's the layer we deliberately bypass. We talk to atlas
      directly through the generated atlas_pb2 stubs (one
      RegisterPrimitive RPC + a heartbeat loop, that's it).

Required PYTHONPATH (set by start.sh):
    rbnx-build/codegen/proto_gen        — atlas_pb2 / atlas_pb2_grpc
    /opt/ros/humble/lib/python*/...     — implicit via ros2 launch's own env
"""
from __future__ import annotations

import os
import signal
import subprocess
import sys
import threading
import time

import grpc                       # type: ignore
import atlas_pb2 as pb            # type: ignore
import atlas_pb2_grpc as pb_grpc  # type: ignore


PROVIDER_ID    = "ranger_description"
NAMESPACE      = "robonix/primitive/tf"
HEARTBEAT_PERIOD_S = 30.0


def _log(msg: str) -> None:
    # Mirror the format mid360_imu / nav2_wrapper use so rbnx-boot's
    # log scraping treats us the same.
    print(f"[ranger_description] {msg}", flush=True)


def _register_with_atlas(stub: pb_grpc.AtlasStub) -> None:
    """RegisterPrimitive once. Fail loud (exit 2) on any RPC error so
    rbnx boot's spinner reports the actual reason instead of just
    timing out at the 90 s registration deadline.

    All three RegisterPrimitive / RegisterService / RegisterSkill RPCs
    take a single shared `RegisterRequest` message — see atlas.proto
    line ~121. Don't be fooled by the verb-suffixed RPC name into
    looking for a `RegisterPrimitiveRequest` type; it doesn't exist.
    """
    try:
        req = pb.RegisterRequest(
            id=PROVIDER_ID,
            namespace=NAMESPACE,
            capability_md_path="",
        )
        stub.RegisterPrimitive(req, timeout=5.0)
    except grpc.RpcError as e:
        _log(f"RegisterPrimitive failed: {e.code().name} {e.details()}")
        sys.exit(2)
    _log(f"registered with atlas (id={PROVIDER_ID}, namespace={NAMESPACE})")


def _heartbeat_forever(stub: pb_grpc.AtlasStub) -> None:
    """Background daemon: every HEARTBEAT_PERIOD_S, ping atlas. Atlas's
    default eviction is 90 s (DEFAULT_HEARTBEAT_TIMEOUT_MS in
    robonix-atlas/src/service.rs); 30 s gives 3 attempts before
    eviction, which is plenty.

    RPC errors are logged at debug level only — a transient network
    blip shouldn't take the whole package down. If atlas is gone
    permanently, eviction will land naturally."""
    while True:
        time.sleep(HEARTBEAT_PERIOD_S)
        try:
            stub.Heartbeat(pb.HeartbeatRequest(id=PROVIDER_ID), timeout=5.0)
        except grpc.RpcError:
            pass  # silent — see docstring


def _spawn_launch(launch_file: str) -> subprocess.Popen:
    """Spawn `ros2 launch <launch_file>` in its own process group so we
    can SIGTERM the whole tree (launch + every static_transform_publisher
    child) on shutdown."""
    _log(f"spawning ros2 launch {launch_file}")
    return subprocess.Popen(
        ["ros2", "launch", launch_file],
        # New session → killpg(getpgid(child)) reaches every descendant.
        start_new_session=True,
    )


def main() -> int:
    pkg_root = os.environ.get(
        "RBNX_PACKAGE_ROOT",
        os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
    )
    launch_file = os.path.join(pkg_root, "launch", "static_tf.launch.xml")
    if not os.path.isfile(launch_file):
        _log(f"ERR: launch file missing: {launch_file}")
        return 2

    atlas_endpoint = os.environ.get("ROBONIX_ATLAS", "127.0.0.1:50051")
    _log(f"connecting to atlas at {atlas_endpoint}")
    channel = grpc.insecure_channel(atlas_endpoint)
    stub = pb_grpc.AtlasStub(channel)

    _register_with_atlas(stub)

    # Heartbeat thread starts AFTER the initial Register lands, so a
    # registration race that hands us "unknown provider_id" never fires.
    threading.Thread(
        target=_heartbeat_forever,
        args=(stub,),
        name="ranger_description-heartbeat",
        daemon=True,
    ).start()

    proc = _spawn_launch(launch_file)

    # Forward SIGTERM/SIGINT to the launch tree so rbnx boot's
    # SIGTERM-on-PGID teardown propagates cleanly. We don't trap SIGCHLD;
    # if ros2 launch dies on its own, proc.wait() returns and we exit
    # with its code (rbnx boot will mark the package failed).
    def _forward(sig, _frame):
        _log(f"got signal {sig}; forwarding to ros2 launch pid={proc.pid}")
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        except ProcessLookupError:
            pass
    signal.signal(signal.SIGTERM, _forward)
    signal.signal(signal.SIGINT,  _forward)

    rc = proc.wait()
    _log(f"ros2 launch exited rc={rc}")
    return rc


if __name__ == "__main__":
    sys.exit(main())
