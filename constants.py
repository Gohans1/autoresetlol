from enum import Enum, auto
from typing import Tuple, List, Dict, Any
import os
import sys


def get_base_dir() -> str:
    """Returns the base directory of the application."""
    if getattr(sys, "frozen", False):
        # Running as a compiled executable
        return os.path.dirname(sys.executable)
    # Running as a script
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = get_base_dir()


class AppConfig:
    APP_NAME: str = "Anti-Fate Engine"
    VERSION: str = "v7.14"
    GEOMETRY: str = "340x480"
    THEME_MODE: str = "Dark"
    THEME_COLOR: str = "blue"
    CONFIG_FILE: str = os.path.join(BASE_DIR, "config.json")
    LOG_FILE: str = os.path.join(BASE_DIR, "autoresetlol.log")
    VERIFY_TIMEOUT: int = 25


class GameInfo:
    CLIENT_TITLE: str = "League of Legends"
    GAME_TITLE: str = "League of Legends (TM) Client"


class Colors:
    # Shadcn-like palette
    ZINC_50: str = "#fafafa"
    ZINC_100: str = "#f4f4f5"
    ZINC_200: str = "#e4e4e7"
    ZINC_300: str = "#d4d4d8"
    ZINC_400: str = "#a1a1aa"
    ZINC_500: str = "#71717a"
    ZINC_600: str = "#52525b"
    ZINC_700: str = "#3f3f46"
    ZINC_800: str = "#27272a"
    ZINC_900: str = "#18181b"

    EMERALD_400: str = "#34d399"
    SKY_400: str = "#38bdf8"
    AMBER_400: str = "#fbbf24"
    ROSE_400: str = "#fb7185"
    RED_200: str = "#fecaca"
    RED_800: str = "#991b1b"
    RED_900: str = "#7f1d1d"

    # Logic colors
    STATUS_GREEN: str = EMERALD_400
    STATUS_RED: str = ROSE_400
    STATUS_BLUE: str = SKY_400
    STATUS_ORANGE: str = AMBER_400
    STATUS_GRAY: str = ZINC_400


class DefaultConfig:
    FIND_MATCH_POS: List[int] = [100, 200]
    CANCEL_POS: List[int] = [100, 200]
    QUEUE_PIXEL_POS: List[int] = [105, 250]
    QUEUE_PIXEL_COLOR: List[int] = [20, 25, 30]
    ACCEPT_POS: List[int] = [500, 400]
    ACCEPT_COLOR: List[int] = [10, 200, 50]
    MINIMIZE_POS: List[int] = [0, 0]
    RESET_TIME: int = 120
    DIMMER_VALUE: int = 100
    DIMMER_ENABLED: bool = True
    RESET_SOUND_ENABLED: bool = True
    AUTO_STARTUP_ENABLED: bool = False


class UIStatus:
    READY = "Status: Ready"
    RUNNING = "Status: Running..."
    STOPPED = "Stopped"
    SEARCHING = "Searching... ({}/{})s"
    MATCH_FOUND = "MATCH FOUND! Accepting..."
    ACCEPTED = "Accepted. Monitoring..."
    RESETTING = "Resetting Queue..."
    DODGE_DETECTED = "Dodge detected! Resetting..."
    RESTARTING = "Queue Reset. Restarting..."
    VERIFYING = "Verifying Champ Select... {}s"
    CHAMP_SELECT = "Champ Select Confirmed!"
    STANDBY = "Standby (In Game/Lobby)..."
