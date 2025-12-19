"""
Configuration management for SMDR Service.
Handles reading and writing service configuration.
"""
import json
from pathlib import Path
import sys

CONFIG_FILE = "smdr_config.json"

DEFAULT_CONFIG = {
    "port": 7004,
    "log_directory": ".",  # Directory where daily log files are stored
    "auto_start": True,
    "viewer_port": 7010,
    "service_host": "localhost",
}


class SMDRConfig:
    def __init__(self, config_path=None):
        # Base directory for relative paths; when frozen prefer the actual executable dir
        if getattr(sys, "frozen", False):
            self.base_dir = Path(sys.executable).parent
        else:
            self.base_dir = Path.cwd()
        if config_path is None:
            # Try to find config in common locations
            self.config_path = self._find_config_file()
        else:
            self.config_path = Path(config_path)
        
        self.config = self._load_config()
    
    def _find_config_file(self):
        """Find the config file in common locations."""
        # 1) Next to the executable / base dir when bundled
        bundled_path = self.base_dir / CONFIG_FILE
        if bundled_path.exists():
            return bundled_path

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

        def _write(path: Path) -> bool:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True

        try:
            return _write(self.config_path)
        except PermissionError:
            # Fallback to user-local AppData if the current path is not writable (e.g., Program Files)
            try:
                appdata_dir = Path.home() / "AppData/Local/SMDR Receiver"
                fallback_path = appdata_dir / CONFIG_FILE
                success = _write(fallback_path)
                if success:
                    self.config_path = fallback_path
                return success
            except Exception as e:
                print(f"Error saving config: {e}")
                return False
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
    
    def get_log_directory(self):
        """Get the configured log directory."""
        log_dir = self.config.get('log_directory', '.')
        p = Path(log_dir)
        return p if p.is_absolute() else (self.base_dir / p)
    
    def set_log_directory(self, log_dir):
        """Set the log directory."""
        self.config['log_directory'] = str(log_dir)
        return self.save_config()
    
    def get_current_log_file(self):
        """Get the current day's log file path (SMDRdataMMDDYY.log)."""
        from datetime import datetime
        log_dir = self.get_log_directory()
        date_str = datetime.now().strftime("%m%d%y")
        return log_dir / f"SMDRdata{date_str}.log"
    
    # --- Backwards-compat convenience methods for viewer ---
    def get_log_file(self):
        """Return the current log file path for the viewer.

        Kept for compatibility with older viewer code that expects
        a concrete log file rather than a directory. Uses the
        daily-rotated file generated by get_current_log_file().
        """
        return self.get_current_log_file()

    def set_log_file(self, log_file_path):
        """Set the log file location by updating the log directory.

        Older viewer code passes a full file path. We derive and
        persist the directory so daily rotation continues to work.
        Returns True on success, False on failure.
        """
        try:
            p = Path(log_file_path)
            # If a file name was provided, use its parent directory.
            # If a directory was provided, use it directly.
            new_dir = p if p.is_dir() else p.parent
            self.set_log_directory(new_dir)
            return True
        except Exception:
            return False

    
    def get_auto_start(self):
        """Get auto-start setting."""
        return self.config.get('auto_start', True)
    
    def set_auto_start(self, auto_start):
        """Set auto-start setting."""
        self.config['auto_start'] = auto_start
        return self.save_config()

    # --- Viewer network settings ---
    def get_viewer_port(self):
        """Port exposed by the service for remote viewers."""
        return int(self.config.get('viewer_port', DEFAULT_CONFIG['viewer_port']))

    def set_viewer_port(self, port):
        """Set viewer TCP port and persist it."""
        self.config['viewer_port'] = int(port)
        return self.save_config()

    def get_service_host(self):
        """Hostname/IP the viewer should connect to."""
        return self.config.get('service_host', DEFAULT_CONFIG['service_host'])

    def set_service_host(self, host):
        """Set viewer target host and persist it."""
        self.config['service_host'] = str(host)
        return self.save_config()




def create_default_config(install_dir):
    """Create default configuration file during installation."""
    config_path = Path(install_dir) / CONFIG_FILE
    config = SMDRConfig(config_path)
    config.save_config()
    return config_path
