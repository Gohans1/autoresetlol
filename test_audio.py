import ctypes
import time
import os


def play_mp3_with_volume(file_path, volume):
    """
    Plays an MP3 file with a specific volume using Windows MCI.
    volume: 0 to 100
    """
    mci = ctypes.windll.winmm.mciSendStringW

    # Short path to avoid issues with spaces
    # Actually, wrapping in quotes is usually enough for MCI
    alias = "bot_sound"

    # Close any existing instance
    mci(f"close {alias}", None, 0, 0)

    # Open the file
    res = mci(f'open "{file_path}" type mpegvideo alias {alias}', None, 0, 0)
    if res != 0:
        return False

    # Set volume (MCI volume is 0 to 1000)
    mci_volume = int(volume * 10)
    mci(f"setaudio {alias} volume to {mci_volume}", None, 0, 0)

    # Play
    mci(f"play {alias}", None, 0, 0)
    return True


if __name__ == "__main__":
    # Test
    p = os.path.abspath("assets/notify.mp3")
    print(f"Playing {p} at 50% volume")
    play_mp3_with_volume(p, 50)
    time.sleep(3)
