#!/usr/bin/env python3
"""Authorise once by face, then gate HRI behavior requests."""

from pathlib import Path

import cv2
import face_recognition
import numpy as np
import rclpy
from rclpy.node import Node
from rclpy.qos import QoSPresetProfiles
from sensor_msgs.msg import Image
from std_msgs.msg import String

from .speech_feedback import UNRECOGNISED_TOPIC, speak


class FaceVerifier:
    """Compare camera faces with one reference image."""

    def __init__(self, reference_image, camera_index=0, tolerance=0.6):
        self.reference_image = Path(reference_image).expanduser()
        self.camera_index = camera_index
        self.tolerance = tolerance

    def verify(self, read_frame=None):
        if not self.reference_image.is_file():
            raise FileNotFoundError(
                f'Reference image not found: {self.reference_image}'
            )

        image = face_recognition.load_image_file(str(self.reference_image))
        encodings = face_recognition.face_encodings(image)
        if not encodings:
            raise RuntimeError('No face found in the reference image.')

        camera = None
        if read_frame is None:
            camera = cv2.VideoCapture(self.camera_index)
            if not camera.isOpened():
                camera.release()
                raise RuntimeError(f'Camera {self.camera_index} is not available.')
            read_frame = camera.read

        print('[FACE] Look at the camera. Press Q to cancel.')
        try:
            while rclpy.ok():
                ok, frame = read_frame()
                if not ok:
                    continue

                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                faces = face_recognition.face_encodings(rgb_frame)
                authorised = bool(faces) and face_recognition.compare_faces(
                    [encodings[0]], faces[0], tolerance=self.tolerance
                )[0]

                label = 'AUTHORISED' if authorised else 'UNKNOWN'
                color = (0, 255, 0) if authorised else (0, 0, 255)
                cv2.putText(
                    frame, label, (30, 40), cv2.FONT_HERSHEY_SIMPLEX,
                    1, color, 2
                )
                cv2.imshow('Face verification', frame)

                if authorised:
                    cv2.waitKey(750)
                    return True
                if cv2.waitKey(1) & 0xFF == ord('q'):
                    return False
            return False
        finally:
            if camera is not None:
                camera.release()
            cv2.destroyAllWindows()


class FaceVerificationNode(Node):
    def __init__(self):
        super().__init__('face_verification_node')
        self.declare_parameter('authorised_user', '')
        self.declare_parameter('camera_index', 0)
        self.declare_parameter('image_topic', '')
        self.declare_parameter('tolerance', 0.6)
        self.declare_parameter('input_topic', '/social_behavior/request')
        self.declare_parameter('output_topic', '/social_behavior')

    def verify_user(self):
        authorised_user = self.get_parameter('authorised_user').value
        if not authorised_user or Path(authorised_user).name != authorised_user:
            raise ValueError('Set authorised_user to an image filename, such as Manel.png.')

        reference_image = (
            Path.home() / 'UR5e_social_robotics' / 'Documentation' / 'Files'
            / 'Camera&Microphone' / authorised_user
        )

        verifier = FaceVerifier(
            reference_image,
            camera_index=int(self.get_parameter('camera_index').value),
            tolerance=float(self.get_parameter('tolerance').value),
        )
        image_topic = self.get_parameter('image_topic').value
        if image_topic:
            self.latest_image = None
            qos = QoSPresetProfiles.SENSOR_DATA.value
            qos.depth = 1
            subscription = self.create_subscription(Image, image_topic, self.image_callback, qos)
            self.get_logger().info(f'Waiting for colour images on {image_topic}')
            try:
                self.authorised = verifier.verify(self.read_topic_frame)
            finally:
                self.destroy_subscription(subscription)
        else:
            self.authorised = verifier.verify()

        self.authorised_name = Path(authorised_user).stem
        if not self.authorised:
            self.get_logger().error('Face verification failed. Requests are blocked.')
            speak(self, f'I am sorry, you are not the authorised user {self.authorised_name}')
        else:
            speak(self, f'Hello {self.authorised_name}')
            self.get_logger().info('User authorised. HRI requests are enabled.')
            self.pending_behaviors = {}
            self.feedback_subscription = self.create_subscription(
                String, UNRECOGNISED_TOPIC, self.unrecognised_callback, 10
            )
            self.result_subscription = self.create_subscription(
                String, '/social_behavior/result', self.result_callback, 10
            )

        self.publisher_ = self.create_publisher(
            String, str(self.get_parameter('output_topic').value), 10
        )
        self.subscription = self.create_subscription(
            String,
            str(self.get_parameter('input_topic').value),
            self.request_callback,
            10,
        )

    def image_callback(self, msg):
        self.latest_image = msg

    def read_topic_frame(self):
        rclpy.spin_once(self, timeout_sec=0.25)
        msg = self.latest_image
        self.latest_image = None
        if msg is None:
            return False, None
        if msg.encoding not in ('rgb8', 'bgr8'):
            raise RuntimeError(f'Unsupported colour image encoding: {msg.encoding}')

        row_bytes = msg.width * 3
        if not msg.width or not msg.height or msg.step < row_bytes:
            raise RuntimeError('Invalid colour image dimensions or row stride.')
        if len(msg.data) != msg.height * msg.step:
            raise RuntimeError('Invalid colour image buffer size.')

        # ROS image rows can contain padding after the last pixel.
        rows = np.frombuffer(msg.data, dtype=np.uint8).reshape(msg.height, msg.step)
        frame = rows[:, :row_bytes].reshape(msg.height, msg.width, 3)
        if msg.encoding == 'rgb8':
            return True, cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
        return True, frame.copy()

    def request_callback(self, msg):
        if not self.authorised:
            self.get_logger().warn('Rejected behavior request: user not authorised.')
            return
        command = msg.data.strip()
        if self.pending_behaviors and command != 'stop':
            self.get_logger().info(f'Ignored {command} while a sequence is in progress.')
            return
        if not self.count_publishers('/social_behavior/result'):
            self.get_logger().warning(
                'No publisher on /social_behavior/result. Restart the updated '
                'social_robot_behaviors node before sending motion commands.'
            )
            if command == 'stop':
                self.publisher_.publish(msg)
            return
        if command != 'stop':
            speak(self, f'I will start {command}')
        self.pending_behaviors[command] = self.pending_behaviors.get(command, 0) + 1
        self.publisher_.publish(msg)
        self.get_logger().info(f'Authorised behavior: {command}')

    def unrecognised_callback(self, _msg):
        if not self.pending_behaviors:
            speak(self, 'I have not understood')

    def result_callback(self, msg):
        count = self.pending_behaviors.get(msg.data, 0)
        if count == 0:
            return
        if count == 1:
            del self.pending_behaviors[msg.data]
        else:
            self.pending_behaviors[msg.data] = count - 1
        if not self.pending_behaviors:
            speak(self, f'{self.authorised_name}, I am listening')


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = FaceVerificationNode()
        node.verify_user()
        if rclpy.ok():
            rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    except (RuntimeError, FileNotFoundError, ValueError) as error:
        print(f'[FACE] {error}')
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
