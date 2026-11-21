#!/usr/bin/env python3

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    authorised_user = LaunchConfiguration('authorised_user')
    camera_index = LaunchConfiguration('camera_index')
    image_topic = LaunchConfiguration('image_topic')
    microphone_index = LaunchConfiguration('microphone_index')

    speaker_env = {
        'HRI_SPEAKER_DEVICE': LaunchConfiguration('speaker_device'),
        'HRI_SPEECH_VOICE': LaunchConfiguration('speech_voice'),
    }

    return LaunchDescription([
        DeclareLaunchArgument(
            'authorised_user',
            description='Image filename in Documentation/Files/Camera&Microphone (e.g. Manel.png)',
        ),
        DeclareLaunchArgument('camera_index', default_value='0'),
        DeclareLaunchArgument(
            'image_topic',
            default_value='',
            description='ROS colour image topic. Leave empty to use camera_index.',
        ),
        DeclareLaunchArgument(
            'microphone_index',
            default_value='6',
            description='PortAudio microphone index. Use -1 for the system default.',
        ),
        DeclareLaunchArgument(
            'speaker_device',
            default_value='default',
            description='ALSA playback device (see aplay -l).',
        ),
        DeclareLaunchArgument(
            'speech_voice',
            default_value='en-us+f3',
            description='eSpeak NG voice and optional variant, such as en-gb.',
        ),
        Node(
            package='social_robot_hri',
            executable='voice_node',
            name='voice_node',
            output='screen',
            additional_env=speaker_env,
            parameters=[{
                'microphone_index': ParameterValue(microphone_index, value_type=int),
                'speech_feedback': True,
            }],
        ),
        Node(
            package='social_robot_hri',
            executable='voice_interpreter_node',
            name='voice_interpreter_node',
            output='screen',
            additional_env=speaker_env,
            parameters=[{
                'output_topic': '/social_behavior/request',
                'speech_feedback': True,
            }],
        ),
        Node(
            package='social_robot_hri',
            executable='face_verification_node',
            name='face_verification_node',
            output='screen',
            additional_env=speaker_env,
            parameters=[{
                'authorised_user': ParameterValue(authorised_user, value_type=str),
                'camera_index': ParameterValue(camera_index, value_type=int),
                'image_topic': ParameterValue(image_topic, value_type=str),
            }],
        ),
    ])
