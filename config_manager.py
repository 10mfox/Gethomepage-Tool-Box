import os
import yaml
import logging
import threading

log = logging.getLogger(__name__)

CONFIG_PATH = '/app/config'
CONFIG_FILE = os.path.join(CONFIG_PATH, 'config.yaml')

_config_from_file = None
_config_lock = threading.Lock()

def _create_default_config():
    """
    Creates a default config.yaml file.
    It will pre-populate with values from environment variables if they exist.
    """
    # Fetch current values from environment to pre-populate the new config
    default_config = {
        'TAUTULLI_URL': os.environ.get('TAUTULLI_URL', ''),
        'TAUTULLI_API_KEY': os.environ.get('TAUTULLI_API_KEY', ''),
        'JELLYSTAT_URL': os.environ.get('JELLYSTAT_URL', ''),
        'JELLYSTAT_API_KEY': os.environ.get('JELLYSTAT_API_KEY', ''),
        'JELLYSTAT_CONTAINER_NAME': os.environ.get('JELLYSTAT_CONTAINER_NAME', ''),
        'AUDIOBOOKSHELF_URL': os.environ.get('AUDIOBOOKSHELF_URL', ''),
        'AUDIOBOOKSHELF_API_KEY': os.environ.get('AUDIOBOOKSHELF_API_KEY', ''),
        'HOMEPAGE_PREVIEW_URL': os.environ.get('HOMEPAGE_PREVIEW_URL', ''),
        'TZ': os.environ.get('TZ', 'America/New_York'),
        'POLL_INTERVAL': os.environ.get('POLL_INTERVAL', 15),
        'REQUEST_TIMEOUT': os.environ.get('REQUEST_TIMEOUT', 30),
        'GUNICORN_TIMEOUT': os.environ.get('GUNICORN_TIMEOUT', 60),
        'ENABLE_CONFIG_EDITOR': os.environ.get('ENABLE_CONFIG_EDITOR', 'false'),
        'ENABLE_DEBUG': os.environ.get('ENABLE_DEBUG', 'false'),
        'REDIS_HOST': os.environ.get('REDIS_HOST', 'redis'),
    }

    # Create a commented YAML string
    commented_config = f"""
# --- Tool-Box Configuration --- #
# This file is for the configuration of the Gethomepage Tool-Box.
# Values set here will override environment variables.
# If a value is missing or empty in this file, the application will
# fall back to using environment variables (e.g., from your .env file).

# --- Required --- #
# Your timezone from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
TZ: '{default_config['TZ']}'

# --- Media Server Connections (add what you use) --- #

# Tautulli (for Plex)
TAUTULLI_URL: '{default_config['TAUTULLI_URL']}'
TAUTULLI_API_KEY: '{default_config['TAUTULLI_API_KEY']}'

# Jellystat (for Jellyfin/Emby)
JELLYSTAT_URL: '{default_config['JELLYSTAT_URL']}'
JELLYSTAT_API_KEY: '{default_config['JELLYSTAT_API_KEY']}'
# Optional: If running in the same Docker network, you can use the container name for direct communication.
# This is often more reliable than using the host IP.
JELLYSTAT_CONTAINER_NAME: '{default_config['JELLYSTAT_CONTAINER_NAME']}'

# Audiobookshelf
AUDIOBOOKSHELF_URL: '{default_config['AUDIOBOOKSHELF_URL']}'
AUDIOBOOKSHELF_API_KEY: '{default_config['AUDIOBOOKSHELF_API_KEY']}'

# --- Optional: Homepage Preview --- #
# URL for the preview pane in the CSS GUI Editor
HOMEPAGE_PREVIEW_URL: '{default_config['HOMEPAGE_PREVIEW_URL']}'

# --- Advanced settings --- #

# How often (in seconds) to check for library updates.
POLL_INTERVAL: {default_config['POLL_INTERVAL']}
# How long (in seconds) to wait for API responses.
REQUEST_TIMEOUT: {default_config['REQUEST_TIMEOUT']}
# Gunicorn worker timeout. Increase if you have very large libraries.
GUNICORN_TIMEOUT: {default_config['GUNICORN_TIMEOUT']}

# --- Optional: Enable advanced editor features --- #
# Set to true to enable the full config file editor
ENABLE_CONFIG_EDITOR: {str(default_config['ENABLE_CONFIG_EDITOR']).lower()}
# Set to true to enable the raw data viewer
ENABLE_DEBUG: {str(default_config['ENABLE_DEBUG']).lower()}

# --- Docker specific - usually no need to change --- #
# This is for the connection to the redis container.
REDIS_HOST: '{default_config['REDIS_HOST']}'
"""
    try:
        # Ensure config directory exists
        os.makedirs(CONFIG_PATH, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            f.write(commented_config)
        log.info(f"Created default config file at {CONFIG_FILE}")
    except Exception as e:
        log.error(f"Could not create default config file: {e}")

def _load_config_from_file():
    """Loads config from yaml file into a dictionary."""
    global _config_from_file
    if not os.path.exists(CONFIG_PATH):
        log.warning(f"Config directory not found at {CONFIG_PATH}. This is expected if you are not mounting a config volume.")
        _config_from_file = {}
        return

    if not os.path.exists(CONFIG_FILE):
        log.info(f"Config file not found at {CONFIG_FILE}. Creating a default one.")
        _create_default_config()
    
    try:
        with open(CONFIG_FILE, 'r') as f:
            _config_from_file = yaml.safe_load(f) or {}
            log.info("Successfully loaded config.yaml.")
    except Exception as e:
        log.error(f"Error loading config.yaml, will rely on environment variables. Error: {e}")
        _config_from_file = {}

def get_config(key, default=None, type_cast=None):
    """
    Gets a config value with a fallback mechanism.
    Priority:
    1. Value from config.yaml (if not empty/null)
    2. Value from environment variable
    3. Default value provided
    """
    global _config_from_file
    with _config_lock:
        if _config_from_file is None:
            _load_config_from_file()

    # 1. From config.yaml
    value = _config_from_file.get(key)
    
    # Check for empty strings, as user might leave them blank in yaml
    if value is not None and value != '':
        pass
    else:
        # 2. From environment variable
        value = os.environ.get(key)
        if value is None:
            # 3. From default value
            value = default

    if type_cast and value is not None:
        try:
            if type_cast == bool:
                return str(value).lower() in ['true', '1', 't', 'y', 'yes']
            return type_cast(value)
        except (ValueError, TypeError):
            log.warning(f"Could not cast config value for '{key}' to {type_cast}. Using default: {default}")
            return default
            
    return value