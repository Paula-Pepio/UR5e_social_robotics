#!/usr/bin/env python3
"""Print microphone transcriptions without publishing ROS messages."""

import argparse
import sys

import rclpy
from rclpy.node import Node
import speech_recognition as sr


class VoiceTranscriptionNode(Node):
    def __init__(self, microphone, language):
        super().__init__('voice_transcription_node')
        self.microphone = microphone
        self.language = language
        self.recognizer = sr.Recognizer()
        self.recognizer.operation_timeout = 10

    def listen(self):
        with self.microphone as source:
            self.get_logger().info('Calibrating microphone. Please stay quiet.')
            self.recognizer.adjust_for_ambient_noise(source, duration=0.5)
            while rclpy.ok():
                self.get_logger().info('Listening...')
                try:
                    audio = self.recognizer.listen(
                        source, timeout=5, phrase_time_limit=4
                    )
                    text = self.recognizer.recognize_google(
                        audio, language=self.language
                    )
                except sr.WaitTimeoutError:
                    self.get_logger().info('No speech detected.')
                except sr.UnknownValueError:
                    self.get_logger().warning('Speech not understood.')
                except sr.RequestError as error:
                    self.get_logger().error(f'Speech recognition service: {error}')
                    return 1
                else:
                    self.get_logger().info(f'Transcription: {text!r}')
        return 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--list-mics', action='store_true')
    parser.add_argument('--mic', type=int, help='PortAudio input device index')
    parser.add_argument('--language', default='en-US')
    args = parser.parse_args()

    devices = sr.Microphone.list_microphone_names()
    if not devices:
        print('PortAudio found no audio devices in this environment.', file=sys.stderr)
        return 1
    if args.list_mics:
        for index, name in enumerate(devices):
            print(f'{index}: {name}')
        return 0
    if args.mic is not None and not 0 <= args.mic < len(devices):
        parser.error('Invalid microphone index. Run with --list-mics.')

    rclpy.init()
    node = None
    try:
        microphone = sr.Microphone(device_index=args.mic)
        node = VoiceTranscriptionNode(microphone, args.language)
        return node.listen()
    except (OSError, AttributeError) as error:
        print(f'Could not open or read the microphone: {error}', file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 0
    finally:
        if node is not None:
            node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    sys.exit(main())
