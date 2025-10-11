import os
import yaml
import logging
import threading

log = logging.getLogger(__name__)

CONFIG_PATH = '/app/config'
MAPPINGS_FILE = os.path.join(CONFIG_PATH, 'mappings.yaml')
UPDATE_SIGNAL_FILE = os.path.join(CONFIG_PATH, '.mappings.updated')

# --- Thread-safe, in-memory cache for mappings ---
_mappings_cache = None
_mappings_lock = threading.Lock()

# --- End Cache ---

def get_default_mappings():
    """
    Returns the default mapping structure with example templates and available fields.
    This serves as the blueprint for the mappings editor.
    """
    return {
        'tautulli': {
            'movie': {
                'template': '{title}',
                'fields': ['title', 'year', 'originally_available_at', 'media_type', 'grandparent_title', 'parent_title']
            },
            'episode': {
                'template': '{grandparent_title} - S{parent_media_index}E{media_index} - {title}',
                'fields': ['title', 'year', 'originally_available_at', 'media_type', 'grandparent_title', 'parent_title', 'parent_media_index', 'media_index']
            },
            'album': {
                'template': '{parent_title} - {title}',
                'fields': ['title', 'year', 'originally_available_at', 'media_type', 'parent_title']
            }
        },
        'jellystat': {
            'Movie': {
                'template': '{Name}',
                'fields': ['Name']
            },
            'Episode': {
                'template': '{SeriesName} - S{SeasonNumber}E{EpisodeNumber} - {Name}',
                'fields': ['Name', 'SeriesName', 'SeasonNumber', 'EpisodeNumber']
            },
            'Audio': {
                'template': '{Name}',
                'fields': ['Name']
            }
        },
        'audiobookshelf': {
            'book': {
                'template': '{authorName} - {title}',
                'fields': ['title', 'subtitle', 'authorName', 'narratorName', 'seriesName', 'genre', 'publishedYear', 'publisher', 'description', 'duration', 'numChapters', 'numTracks', 'mediaType', 'path']
            }
        }
    }

def get_mappings():
    """
    Loads mappings from mappings.yaml. If the file doesn't exist,
    it returns the default mappings.
    """
    global _mappings_cache
    with _mappings_lock:
        # If a signal file exists, it means another process updated the mappings.
        # We must invalidate our local in-memory cache to force a reload from disk.
        if os.path.exists(UPDATE_SIGNAL_FILE):
            _mappings_cache = None
            try:
                os.remove(UPDATE_SIGNAL_FILE)
                log.info("Mapping update signal detected. Invalidating mapping cache to force reload.")
            except OSError as e:
                log.warning(f"Could not remove mapping update signal file: {e}")

        # If the cache is populated, return it. Otherwise, load from file.
        if _mappings_cache is not None:
            return _mappings_cache

        if os.path.exists(MAPPINGS_FILE):
            try:
                with open(MAPPINGS_FILE, 'r') as f:
                    log.info("Loading mappings from mappings.yaml into cache.")
                    _mappings_cache = yaml.safe_load(f)
            except Exception as e:
                log.error(f"Error loading mappings.yaml, falling back to defaults: {e}")
                _mappings_cache = get_default_mappings()
        else:
            _mappings_cache = get_default_mappings()
        return _mappings_cache

def save_mappings(data):
    """
    Saves the provided mapping data to mappings.yaml.
    """
    global _mappings_cache
    try:
        with open(MAPPINGS_FILE, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
        # Create a signal file to notify other processes to reload the mappings.
        with open(UPDATE_SIGNAL_FILE, 'w') as f:
            pass # Just create an empty file

        log.info("Mappings saved and update signal created.")
        return True, "Mappings saved successfully."
    except Exception as e:
        log.error(f"Error saving mappings.yaml: {e}")
        return False, f"Could not save mappings: {e}", None

def apply_mapping(item_data, source, media_type):
    """
    Applies the configured mapping template to format a display title.
    
    - item_data: The dictionary of data for the item.
    - source: The source id (e.g., 'tautulli').
    - media_type: The media type (e.g., 'movie', 'show').
    """
    mappings = get_mappings()

    # Find the correct mapping, falling back gracefully
    source_mapping = mappings.get(source, {})
    type_mapping = source_mapping.get(media_type)

    # If no specific mapping exists, try to find a default 'title' or 'name' field.
    if not type_mapping:
        return item_data.get('title', item_data.get('name', 'Unknown Title'))

    template = type_mapping.get('template', '{title}')

    # Use a dictionary that returns an empty string for missing keys,
    # ensuring that any field in the template can be resolved.
    class SafeDict(dict):
        def __missing__(self, key):
            return ''

    formatted_title = template.format_map(SafeDict(item_data))
    return formatted_title