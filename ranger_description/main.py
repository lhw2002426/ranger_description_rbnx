#!/usr/bin/env python3
# SPDX-License-Identifier: MulanPSL-2.0
"""ranger_description_rbnx — static-TF stand-in for `system.soma`.

Until soma (URDF + robot_state_publisher) ships in robonix v0.2, the
deploy needs SOMETHING to publish the static edges from `base_link`
down to each sensor mount frame. Without them, rtabmap's RGBD path
silently fails TF lookups and nav goals land in the wrong place.

This package owns `robonix/primitive/tf/*`. Its only side-effect is
spawning `ros2 launch <pkg>/launch/static_tf.launch.xml` as a managed
subprocess at Driver(CMD_INIT) time, with optional `<key>:=<value>`
launch-arg overrides forwarded from the deploy manifest's
`config.launch_args`. There is no atlas-routed topic — TF is a global
ROS-graph side-channel that every tf2-aware node joins automatically,
so wrapping it in atlas would only add indirection.

Lifecycle (per Robonix developer guide §5 / §14.3):
    on_init      — heavy: spawn ros2 launch, wait briefly for it to
                   actually start (we sentinel the subprocess's
                   poll() rather than the /tf_static topic — TF
                   subscriptions are awkward to one-shot from rclpy
                   and a launch process that crashed in <0.5 s is
                   the failure case we actually need to catch).
                   Returning Err here is the right failure mode (rbnx
                   aborts boot) because mapping / nav are useless
                   without these TF edges.
    on_shutdown  — kill the launch subprocess (and, via process
                   group, any static_transform_publisher children
                   it spawned). Idempotent.

Why on_init not on_activate: the static TFs need to be live BEFORE any
downstream consumer (mapping, nav) tries to do TF lookups during its
own Init. With rbnx boot's strict-serial ordering, putting this
package early in `primitive:` and doing the spawn in on_init is the
simplest way to guarantee that.

Config (from manifest's `config:` block, delivered via Driver(CMD_INIT)):
    launch_file        default "launch/static_tf.launch.xml"
                       (relative to package root; absolute path also accepted)
    launch_args        optional dict[str, str], forwarded as
                       `<key>:=<value>` ros2 launch args. Values are
                       coerced via str(); use strings in the YAML to
                       avoid surprises with floats vs. ints.
    spawn_grace_s      default 1.5  — how long we wait after spawning
                       to check that ros2 launch is still alive. The
                       common failure (typo in launch file, missing
                       tf2_ros) crashes ros2 launch in well under 1 s,
                       so even a small grace period catches it.
"""
from __future__ import annotations

import logging
import os
import signal
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from robonix_api import Primitive, Ok, Err

logging.basicConfig(
    level=os.environ.get("RANGER_DESCRIPTION_LOG_LEVEL", "INFO"),
    format="[ranger_description] %(message)s",
)
log = logging.getLogger("ranger_description")

# Provider id MUST equal the deploy manifest's `primitive: - name: ...`
# entry for this package — rbnx boot reconciles the two on spawn.
ranger_description = Primitive(
    id="ranger_description",
    namespace="robonix/primitive/tf",
)

_pkg_root: Path = Path(__file__).resolve().parent.parent

# Spawned at on_init, killed at on_shutdown. Module-level so the kill
# helper can find it regardless of who calls (CMD_SHUTDOWN / signal).
_launch_proc: Optional[subprocess.Popen] = None


def _resolve_launch_file(cfg: dict) -> Path:
    rel = str(cfg.get("launch_file", "launch/static_tf.launch.xml"))
    p = Path(rel)
    if not p.is_absolute():
        p = _pkg_root / p
    if not p.is_file():
        raise FileNotFoundError(f"launch file not found: {p}")
    return p


def _build_launch_argv(cfg: dict) -> list[str]:
    launch_path = _resolve_launch_file(cfg)
    argv: list[str] = ["ros2", "launch", str(launch_path)]
    extra = cfg.get("launch_args") or {}
    if not isinstance(extra, dict):
        raise TypeError(
            f"launch_args must be a dict, got {type(extra).__name__}"
        )
    for k, v in extra.items():
        # ros2 launch is fine with anything stringifiable; the launch
        # file's <arg> declarations decide how it's parsed.
        argv.append(f"{k}:={v}")
    return argv


def _spawn_launch(cfg: dict) -> None:
    global _launch_proc
    argv = _build_launch_argv(cfg)
    log_path = _pkg_root / "rbnx-build" / "data" / "static_tf.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log_fh = open(log_path, "ab", buffering=0)
    log.info("spawning %s → %s", " ".join(argv), log_path)
    _launch_proc = subprocess.Popen(
        argv,
        stdout=log_fh,
        stderr=log_fh,
        start_new_session=True,
    )


def _kill_launch() -> None:
    global _launch_proc
    p = _launch_proc
    if p is None or p.poll() is not None:
        _launch_proc = None
        return
    try:
        # Kill the whole session so static_transform_publisher children
        # die too. ros2 launch occasionally leaks them on plain SIGTERM.
        os.killpg(os.getpgid(p.pid), signal.SIGTERM)
    except ProcessLookupError:
        _launch_proc = None
        return
    try:
        p.wait(timeout=5.0)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(p.pid), signal.SIGKILL)
        except ProcessLookupError:
            pass
    _launch_proc = None


@ranger_description.on_init
def init(cfg: dict):
    """REGISTERED → INACTIVE → (effectively) ACTIVE.

    Spawn ros2 launch and verify it's still alive a moment later. We
    don't try to subscribe to /tf_static as a sentinel — tf2's static
    publishing is latched-on-publish and a one-shot rclpy subscription
    is awkward to set up cleanly here. Watching `proc.poll()` for the
    "exited within 1.5 s" failure mode catches the cases that actually
    matter (typo in launch file, tf2_ros missing on PATH, etc.).
    """
    cfg = cfg or {}
    try:
        grace = float(cfg.get("spawn_grace_s", 1.5))
        if grace <= 0:
            return Err(f"spawn_grace_s must be > 0, got {grace}")
    except (TypeError, ValueError) as e:
        return Err(f"spawn_grace_s not numeric: {e}")

    try:
        _spawn_launch(cfg)
    except (FileNotFoundError, TypeError) as e:
        return Err(f"prepare launch failed: {e}")
    except Exception as e:  # noqa: BLE001
        return Err(f"spawn ros2 launch failed: {e}")

    # Grace window: if ros2 launch crashes immediately, surface that
    # before reporting Init success.
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline:
        if _launch_proc is not None and _launch_proc.poll() is not None:
            rc = _launch_proc.returncode
            _launch_proc = None  # type: ignore[assignment]
            return Err(
                f"ros2 launch exited within {grace:.1f}s (rc={rc}); "
                f"check rbnx-build/data/static_tf.log"
            )
        time.sleep(0.1)

    log.info("CMD_INIT ok: static TF launch alive (pid=%s)",
             _launch_proc.pid if _launch_proc else "?")
    return Ok()


@ranger_description.on_shutdown
def shutdown():
    """any → TERMINATED. Kill the ros2 launch subprocess (and its
    static_transform_publisher children, via the process group)."""
    _kill_launch()
    log.info("CMD_SHUTDOWN ok")
    return Ok()


if __name__ == "__main__":
    ranger_description.run()
