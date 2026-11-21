#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from std_msgs.msg import String
import speech_recognition as sr

from .speech_feedback import UNRECOGNISED_TOPIC


class VoiceNode(Node):

    def __init__(self):
        super().__init__('voice_node')

        self.publisher_ = self.create_publisher(
            String,
            '/voice/text',
            10
        )

        self.declare_parameter('microphone_index', 6)
        self.declare_parameter('language', 'en-US')
        self.declare_parameter('speech_feedback', False)
        self.feedback_publisher = None
        if self.get_parameter('speech_feedback').value:
            self.feedback_publisher = self.create_publisher(String, UNRECOGNISED_TOPIC, 10)
        self.declare_parameter('timeout', 5.0)
        self.declare_parameter('phrase_time_limit', 4.0)

        self.recognizer = sr.Recognizer()
        microphone_index = self.get_parameter('microphone_index').value
        self.microphone = sr.Microphone(
            device_index=None if microphone_index == -1 else microphone_index
        )
        self.get_logger().info(f'Microphone index: {microphone_index}')
        with self.microphone as source:
            self.get_logger().info('Calibrating microphone...')
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)

        self.get_logger().info('Voice node started.')
        self.get_logger().info('Say a command after the listening prompt.')

        self.timer = self.create_timer(0.5, self.read_command)

    def read_command(self):
        try:
            with self.microphone as source:
                self.get_logger().info('Listening...')
                audio = self.recognizer.listen(
                    source,
                    timeout=float(self.get_parameter('timeout').value),
                    phrase_time_limit=float(
                        self.get_parameter('phrase_time_limit').value
                    ),
                )
            text = self.recognizer.recognize_google(
                audio,
                language=str(self.get_parameter('language').value),
            )
        except sr.WaitTimeoutError:
            return
        except sr.UnknownValueError:
            self.get_logger().warn('Speech not understood.')
            if self.feedback_publisher is not None:
                self.feedback_publisher.publish(String())
            return
        except sr.RequestError as error:
            self.get_logger().error(f'Speech-recognition service error: {error}')
            return

        msg = String()
        msg.data = text
        self.publisher_.publish(msg)

        self.get_logger().info(f'Published voice text: {text}')


def main(args=None):
    rclpy.init(args=args)
    node = VoiceNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()
