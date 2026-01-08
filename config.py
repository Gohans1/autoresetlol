import json
import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict, field
from copy import deepcopy
from constants import DefaultConfig, AppConfig

logger = logging.getLogger("AutoResetLoL")


# Profile-specific settings (coordinates and colors for different LoL clients)
PROFILE_KEYS = [
    "find_match_button_pos",
    "cancel_button_pos",
    "in_queue_pixel_pos",
    "in_queue_pixel_color",
    "accept_match_pixel_pos",
    "accept_match_pixel_color",
    "champ_select_pixel_pos",
    "champ_select_pixel_color",
    "minimize_btn_pos",
]


@dataclass
class ProfileConfig:
    """Configuration for a single profile (coordinates/colors for a specific LoL client)."""

    find_match_button_pos: List[int] = field(
        default_factory=lambda: list(DefaultConfig.FIND_MATCH_POS)
    )
    cancel_button_pos: List[int] = field(
        default_factory=lambda: list(DefaultConfig.CANCEL_POS)
    )
    in_queue_pixel_pos: List[int] = field(
        default_factory=lambda: list(DefaultConfig.QUEUE_PIXEL_POS)
    )
    in_queue_pixel_color: List[int] = field(
        default_factory=lambda: list(DefaultConfig.QUEUE_PIXEL_COLOR)
    )
    accept_match_pixel_pos: List[int] = field(
        default_factory=lambda: list(DefaultConfig.ACCEPT_POS)
    )
    accept_match_pixel_color: List[int] = field(
        default_factory=lambda: list(DefaultConfig.ACCEPT_COLOR)
    )
    champ_select_pixel_pos: List[int] = field(default_factory=lambda: [0, 0])
    champ_select_pixel_color: List[int] = field(default_factory=lambda: [0, 0, 0])
    minimize_btn_pos: List[int] = field(
        default_factory=lambda: list(DefaultConfig.MINIMIZE_POS)
    )

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ProfileConfig":
        """Creates a ProfileConfig instance from a dictionary."""
        valid_keys = cls.__dataclass_fields__.keys()
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)


@dataclass
class BotConfig:
    """Main configuration including global settings and profiles."""

    # Profile System
    current_profile: str = DefaultConfig.CURRENT_PROFILE
    profiles: Dict[str, Dict[str, Any]] = field(default_factory=dict)

    # Global Settings (not profile-specific)
    reset_time: int = DefaultConfig.RESET_TIME
    dimmer_value: int = DefaultConfig.DIMMER_VALUE
    dimmer_enabled: bool = DefaultConfig.DIMMER_ENABLED
    dimmer_mode: str = DefaultConfig.DIMMER_MODE
    dimmer_gaming_value: int = DefaultConfig.DIMMER_GAMING_VALUE
    dimmer_browsing_value: int = DefaultConfig.DIMMER_BROWSING_VALUE
    auto_dimmer_switch_enabled: bool = DefaultConfig.AUTO_DIMMER_SWITCH_ENABLED
    reset_sound_enabled: bool = DefaultConfig.RESET_SOUND_ENABLED
    sound_volume: int = 50
    selected_sound: str = DefaultConfig.SELECTED_SOUND
    auto_startup_enabled: bool = DefaultConfig.AUTO_STARTUP_ENABLED
    auto_accept_enabled: bool = DefaultConfig.AUTO_ACCEPT_ENABLED
    auto_reset_enabled: bool = DefaultConfig.AUTO_RESET_ENABLED
    window_geometry: str = "360x540"

    def __post_init__(self):
        """Ensure at least one profile exists."""
        if not self.profiles:
            self.profiles = {"Profile 1": asdict(ProfileConfig())}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "BotConfig":
        """Creates a BotConfig instance from a dictionary, with migration support."""
        valid_keys = cls.__dataclass_fields__.keys()

        # Check if this is old format (no profiles key, has direct coords)
        needs_migration = "profiles" not in data and "find_match_button_pos" in data

        if needs_migration:
            logger.info("Detected old config format. Migrating to Profile System...")
            return cls._migrate_old_config(data)

        # New format - just filter and load
        filtered_data = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered_data)

    @classmethod
    def _migrate_old_config(cls, old_data: Dict[str, Any]) -> "BotConfig":
        """Migrate old flat config to new profile-based config."""
        # Extract profile-specific keys into Profile 1
        profile_data = {}
        for key in PROFILE_KEYS:
            if key in old_data:
                profile_data[key] = old_data[key]

        # Fill missing profile keys with defaults
        default_profile = asdict(ProfileConfig())
        for key in PROFILE_KEYS:
            if key not in profile_data:
                profile_data[key] = default_profile[key]

        # Extract global settings
        global_keys = [
            k
            for k in cls.__dataclass_fields__.keys()
            if k not in ("profiles", "current_profile")
        ]
        global_data = {k: old_data[k] for k in global_keys if k in old_data}

        # Build new config
        new_config = cls(
            current_profile="Profile 1",
            profiles={"Profile 1": profile_data},
            **global_data,
        )

        logger.info("Migration complete. Old coords saved as 'Profile 1'.")
        return new_config


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
        """Retrieves a configuration value. Profile keys are resolved from current profile."""
        # Check if it's a profile-specific key
        if key in PROFILE_KEYS:
            profile_name = self.config.current_profile
            if profile_name in self.config.profiles:
                return self.config.profiles[profile_name].get(key)
            return None

        # Global key
        if hasattr(self.config, key):
            return getattr(self.config, key)
        return None

    def set(self, key: str, value: Any) -> None:
        """Sets a configuration value and saves to file."""
        # Check if it's a profile-specific key
        if key in PROFILE_KEYS:
            profile_name = self.config.current_profile
            if profile_name in self.config.profiles:
                self.config.profiles[profile_name][key] = value
                self.save_config()
            else:
                logger.warning(f"Profile '{profile_name}' not found.")
            return

        # Global key
        if hasattr(self.config, key):
            setattr(self.config, key, value)
            self.save_config()
        else:
            logger.warning(f"Attempted to set unknown config key: {key}")

    # === Profile Management ===

    def get_current_profile(self) -> str:
        """Get the name of the current active profile."""
        return self.config.current_profile

    def get_profile_names(self) -> List[str]:
        """Get list of all profile names."""
        return list(self.config.profiles.keys())

    def switch_profile(self, profile_name: str) -> bool:
        """Switch to a different profile."""
        if profile_name in self.config.profiles:
            self.config.current_profile = profile_name
            self.save_config()
            logger.info(f"Switched to profile: {profile_name}")
            return True
        logger.warning(f"Profile '{profile_name}' not found.")
        return False

    def create_profile(self, name: str, copy_from: Optional[str] = None) -> bool:
        """Create a new profile. Optionally copy from existing profile."""
        if name in self.config.profiles:
            logger.warning(f"Profile '{name}' already exists.")
            return False

        if copy_from and copy_from in self.config.profiles:
            self.config.profiles[name] = deepcopy(self.config.profiles[copy_from])
        else:
            self.config.profiles[name] = asdict(ProfileConfig())

        self.save_config()
        logger.info(f"Created profile: {name}")
        return True

    def rename_profile(self, old_name: str, new_name: str) -> bool:
        """Rename an existing profile."""
        if old_name not in self.config.profiles:
            logger.warning(f"Profile '{old_name}' not found.")
            return False
        if new_name in self.config.profiles:
            logger.warning(f"Profile '{new_name}' already exists.")
            return False

        self.config.profiles[new_name] = self.config.profiles.pop(old_name)
        if self.config.current_profile == old_name:
            self.config.current_profile = new_name

        self.save_config()
        logger.info(f"Renamed profile: {old_name} -> {new_name}")
        return True

    def delete_profile(self, name: str) -> bool:
        """Delete a profile. Cannot delete the last profile."""
        if name not in self.config.profiles:
            logger.warning(f"Profile '{name}' not found.")
            return False
        if len(self.config.profiles) <= 1:
            logger.warning("Cannot delete the last profile.")
            return False

        del self.config.profiles[name]

        # Switch to first available profile if current was deleted
        if self.config.current_profile == name:
            self.config.current_profile = list(self.config.profiles.keys())[0]

        self.save_config()
        logger.info(f"Deleted profile: {name}")
        return True

    def get_profile_data(self, profile_name: Optional[str] = None) -> Dict[str, Any]:
        """Get all data for a profile."""
        name = profile_name or self.config.current_profile
        if name in self.config.profiles:
            return self.config.profiles[name]
        return {}

    def set_profile_data(
        self, key: str, value: Any, profile_name: Optional[str] = None
    ) -> None:
        """Set a specific value in a profile."""
        name = profile_name or self.config.current_profile
        if name in self.config.profiles and key in PROFILE_KEYS:
            self.config.profiles[name][key] = value
            self.save_config()


# Global instance
config_manager = ConfigManager()
