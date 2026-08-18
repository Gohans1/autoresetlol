from typing import List, Dict, Tuple
import os
import sys


def get_resource_dir() -> str:
    """Returns the base directory for bundled resources."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_config_dir() -> str:
    """Returns the directory for persistent configuration."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


RESOURCE_DIR = get_resource_dir()
CONFIG_DIR = get_config_dir()


class AppConfig:
    APP_NAME: str = "Anti-Fate Engine"
    VERSION: str = (
        "v2.0"  # Dimmer + LCU API only — pixel/reset/timer/sound/profile removed
    )
    GEOMETRY: str = "720x520"  # Wide 2-column: Arena (left) + Status/Dimmer/LCU (right)
    THEME_MODE: str = "Dark"
    THEME_COLOR: str = "blue"
    CONFIG_FILE: str = os.path.join(CONFIG_DIR, "config.json")
    LOG_FILE: str = os.path.join(CONFIG_DIR, "autoresetlol.log")
    APP_ICON: str = os.path.join(RESOURCE_DIR, "assets", "avatar.ico")
    APP_AVATAR: str = os.path.join(RESOURCE_DIR, "assets", "avatar.png")
    VERIFY_TIMEOUT: int = 25
    FONT_FAMILY: str = "Inter"


class Colors:
    # Flexoki Dark Palette (HSL to Hex)
    BG: str = "#100f0f"  # background: 0 3% 6%
    FG: str = "#cecdc3"  # foreground: 55 10% 79%
    CARD: str = "#100f0f"  # card: 0 3% 6%
    CARD_FG: str = "#cecdc3"  # card-foreground: 55 10% 79%
    PRIMARY: str = "#cecdc3"  # primary: 55 10% 79%
    PRIMARY_FG: str = "#100f0f"  # primary-foreground: 0 3% 6%
    SECONDARY: str = "#1c1b1a"  # secondary: 30 4% 11%
    MUTED: str = "#1c1b1a"  # muted: 30 4% 11%
    MUTED_FG: str = "#878580"  # muted-foreground: 43 3% 52%
    BORDER: str = "#282726"  # border: 30 3% 15%
    INPUT: str = "#282726"  # input: 30 3% 15%
    RING: str = "#3f3e3d"  # ring: 30 3% 24%

    # Flexoki Primary Colors
    RED: str = "#d65d4e"  # red-primary: 5 61% 54%
    ORANGE: str = "#da702c"  # orange-primary: 23 70% 51%
    YELLOW: str = "#d0a215"  # yellow-primary: 45 82% 45%
    GREEN: str = "#879a39"  # green-primary: 72 46% 41%
    CYAN: str = "#3aa99f"  # cyan-primary: 175 49% 45%
    BLUE: str = "#4385be"  # blue-primary: 208 49% 50%
    PURPLE: str = "#8b7ec8"  # purple-primary: 251 40% 64%
    MAGENTA: str = "#ce5d97"  # magenta-primary: 329 54% 59%

    # Logic colors
    STATUS_GREEN: str = GREEN
    STATUS_RED: str = RED
    STATUS_BLUE: str = BLUE
    STATUS_ORANGE: str = ORANGE
    STATUS_GRAY: str = MUTED_FG


class DefaultConfig:
    DIMMER_VALUE: int = 100
    DIMMER_ENABLED: bool = True
    DIMMER_MODE: str = "browsing"  # "gaming" or "browsing"
    DIMMER_GAMING_VALUE: int = 100  # Brightness for gaming mode
    DIMMER_BROWSING_VALUE: int = 100  # Brightness for browsing mode
    AUTO_DIMMER_SWITCH_ENABLED: bool = (
        True  # Auto switch gaming/browsing theo trạng thái trận (LCU)
    )
    AUTO_STARTUP_ENABLED: bool = False
    AUTO_ACCEPT_ENABLED: bool = True  # Auto-accept match khi có trận (LCU)
    AUTO_BAN_ENABLED: bool = False  # Arena: auto-ban preset champion
    AUTO_PICK_ENABLED: bool = False  # Arena: auto-pick main -> backups (hover only)
    ARENA_BAN_CHAMP: int = 0  # Champion id to ban in Arena (0 = unset)
    ARENA_PICK_CHAIN: List[int] = [0, 0, 0, 0]  # Main + 3 backups, priority order
    UI_SCALE: float = 1.0  # UI zoom scale (0.8 - 1.5)


class UIStatus:
    READY = "Sẵn sàng"
    RUNNING = "Đang hoạt động"
    STOPPED = "Đã dừng"
    SEARCHING = "Đang tìm trận"
    MATCH_FOUND = "Có trận mới — đang chờ xác nhận"
    ACCEPTED = "Đã nhận trận — đang vào chọn tướng"
    VERIFYING = "Đang vào trận — còn {} giây"
    CHAMP_SELECT = "Đang chọn tướng"
    DODGED = "Trận bị hủy — đang tìm trận mới"
