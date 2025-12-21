import json
import os

CONFIG_FILE = "config.json"

DEFAULT_CONFIG = {
    "find_match_button_pos": [100, 200],
    "cancel_button_pos": [100, 200],
    "in_queue_pixel_pos": [105, 250],
    "in_queue_pixel_color": [20, 25, 30],
    "accept_match_pixel_pos": [500, 400],
    "accept_match_pixel_color": [10, 200, 50],
    "reset_time": 120,
}


class ConfigManager:
    def __init__(self, config_file=CONFIG_FILE):
        self.config_file = config_file
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self):
        """Loads configuration from the JSON file. Creates it if it doesn't exist."""
        if not os.path.exists(self.config_file):
            print(f"Config file not found. Creating default {self.config_file}...")
            self.save_config()
        else:
            try:
                with open(self.config_file, "r") as f:
                    loaded_config = json.load(f)
                    # Update current config with loaded values, keeping defaults for missing keys
                    self.config.update(loaded_config)
                print(f"Config loaded from {self.config_file}")
            except json.JSONDecodeError:
                print(f"Error decoding {self.config_file}. Using default config.")
                # Optionally backup the corrupted file and recreate default?
                # For now, just using defaults in memory is safer than overwriting.
            except Exception as e:
                print(f"Error loading config: {e}")

    def save_config(self):
        """Saves the current configuration to the JSON file."""
        try:
            with open(self.config_file, "w") as f:
                json.dump(self.config, f, indent=4)
            print(f"Config saved to {self.config_file}")
        except Exception as e:
            print(f"Error saving config: {e}")

    def get(self, key):
        """Retrieves a configuration value."""
        return self.config.get(key, DEFAULT_CONFIG.get(key))

    def set(self, key, value):
        """Sets a configuration value and saves to file."""
        self.config[key] = value
        self.save_config()


# Global instance for easy access
config_manager = ConfigManager()
