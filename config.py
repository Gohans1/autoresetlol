import json
import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
import threading
from constants import DefaultConfig, AppConfig
from arena_config import champion_id, normalize_pick_chain

logger = logging.getLogger("AutoResetLoL")


def _normalize_arena_recent(value: object) -> Dict[str, List[int]]:
    """Normalize recent champion IDs and remove duplicate aliases."""
    if not isinstance(value, dict):
        return {}
    recent: Dict[str, List[int]] = {}
    for key, values in value.items():
        if not isinstance(values, (list, tuple)):
            continue
        normalized: List[int] = []
        for raw_id in values:
            cid = champion_id(raw_id)
            if cid > 0 and cid not in normalized:
                normalized.append(cid)
            if len(normalized) >= 5:
                break
        recent[str(key)] = normalized
    return recent


def _normalize_arena_names(value: object) -> Dict[str, str]:
    """Merge cached names that use base and Arena alias IDs."""
    if not isinstance(value, dict):
        return {}
    names: Dict[str, str] = {}
    for raw_id, raw_name in value.items():
        cid = champion_id(raw_id)
        name = raw_name.strip() if isinstance(raw_name, str) else ""
        if cid > 0 and name:
            names[str(cid)] = name
    return names


def _normalize_arena_value(key: str, value: Any) -> Any:
    """Keep every Arena ID at the config boundary in canonical form."""
    if key == "arena_ban_champ":
        return champion_id(value)
    if key == "arena_pick_chain":
        return list(normalize_pick_chain(value))
    if key == "arena_recent":
        return _normalize_arena_recent(value)
    if key == "arena_champion_names":
        return _normalize_arena_names(value)
    return value


@dataclass
class BotConfig:
    """Configuration — dimmer + LCU features only (v2.0).

    Không còn: profile tọa độ, pixel colors, reset queue, timer, âm thanh
    báo reset. Tất cả tính năng giờ đọc trạng thái từ LCU API.
    """

    # Dimmer
    dimmer_value: int = DefaultConfig.DIMMER_VALUE
    dimmer_enabled: bool = DefaultConfig.DIMMER_ENABLED
    dimmer_mode: str = DefaultConfig.DIMMER_MODE
    dimmer_gaming_value: int = DefaultConfig.DIMMER_GAMING_VALUE
    dimmer_browsing_value: int = DefaultConfig.DIMMER_BROWSING_VALUE
    auto_dimmer_switch_enabled: bool = DefaultConfig.AUTO_DIMMER_SWITCH_ENABLED

    # LCU features
    auto_startup_enabled: bool = DefaultConfig.AUTO_STARTUP_ENABLED
    auto_accept_enabled: bool = DefaultConfig.AUTO_ACCEPT_ENABLED
    auto_ban_enabled: bool = DefaultConfig.AUTO_BAN_ENABLED
    auto_pick_enabled: bool = DefaultConfig.AUTO_PICK_ENABLED
    discord_notify_ban: bool = DefaultConfig.DISCORD_NOTIFY_BAN
    discord_notify_pick: bool = DefaultConfig.DISCORD_NOTIFY_PICK
    discord_notify_in_game: bool = DefaultConfig.DISCORD_NOTIFY_IN_GAME
    arena_ban_champ: int = DefaultConfig.ARENA_BAN_CHAMP
    arena_pick_chain: List[int] = field(
        default_factory=lambda: list(DefaultConfig.ARENA_PICK_CHAIN)
    )

    # App UX
    window_geometry: str = AppConfig.GEOMETRY
    ui_scale: float = DefaultConfig.UI_SCALE  # UI zoom scale (0.8 - 2.0)
    # Arena MRU — {field: [champion_id,...]} — tướng chọn gần nhất mỗi field
    # (tối đa 5) để gợi ý lên đầu khi mở dropdown
    arena_recent: Dict[str, List[int]] = field(default_factory=dict)
    # Cache tên tướng — {champion_id: name}; giúp app mở lại vẫn hiện tên
    # ngay cả khi client chưa kết nối.
    arena_champion_names: Dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotConfig":
        """Load config and normalize Arena IDs from older client data."""
        valid_keys = cls.__dataclass_fields__.keys()
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        config = cls(**filtered_data)
        for key in (
            "arena_ban_champ",
            "arena_pick_chain",
            "arena_recent",
            "arena_champion_names",
        ):
            setattr(config, key, _normalize_arena_value(key, getattr(config, key)))
        return config


class ConfigManager:
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or AppConfig.CONFIG_FILE
        self.config: BotConfig = BotConfig()
        self._lock = threading.Lock()
        self.load_config()

    def load_config(self) -> None:
        """Loads configuration from the JSON file. Creates it if it doesn't exist."""
        if not os.path.exists(self.config_file):
            logger.info(
                f"Config file not found. Creating default {self.config_file}..."
            )
            self.save_config()
        else:
            try:
                with open(self.config_file, "r") as f:
                    data = json.load(f)
                    self.config = BotConfig.from_dict(data)
                logger.info(f"Config loaded from {self.config_file}")
            except json.JSONDecodeError:
                logger.error(
                    f"Error decoding {self.config_file}. Using default config."
                )
            except Exception as e:
                logger.error(f"Error loading config: {e}")

    def save_config(self) -> None:
        """Saves the current configuration to the JSON file.

        Lock: bot/watcher thread và GUI thread có thể ghi đồng thời — write
        không lock có thể làm hỏng config.json.
        """
        with self._lock:
            try:
                with open(self.config_file, "w") as f:
                    json.dump(asdict(self.config), f, indent=4)
                logger.info(f"Config saved to {self.config_file}")
            except Exception as e:
                logger.error(f"Error saving config: {e}")

    def get(self, key: str) -> Any:
        """Retrieves a configuration value."""
        if hasattr(self.config, key):
            return getattr(self.config, key)
        return None

    def set(self, key: str, value: Any, save: bool = True) -> None:
        """Sets a configuration value and saves to file.

        save=False batches multiple updates into one file write (e.g. the
        dimmer slider drag handler, which fires dozens of times per second).
        """
        if hasattr(self.config, key):
            setattr(self.config, key, _normalize_arena_value(key, value))
            if save:
                self.save_config()
        else:
            logger.warning(f"Attempted to set unknown config key: {key}")


# Global instance
config_manager = ConfigManager()
