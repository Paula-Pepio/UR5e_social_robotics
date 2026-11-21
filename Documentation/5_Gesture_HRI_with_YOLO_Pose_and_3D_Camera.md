# Gesture HRI with YOLO Pose and a 3D Camera

## Status

This is an experimental guide. The gesture nodes are not finished or validated.

Use the current nodes only with perception data, fake hardware and planning mode. Do not execute gesture-driven motions on the real UR5e.

All software is already installed. See [UR5e ROS 2 setup](Files/References/UR5e_ROS2_Setup.md) for the workspace, `.venv-humble` and Ultralytics. For the camera driver, see the [Orbbec Gemini 2 installation guide](Files/Camera%26Microphone/Gemini2_installation.md).

The Teacher PC acts as both HRI client and robot server. It runs the camera, perception, gesture, behavior, MoveIt 2 and robot-control nodes. No Student PC is used because the person must stand in front of the robot, camera and audio equipment.

## Objective

The final HRI system will react when an authorised person offers a hand:

- a hand extended at handshake height requests `handshake`;
- a raised hand at high-five height requests `give5`.

YOLO Pose detects the body keypoints in the colour image. The 3D camera adds depth to the shoulder, elbow and wrist positions. A gesture classifier must then choose the social intent.

The standard YOLO Pose model does not detect fingers. The first `give5` classifier must therefore use the arm and wrist position, or a future hand-pose model.

## Expected architecture

```text
authorised face
      |
      +------------------------------+
                                     v
Gemini2 RGB + depth -> YOLO Pose -> 3D body keypoints
                                     |
                                     v
                           gesture classifier
                         /                    \
              handshake_offer             give5_offer
                         \                    /
                          interaction manager
                                     |
                                     v
                              MoveIt 2 -> UR5e
```

The final system must associate the authorised face with the same person whose body pose is used. This association is not implemented yet.

## Current data flow

| Interface | Data |
|---|---|
| `/person_pose_3d` | The 17 COCO body keypoints in metres, in the camera optical frame |
| `/wrist_pose` | The selected wrist pose in the camera optical frame |
| `/social_intent` | The detected intent; currently only `handshake_offer` |
| `/handshake_target` | One captured wrist target transformed to the `table` frame |
| `/ur5e/run_pose` | The pose request used for approach, contact, shake, retreat and home |

The current handshake uses one wrist snapshot. It does not track the hand while the robot moves. It does not control a gripper or detect physical contact, and it does not generate a YAML motion file.

## Frame convention and simulation-validation workflow

The pose detector first measures the selected wrist in
`camera_color_optical_frame`. MoveIt plans the UR5e in `base_link`. A detected
wrist must therefore be transformed through a calibrated TF tree before it can
be used as a robot target:

```text
base_link -> table -> camera_color_optical_frame -> detected wrist
```

`table` is the current intermediate frame used by the interaction manager. It
is not automatically the same frame as `base_link`. The TF transform
`base_link -> table` must exist, even if both origins physically coincide.

Use the following workflow for each new HRI interaction. It is deliberately
simulation-first; keep `execute:=false` until every acceptance check passes.

1. Start the camera with depth registration and verify that both RGB and depth
   topics publish at the requested rate. Inspect `/camera/color/camera_info`.
2. Start `pose_3d_node`, inspect `/wrist_pose`, and confirm that the selected
   wrist moves plausibly in metres in `camera_color_optical_frame`. When the
   hand moves towards the camera, its optical-frame `z` should decrease.
3. Calibrate the measured static transform
   `table -> camera_color_optical_frame` in `pose_3d_params.yaml`. Enter
   measured `translation_m` and `rpy_rad`, then set
   `camera_table_tf_node.enabled` to `true`. Never enable the zero defaults.
4. Verify the complete TF chain before planning:

   ```bash
   ros2 run tf2_ros tf2_echo table camera_color_optical_frame
   ros2 run tf2_ros tf2_echo base_link table
   ros2 run tf2_ros tf2_echo base_link camera_color_optical_frame
   ```

5. Transform a captured `/wrist_pose` into `base_link` and inspect its
   `x`, `y`, and `z` values. This diagnostic output should be added as a
   dedicated `/wrist_pose_base` topic before robot motion is enabled. Validate
   it against several known physical points in the workspace; use an agreed
   position-error limit (for example, 20–30 mm for the first approach test).
6. Run the UR5e with fake hardware and MoveIt in RViz. Confirm that the
   transformed wrist target is reachable, collision-free, and visually located
   where the person's hand is represented in the scene.
7. Derive a TCP approach pose from the wrist pose. Do **not** command `tool0`
   to the wrist centre. Use a validated clearance (initially 100–150 mm) in
   the selected approach direction and an explicitly validated tool
   orientation. Only then test approach, contact, shake and retreat in
   planning mode.

For `handshake_offer`, the current classifier and interaction manager provide
the initial implementation. For `give5_offer`, repeat steps 1--6 to collect
and validate shoulder, elbow and wrist configurations before adding its
classifier and manager. A raised-hand pose must not be interpreted as a
handshake.

## Current implementation

| Component | Current state |
|---|---|
| `gesture_node` | Placeholder only; it does not run YOLO Pose or publish gestures |
| `pose_3d_node` | Detects one person with YOLO Pose and publishes 3D keypoints and a wrist pose |
| `gesture_interpreter_node` | Detects only an extended arm and publishes `handshake_offer` |
| `interaction_manager_node` | Creates an experimental dynamic handshake from one wrist snapshot |
| Face authorisation link | Not connected to the detected body pose |
| `give5` classifier and manager | Not implemented |
| Real-robot validation | Not completed |

## Launch files

| Launch file | State | Purpose |
|---|---|---|
| `orbbec_camera gemini2.launch.py` | Available | Starts the Gemini2 camera |
| `social_robot_perception pose_3d.launch.py` | Available | Starts YOLO Pose and 3D keypoint estimation |
| `social_robot_hri gesture_interpreter.launch.py` | Available | Starts the current handshake-offer classifier |
| `social_robot_behaviors dynamic_handshake.launch.py` | Experimental | Starts perception, handshake interpretation and the interaction manager |
| `dynamic_give5.launch.py` | Not implemented | Will execute the dynamic `give5` behavior |
| `gesture_hri.launch.py` | Not implemented | Will combine face authorisation and both gesture behaviors |

## 1. Prepare every terminal

Run this in every terminal inside the Teacher container:

```bash
cd /root/UR5e_social_robotics
source /opt/ros/humble/setup.bash
source .venv-humble/bin/activate
source install/setup.bash
```

The camera calibration is only required when transforming a detected wrist to
the robot frames. Before the dynamic-handshake test, `pose_3d_params.yaml`
must contain the approved `table -> camera_color_optical_frame` transform.

Check that `camera_table_tf_node.enabled` is `true`, that the child frame
matches `/camera/color/camera_info`, and that `translation_m` and `rpy_rad`
contain measured values. Never use the zero defaults for robot motion.

## 2. Start the camera

Terminal 1:

```bash
ros2 launch orbbec_camera gemini2.launch.py \
  color_width:=640 color_height:=480 color_fps:=15 \
  depth_width:=640 depth_height:=400 depth_fps:=15 \
  depth_registration:=true enable_point_cloud:=false enable_ir:=false
```

Check the image and camera information:

```bash
ros2 topic hz /camera/color/image_raw
ros2 topic hz /camera/depth/image_raw
ros2 topic echo /camera/color/camera_info --once
```

## 3. Test YOLO Pose and 3D keypoints

Terminal 2:

```bash
ros2 launch social_robot_perception pose_3d.launch.py
```

Terminal 3:

```bash
ros2 topic echo /person_pose_3d
```

Terminal 4:

```bash
ros2 topic echo /wrist_pose
```

Stand in front of the camera and move one arm. Check that the wrist position changes correctly in metres and that the message uses the configured camera frame.

## 4. Test the current gesture classifier

Keep the camera and `pose_3d_node` running. In terminal 5:

```bash
ros2 launch social_robot_hri gesture_interpreter.launch.py
```

In terminal 6:

```bash
ros2 topic echo /social_intent
```

Extend the configured arm towards the camera and hold it briefly. The current expected result is:

```text
handshake_offer
```

Raise the hand as if offering a high five. Record the 3D shoulder, elbow and wrist positions. The current node cannot publish `give5_offer` yet.

Keep the selected shoulder, elbow and wrist visible. The selected arm and detection thresholds are configured in `social_robot_hri/config/gesture_interpreter_params.yaml`. Move away before repeating the gesture so that the cooldown can finish.

## 5. Test the experimental dynamic handshake

Stop the nodes from sections 3 and 4 to avoid duplicate nodes. Keep the camera running.

Terminal 2 - fake UR5e:

```bash
ros2 launch ur_robot_driver ur_control.launch.py \
  ur_type:=ur5e robot_ip:=192.168.0.20 \
  use_fake_hardware:=true launch_rviz:=false
```

Terminal 3 - MoveIt 2:

```bash
ros2 launch ur_moveit_config ur_moveit.launch.py \
  ur_type:=ur5e launch_rviz:=true
```

Terminal 4 - pose service:

```bash
ros2 run ur5e_motion_server ur5e_pose_server
```

Terminal 5 - experimental gesture chain in planning mode:

```bash
ros2 launch social_robot_behaviors dynamic_handshake.launch.py execute:=false
```

Terminal 6 - inspect the detected intent and target:

```bash
ros2 topic echo /social_intent
```

```bash
ros2 topic echo /handshake_target
```

Verify the camera transform:

```bash
ros2 run tf2_ros tf2_echo table camera_color_optical_frame
ros2 run tf2_ros tf2_echo base_link table
ros2 run tf2_ros tf2_echo base_link camera_color_optical_frame
```

Offer a handshake and check the requested approach, contact and retreat positions in the `interaction_manager_node` log. With `execute:=false`, the robot must not execute these poses.

Confirm that exactly one `/handshake_target` is captured and that its frame is `table`. The target must remain fixed even if the person moves after detection; this confirms the current snapshot behavior.

In RViz, verify that this target transforms consistently to `base_link` and
that its position corresponds to the visible hand. The current implementation
does not yet publish `/wrist_pose_base`; add that diagnostic topic before
using gesture-driven robot motion.

Do not use `execute:=true`. Face authorisation, gesture classification, workspace limits and the complete robot sequence must be finished and validated first.

## Required next work

Before a complete demonstration can be executed, the project needs:

1. a link between face authorisation and the selected YOLO Pose person;
2. separate and validated `handshake_offer` and `give5_offer` classifiers;
3. a dynamic `give5` interaction manager and launch file;
4. filtering, cooldown and protection against repeated detections;
5. calibrated `base_link -> table -> camera_color_optical_frame` TF chain and
   a `/wrist_pose_base` diagnostic output;
6. camera, workspace, collision and TCP-approach validation in fake hardware;
7. fake-hardware tests followed by instructor approval.

The real-robot procedure will be added only after these nodes are finished and validated.
