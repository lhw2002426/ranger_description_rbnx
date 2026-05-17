# ranger_description_rbnx

Robonix package owning the `primitive/tf/*` namespace for the AgileX Ranger Mini. It is a thin wrapper around a tiny `ros2 launch` file that brings up two `static_transform_publisher` nodes:

- `base_link → livox_frame`        — MID-360 mount
- `base_link → camera_435i_link`   — RealSense D435i body mount

It exists as a **stand-in for `system.soma`** (URDF + robot_state_publisher), which is on the v0.2 robonix roadmap but not yet shipped. When soma lands, drop this package from the deploy manifest and point `system.soma.urdf_path` at the proper URDF — this whole package becomes a no-op and can be removed.

## Capability surface

| Contract                      | Mode | Transport | Source / handler                            |
| ----------------------------- | ---- | --------- | ------------------------------------------- |
| `robonix/primitive/tf/driver` | rpc  | gRPC      | `Driver(CMD_INIT, config_json)` — lifecycle |

We deliberately do **not** atlas-declare `/tf_static` as a topic_out capability. TF is a global side-channel in ROS 2 (every node with `tf2_ros` joins the same `/tf` + `/tf_static` graph automatically), so routing it through atlas would only add indirection without changing the wiring.

## Frame contract (must match the rest of the deploy)

| Frame | Owner | Notes |
| --- | --- | --- |
| `base_link` | `ranger_chassis_rbnx` | chassis frame; the chassis driver publishes `odom → base_link` when `publish_odom_tf: true`. |
| `livox_frame` | **this package** | The Livox driver publishes `PointCloud2` with `frame_id="livox_frame"` (hard-coded). Don't rename. |
| `camera_435i_link` | **this package** | RealSense D435i body mount. Note the `camera_435i` prefix — `realsense2_camera` builds frame names as `<camera_name>_<base_frame_id>`, and the deploy sets `camera_name: camera_435i`. The common mistake is publishing to bare `camera_link`, which nothing in the deploy uses. |
| `camera_435i_*_optical_frame` | `realsense2_camera` | Published by the RealSense driver itself, off `camera_435i_link`. Don't add static TFs for these. |

`map → odom` is owned by rtabmap (`mapping_rbnx`); this package does not republish it.

## Driver-init lifecycle

`scripts/start.sh` brings up the atlas bridge (`python3 -m ranger_description.main`). The bridge opens a gRPC server, registers the cap on atlas, declares `primitive/tf/driver`, then blocks awaiting `Driver(CMD_INIT, config_json)`.

When `rbnx boot` calls Init, the handler spawns `ros2 launch <pkg>/launch/static_tf.launch.xml` (with optional `launch_args` overrides forwarded as `<key>:=<value>`), waits a short grace window (`spawn_grace_s`, default 1.5 s) to make sure the launch process didn't crash, and returns `Ok()`.

We do `spawn_launch + grace_check` inside **`on_init`** rather than `on_activate` because mapping / nav read these TFs during their own Init, and rbnx boot's strict-serial ordering means putting this package early in `primitive:` + doing the spawn in `on_init` is the cleanest way to guarantee the TFs are live before downstream Inits run.

## Build phase

`scripts/build.sh` calls `rbnx codegen` only — no native compilation, no vendored ROS package source. The only "artifact" this package ships is `launch/static_tf.launch.xml`, which is consumed at runtime by `ros2 launch` and needs no compilation step.

## Config (passed via `Driver(CMD_INIT, config_json)`)

```yaml
primitive:
  - name: ranger_description
    url: https://github.com/lhw2002426/ranger_description_rbnx
    branch: main
    config:
      # Optional: pick a different launch file shipped in this package.
      # Relative paths resolve against the package root; absolute paths
      # are also accepted.
      # launch_file: launch/static_tf.launch.xml

      # Optional: per-axis overrides for the mount offsets baked into
      # static_tf.launch.xml. The defaults are placeholders derived
      # from CAD — measure your actual robot and override these
      # before relying on the TF tree for SLAM / nav.
      launch_args:
        lidar_x:  "0.18"
        lidar_y:  "0.00"
        lidar_z:  "0.425"
        camera_x: "0.28"
        camera_y: "0.00"
        camera_z: "0.30"

      # spawn_grace_s: 1.5
```

## Standalone testing (no rbnx)

```bash
ros2 launch ranger_description_rbnx/launch/static_tf.launch.xml
```

Override mount offsets without editing the file:

```bash
ros2 launch ranger_description_rbnx/launch/static_tf.launch.xml \
    lidar_x:=0.18 lidar_z:=0.42 \
    camera_x:=0.28 camera_z:=0.30
```

Mis-calibrated TF is the single most common reason rtabmap "thinks the robot is jumping around" or nav goals land 30 cm off — measure the actual mount before trusting the defaults.

## License

MulanPSL-2.0.
