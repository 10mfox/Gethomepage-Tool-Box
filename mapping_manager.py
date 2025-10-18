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
            'recently_added': {
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
            'user_activity': {
                'activity_episode': {
                    'templates': {
                        'title': '{grandparent_title} - S{parent_media_index}E{media_index} {view_offset_hhmmss} / {duration_hhmmss}',
                        'user': '{user} ({status}) {status_dot}'
                    },
                    'fields': ['user', 'friendly_name', 'title', 'grandparent_title', 'parent_title', 'state', 'platform', 'device', 'player', 'progress_percent', 'status', 'view_offset_hhmmss', 'duration_hhmmss', 'status_dot']
                },
                'activity_movie': {
                    'templates': {
                        'title': '{title} {view_offset_hhmmss} / {duration_hhmmss}',
                        'user': '{user} ({status}) {status_dot}'
                    },
                    'fields': ['user', 'friendly_name', 'title', 'year', 'state', 'platform', 'device', 'player', 'progress_percent', 'status', 'view_offset_hhmmss', 'duration_hhmmss', 'status_dot']
                },
                'last_played_episode': {
                    'templates': {
                        'title': '{grandparent_title} - S{parent_media_index}E{media_index} - {title}',
                        'user': '{user} ({status}) {status_dot}'
                    },
                    'fields': ['user', 'friendly_name', 'title', 'grandparent_title', 'parent_title', 'stopped', 'stopped_formatted', 'platform', 'device', 'player', 'status', 'status_dot']
                },
                'last_played_movie': {
                    'templates': {
                        'title': '{title} ({year})',
                        'user': '{user} ({status}) {status_dot}'
                    },
                    'fields': ['user', 'friendly_name', 'title', 'year', 'stopped', 'stopped_formatted', 'platform', 'device', 'player', 'status', 'status_dot']
                },
                'last_played_track': {
                    'templates': {
                        'title': '{grandparent_title} - {title}',
                        'user': '{user} ({status}) {status_dot}'
                    },
                    'fields': ['user', 'friendly_name', 'title', 'grandparent_title', 'parent_title', 'stopped', 'stopped_formatted', 'platform', 'device', 'player', 'status', 'status_dot']
                }
            }
        },
        'jellystat': {
            'recently_added': {
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
            'user_activity': {
                'activity_Episode': {
                    'templates': {
                        'title': '{SeriesName} - S{ParentIndexNumber}E{IndexNumber} {PositionTicks_hhmmss}/{RunTimeTicks_hhmmss}',
                        'user': '{UserName} ({status}) {status_dot}'
                    },
                    'fields': ['UserName', 'Client', 'DeviceName', 'Name', 'SeriesName', 'IsPaused', 'PlayMethod', 'status', 'CompletionPercentage', 'IndexNumber', 'ParentIndexNumber', 'PositionTicks_hhmmss', 'RunTimeTicks_hhmmss', 'LastWatched', 'CommunityRating', 'OfficialRating', 'ProductionYear', 'Container', 'VideoCodec', 'AudioCodec', 'LastClient', 'status_dot']
                },
                'activity_Movie': {
                    'templates': {
                        'title': '{Name} {PositionTicks_hhmmss}/{RunTimeTicks_hhmmss}',
                        'user': '{UserName} ({status}) {status_dot}'
                    },
                    'fields': ['UserName', 'Client', 'DeviceName', 'Name', 'IsPaused', 'PlayMethod', 'status', 'PositionTicks_hhmmss', 'RunTimeTicks_hhmmss', 'CommunityRating', 'OfficialRating', 'ProductionYear', 'Container', 'VideoCodec', 'AudioCodec', 'CompletionPercentage', 'LastClient', 'status_dot']
                },
                'last_played_Episode': {
                    'templates': {
                        'title': '{LastWatched}',
                        'user': '{UserName} ({status}) {status_dot}'
                    },
                    'fields': ['UserName', 'LastWatched', 'LastActivityDate', 'LastActivityDate_formatted', 'LastClient', 'TotalPlays', 'TotalWatchTime', 'status', 'status_dot', 'LastActivityDate_formatted']
                },
                'last_played_Movie': {
                    'templates': {
                        'title': '{LastWatched}',
                        'user': '{UserName} ({status}) {status_dot}'
                    },
                    'fields': ['UserName', 'LastWatched', 'LastActivityDate', 'LastActivityDate_formatted', 'LastClient', 'TotalPlays', 'TotalWatchTime', 'status', 'status_dot', 'LastActivityDate_formatted']
                }
            }
        },
        'audiobookshelf': {
            'recently_added': {
                'book': {
                    'template': '{authorName} - {title}',
                    'fields': ['title', 'subtitle', 'authorName', 'narratorName', 'seriesName', 'genre', 'publishedYear', 'publisher', 'description', 'duration', 'numChapters', 'numTracks', 'mediaType', 'path']
                }
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
        return False, f"Could not save mappings: {e}"

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
    type_mapping = source_mapping.get('recently_added', {}).get(media_type)

    if not type_mapping:
        # If no specific mapping exists, try to find a default 'title' or 'name' field.
        return item_data.get('title', item_data.get('name', 'Unknown Title'))

    template = type_mapping.get('template', '{title}')

    class SafeDict(dict):
        def __missing__(self, key):
            return ''

    return template.format_map(SafeDict(item_data))

def apply_activity_mapping(item_data, source='jellystat', sub_type='activity'):
    """
    Applies the mapping specifically for the 'activity' type, which has multiple templates.
    Returns a dictionary of formatted strings.
    """
    # Map the old sub_type to the new structure keys
    activity_type = 'last_played' if 'last_played' in sub_type else 'activity'

    # Determine the specific sub-type based on the media type
    media_type = item_data.get('media_type') or item_data.get('Type')
    
    # For Jellystat history, the 'Type' field is missing. We can infer the type.
    if source == 'jellystat' and not media_type:
        media_type = 'Episode' if item_data.get('SeriesName') else 'Movie'
    media_type = media_type or '' # Ensure media_type is a string
    
    # Normalize media type for lookup
    if 'movie' in media_type.lower(): media_type_key = 'movie' if source == 'tautulli' else 'Movie'
    elif 'episode' in media_type.lower(): media_type_key = 'episode' if source == 'tautulli' else 'Episode'
    elif 'track' in media_type.lower() and source == 'tautulli': media_type_key = 'track'
    else: media_type_key = media_type # Fallback for other types

    mappings = get_mappings()
    type_mapping = mappings.get(source, {}).get(activity_type, {}).get(media_type_key)

    if not type_mapping or 'templates' not in type_mapping:
        # Fallback for when mappings are not found. Check for both Jellystat and Tautulli style fields.
        # For last played, Jellystat has a nice 'LastWatched' field.
        title = item_data.get('LastWatched', item_data.get('Name', item_data.get('title', '')))
        user = item_data.get('UserName', item_data.get('user', ''))
        return {'title': title, 'user': user}

    class SafeDict(dict):
        """A dict that can handle nested key access like 'media[metadata][title]'."""
        def __missing__(self, key):
            # Handle nested keys like 'user[username]'
            if '[' in key and key.endswith(']'):
                parts = key.replace(']', '').split('[')
                val = self
                for part in parts:
                    if isinstance(val, dict):
                        val = val.get(part)
                        if val is None: return ''
                    else:
                        return ''
                return val if not isinstance(val, dict) else ''
            return ''

    output = {}
    templates = type_mapping.get('templates', {})
    for key, template in templates.items():
        # Format the string and then clean up any leading/trailing hyphens or whitespace
        # that might result from empty fields (e.g., "{grandparent_title} - {title}" for a movie).
        output[key] = template.format_map(SafeDict(item_data)).strip(' -')
    return output