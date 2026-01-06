import json
import os
import logging
from typing import List, Dict, Any, Optional, Union
from dataclasses import dataclass, asdict, field
from constants import DefaultConfig, AppConfig

logger = logging.getLogger("AutoResetLoL")


@dataclass
class BotConfig:
    find_match_button_pos: List[int] = field(
        default_factory=lambda: DefaultConfig.FIND_MATCH_POS
    )
    cancel_button_pos: List[int] = field(
        default_factory=lambda: DefaultConfig.CANCEL_POS
    )
    in_queue_pixel_pos: List[int] = field(
        default_factory=lambda: DefaultConfig.QUEUE_PIXEL_POS
    )
    in_queue_pixel_color: List[int] = field(
        default_factory=lambda: DefaultConfig.QUEUE_PIXEL_COLOR
    )
    accept_match_pixel_pos: List[int] = field(
        default_factory=lambda: DefaultConfig.ACCEPT_POS
    )
    accept_match_pixel_color: List[int] = field(
        default_factory=lambda: DefaultConfig.ACCEPT_COLOR
    )
    champ_select_pixel_pos: List[int] = field(default_factory=lambda: [0, 0])
    champ_select_pixel_color: List[int] = field(default_factory=lambda: [0, 0, 0])
    minimize_btn_pos: List[int] = field(
        default_factory=lambda: DefaultConfig.MINIMIZE_POS
    )
    reset_time: int = DefaultConfig.RESET_TIME
    dimmer_value: int = DefaultConfig.DIMMER_VALUE
    dimmer_enabled: bool = DefaultConfig.DIMMER_ENABLED
    dimmer_mode: str = DefaultConfig.DIMMER_MODE  # "gaming" or "browsing"
    dimmer_gaming_value: int = DefaultConfig.DIMMER_GAMING_VALUE
    dimmer_browsing_value: int = DefaultConfig.DIMMER_BROWSING_VALUE
    reset_sound_enabled: bool = DefaultConfig.RESET_SOUND_ENABLED
    sound_volume: int = 50  # Default 50%
    selected_sound: str = DefaultConfig.SELECTED_SOUND  # Sound file name
    auto_startup_enabled: bool = DefaultConfig.AUTO_STARTUP_ENABLED
    auto_accept_enabled: bool = DefaultConfig.AUTO_ACCEPT_ENABLED
    auto_reset_enabled: bool = DefaultConfig.AUTO_RESET_ENABLED
    window_geometry: str = "360x540"

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotConfig":
        """
        Creates a BotConfig instance from a dictionary, filtering unknown keys
        and ensuring types where possible (basic validation).
        """
        valid_keys = cls.__dataclass_fields__.keys()
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


class ConfigManager:
    def __init__(self, config_file: Optional[str] = None):
        self.config_file = config_file or AppConfig.CONFIG_FILE
        self.config: BotConfig = BotConfig()
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
        """Saves the current configuration to the JSON file."""
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

    def set(self, key: str, value: Any) -> None:
        """Sets a configuration value and saves to file."""
        if hasattr(self.config, key):
            setattr(self.config, key, value)
            self.save_config()
        else:
            logger.warning(f"Attempted to set unknown config key: {key}")


# Global instance
config_manager = ConfigManager()
