# ranger_description_rbnx

A minimal robonix wrapper around a single `ros2 launch` file. Spawns two `static_transform_publisher` nodes:

- `base_link → livox_frame`        — MID-360 mount
- `base_link → camera_435i_link`   — RealSense D435i body mount

It exists as a **stand-in for `system.soma`** (URDF + robot_state_publisher), which is on the v0.2 robonix roadmap but not yet shipped. When soma lands, drop this package from the deploy manifest and point `system.soma.urdf_path` at the proper URDF — this whole package becomes a no-op and can be removed.

## What this package is (and isn't)

- ✔ A `ros2 launch <pkg>/launch/static_tf.launch.xml` invocation supervised by rbnx boot.
- ✘ Not a Python atlas_bridge. There's no `Driver(CMD_INIT)` handler, no `@on_init`, no `@on_activate`. `start.sh` just `exec`s `ros2 launch` and lets the launch tree be its sole process.
- ✘ Not an atlas-routed capability. `capabilities: []` in `package_manifest.yaml`. TF is already a ROS 2 global side-channel (every tf2-aware node joins `/tf` + `/tf_static` automatically), so atlas-routing it would only add indirection. rbnx boot registers the package on atlas with state ACTIVE the moment `start.sh` spawns and skips the Driver(CMD_INIT) handshake.
- ✘ Not a build target. `build.sh` is a no-op (just writes the `.rbnx-built` stamp so rbnx boot's "needs build" heuristic stays happy). No codegen, no protoc, no native compile.

## Frame contract (must match the rest of the deploy)

| Frame | Owner | Notes |
| --- | --- | --- |
| `base_link` | `ranger_chassis_rbnx` | chassis frame; the chassis driver publishes `odom → base_link` when `publish_odom_tf: true`. |
| `livox_frame` | **this package** | The Livox driver publishes `PointCloud2` with `frame_id="livox_frame"` (hard-coded). Don't rename. |
| `camera_435i_link` | **this package** | RealSense D435i body mount. Note the `camera_435i` prefix — `realsense2_camera` builds frame names as `<camera_name>_<base_frame_id>`, and the deploy sets `camera_name: camera_435i`. The common mistake is publishing to bare `camera_link`, which nothing in the deploy uses. |
| `camera_435i_*_optical_frame` | `realsense2_camera` | Published by the RealSense driver itself, off `camera_435i_link`. Don't add static TFs for these. |

`map → odom` is owned by rtabmap (`mapping_rbnx`); this package does not republish it.

## Layout

```
ranger_description_rbnx/
├── package_manifest.yaml        capabilities: [] (intentional)
├── launch/
│   └── static_tf.launch.xml     two static_transform_publisher nodes
└── scripts/
    ├── build.sh                 no-op (writes .rbnx-built stamp)
    └── start.sh                 exec ros2 launch …/static_tf.launch.xml
```

## Configuration — edit the launch file directly

The mount-offset defaults baked into `launch/static_tf.launch.xml` are placeholders derived from CAD. To override per-axis you can either:

1. **Edit `launch/static_tf.launch.xml`** (default values in the `<arg ...>` tags) and re-push, or
2. **Pass `<key>:=<value>` args from the command line** when running standalone (the `<arg>` defaults exist exactly for this):

```bash
ros2 launch ranger_description_rbnx/launch/static_tf.launch.xml \
    lidar_x:=0.18 lidar_z:=0.42 \
    camera_x:=0.28 camera_z:=0.30
```

There is no manifest-side `launch_args` block anymore — that path required a Python wrapper to convert YAML config → ros2 launch args, which we don't ship. If a deploy needs different defaults, fork this package or just patch the launch file in-tree.

## Standalone testing (without rbnx boot)

```bash
ros2 launch ranger_description_rbnx/launch/static_tf.launch.xml
```

Verify with:

```bash
ros2 run tf2_ros tf2_echo base_link livox_frame
ros2 run tf2_ros tf2_echo base_link camera_435i_link
```

Mis-calibrated TF is the single most common reason rtabmap "thinks the robot is jumping around" or nav goals land 30 cm off — measure the actual mount before trusting the defaults.

## License

MulanPSL-2.0.
