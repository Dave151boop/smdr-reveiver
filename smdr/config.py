"""
Configuration management for SMDR Service.
Handles reading and writing service configuration.
"""
import json
from pathlib import Path

CONFIG_FILE = "smdr_config.json"

DEFAULT_CONFIG = {
    "port": 7004,
    "log_file": "smdr.log",
    "auto_start": True
}


class SMDRConfig:
    def __init__(self, config_path=None):
        if config_path is None:
            # Try to find config in common locations
            self.config_path = self._find_config_file()
        else:
            self.config_path = Path(config_path)
        
        self.config = self._load_config()
    
    def _find_config_file(self):
        """Find the config file in common locations."""
        # Check current directory
        local_config = Path.cwd() / CONFIG_FILE
        if local_config.exists():
            return local_config
        
        # Check Program Files
        program_files = Path("C:/Program Files/SMDR Receiver")
        if program_files.exists():
            pf_config = program_files / CONFIG_FILE
            if pf_config.exists():
                return pf_config
        
        # Check AppData
        appdata = Path.home() / "AppData/Local/SMDR Receiver"
        if appdata.exists():
            ad_config = appdata / CONFIG_FILE
            if ad_config.exists():
                return ad_config
        
        # Default to current directory
        return Path.cwd() / CONFIG_FILE
    
    def _load_config(self):
        """Load configuration from file."""
        if self.config_path.exists():
            try:
                with open(self.config_path, 'r') as f:
                    config = json.load(f)
                # Merge with defaults to ensure all keys exist
                merged = DEFAULT_CONFIG.copy()
                merged.update(config)
                return merged
            except Exception as e:
                print(f"Error loading config: {e}")
                return DEFAULT_CONFIG.copy()
        else:
            # Create default config
            self.save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG.copy()
    
    def save_config(self, config=None):
        """Save configuration to file."""
        if config is not None:
            self.config = config
        
        # Ensure directory exists
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def get(self, key, default=None):
        """Get a configuration value."""
        return self.config.get(key, default)
    
    def set(self, key, value):
        """Set a configuration value."""
        self.config[key] = value
    
    def get_port(self):
        """Get the configured port."""
        return self.config.get('port', 7004)
    
    def set_port(self, port):
        """Set the port."""
        self.config['port'] = port
        return self.save_config()
    
    def get_log_file(self):
        """Get the configured log file path."""
        log_file = self.config.get('log_file', 'smdr.log')
        return Path(log_file)
    
    def set_log_file(self, log_file):
        """Set the log file path."""
        self.config['log_file'] = str(log_file)
        return self.save_config()
    
    def get_auto_start(self):
        """Get auto-start setting."""
        return self.config.get('auto_start', True)
    
    def set_auto_start(self, auto_start):
        """Set auto-start setting."""
        self.config['auto_start'] = auto_start
        return self.save_config()


def create_default_config(install_dir):
    """Create default configuration file during installation."""
    config_path = Path(install_dir) / CONFIG_FILE
    config = SMDRConfig(config_path)
    config.save_config()
    return config_path
