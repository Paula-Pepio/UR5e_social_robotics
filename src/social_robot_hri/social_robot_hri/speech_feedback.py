"""Play the HRI prompts on the Teacher PC."""

import os
import subprocess
import time


UNRECOGNISED_TOPIC = '/voice/unrecognised'


def speak(node, text):
    device = os.environ.get('HRI_SPEAKER_DEVICE', 'default')
    voice = os.environ.get('HRI_SPEECH_VOICE', 'en-us+f3')
    try:
        wave = subprocess.run(
            ['espeak-ng', '--stdout', '-v', voice, '-s', '150', '--', text],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=10,
        ).stdout
        for attempt in range(5):
            try:
                subprocess.run(
                    ['aplay', '-q', '-D', device],
                    input=wave,
                    check=True,
                    stderr=subprocess.PIPE,
                    timeout=10,
                    env={**os.environ, 'LC_ALL': 'C'},
                )
                break
            except subprocess.CalledProcessError as error:
                if attempt == 4 or b'Device or resource busy' not in (error.stderr or b''):
                    raise
                time.sleep(0.3)
        node.get_logger().info(f'Speech played on {device}: {text}')
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode(errors='replace').strip() if error.stderr else str(error)
        node.get_logger().warning(f'Speech output on {device} failed: {detail}')
    except (OSError, subprocess.TimeoutExpired) as error:
        node.get_logger().warning(f'Speech output on {device} failed: {error}')
