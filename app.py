import os
import mapping_manager
import requests
from flask import Flask, render_template, request, jsonify, Blueprint
from flasgger import Swagger, swag_from
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import time


app = Flask(__name__, template_folder='.')

# --- Swagger/Flasgger Configuration ---
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Media Manager & Homepage Tool-Box API",
        "title": "Gethomepage Tool-Box API Docs",
        "description": "API for fetching media server data and managing configurations.",
        "version": os.environ.get('VERSION', 'dev')
    },
    "definitions": {
        "Library": {
            "type": "object",
            "properties": {
                "section_id": {"type": "string", "example": "1"},
                "section_name": {"type": "string", "example": "Movies"},
                "counts": {"type": "object", "example": {"Movies": 1234}}
            }
        },
        "AddedItem": {
            "type": "object",
            "properties": {
                "title": {"type": "string", "example": "The Matrix"},
                "added_at": {"type": "integer", "example": 1672531200}
            }
        },
        "LibraryItems": {
            "type": "object",
            "properties": {
                "items": {
                    "type": "array",
                    "items": {"$ref": "#/definitions/AddedItem"}
                }
            }
        }
    }
}

# Dynamically build swagger tags based on configured sources
swagger_tags = [
    {"name": "Data", "description": "Endpoints for fetching processed data from media servers."},
    {"name": "Editor", "description": "Endpoints for the configuration file editor."},
    {"name": "Mappings", "description": "Endpoints for managing title-formatting mappings."}
]

if os.environ.get('ENABLE_DEBUG', 'false').lower() == 'true':
    swagger_tags.append({"name": "Debug", "description": "Endpoints for debugging and viewing raw data."})

swagger_template['tags'] = swagger_tags

swagger = Swagger(app, template=swagger_template)

# --- Debug Blueprint ---
debug_bp = Blueprint('debug', __name__)

# Read configuration from environment variables
TAUTULLI_URL = os.environ.get('TAUTULLI_URL')
TAUTULLI_API_KEY = os.environ.get('TAUTULLI_API_KEY')
JELLYSTAT_URL = os.environ.get('JELLYSTAT_URL')
JELLYSTAT_API_KEY = os.environ.get('JELLYSTAT_API_KEY')
JELLYSTAT_CONTAINER_NAME = os.environ.get('JELLYSTAT_CONTAINER_NAME')
VERSION = os.environ.get('VERSION', 'dev')
AUDIOBOOKSHELF_URL = os.environ.get('AUDIOBOOKSHELF_URL')
AUDIOBOOKSHELF_API_KEY = os.environ.get('AUDIOBOOKSHELF_API_KEY')
POLL_INTERVAL_SECONDS = int(os.environ.get('POLL_INTERVAL', 15))
REQUEST_TIMEOUT = int(os.environ.get('REQUEST_TIMEOUT', 30))
ENABLE_CONFIG_EDITOR = os.environ.get('ENABLE_CONFIG_EDITOR', 'false').lower() == 'true'
ENABLE_DEBUG = os.environ.get('ENABLE_DEBUG', 'false').lower() == 'true'

# --- Global Source Configuration Check ---
any_source_configured = (
    (TAUTULLI_URL and TAUTULLI_API_KEY) or
    (JELLYSTAT_URL and JELLYSTAT_API_KEY) or
    (AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_KEY)
)

# --- Dynamic Source Lists for Swagger ---
configured_main_sources_list = []
if TAUTULLI_URL and TAUTULLI_API_KEY:
    configured_main_sources_list.append('tautulli')
if JELLYSTAT_URL and JELLYSTAT_API_KEY:
    configured_main_sources_list.append('jellystat')
if AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_KEY:
    configured_main_sources_list.append('audiobookshelf')

configured_activity_sources_list = []
if TAUTULLI_URL and TAUTULLI_API_KEY:
    configured_activity_sources_list.append('tautulli')
if JELLYSTAT_URL and JELLYSTAT_API_KEY:
    configured_activity_sources_list.append('jellystat')

configured_debug_sources_list = configured_main_sources_list[:]
if TAUTULLI_URL and TAUTULLI_API_KEY and ENABLE_DEBUG: configured_debug_sources_list.append('tautulli-activity')
if JELLYSTAT_URL and JELLYSTAT_API_KEY and ENABLE_DEBUG:
    configured_debug_sources_list.extend(['jellystat-activity', 'jellystat-history'])

log = logging.getLogger(__name__)

# --- Helper Functions ---
def _ticks_to_hhmmss(ticks):
    """Converts 100-nanosecond ticks to a HH:MM:SS string."""
    if not ticks or ticks <= 0:
        return "00:00:00"
    seconds = ticks // 10000000
    m, s = divmod(seconds, 60)
    h, m = divmod(m, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

def _ms_to_hhmmss(milliseconds):
    """Converts milliseconds to a HH:MM:SS string."""
    try:
        ms = int(milliseconds)
        if ms <= 0: return "00:00:00"
        seconds = ms // 1000
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"
    except (ValueError, TypeError):
        return "00:00:00"

# --- Jellystat Functions ---
def _get_jellystat_headers():
    """Returns headers for Jellystat API requests."""
    return {"x-api-token": JELLYSTAT_API_KEY}

def _get_jellystat_base_url():
    """Returns the appropriate Jellystat URL for API calls."""
    # Prefer direct container-to-container communication if a container name is provided.
    if JELLYSTAT_CONTAINER_NAME:
        return f"http://{JELLYSTAT_CONTAINER_NAME}:8080" # Jellystat's default internal port is 8080
    return JELLYSTAT_URL

def _process_jellystat_items(items):
    """Helper function to process raw Jellystat items into a consistent format."""
    processed_items = []
    for item in items:
        display_title = mapping_manager.apply_mapping(item, 'jellystat', item.get('Type', ''))
        # Jellystat provides date as a string 'YYYY-MM-DDTHH:MM:SSZ'
        added_at_str = item.get('DateCreated')
        added_at_ts = 0
        if added_at_str:
            added_at_ts = int(datetime.fromisoformat(added_at_str.replace('Z', '+00:00')).timestamp())

        processed_items.append({
            'title': display_title,
            'added_at': added_at_ts
        })
    return processed_items

# --- Audiobookshelf Functions ---
def _get_audiobookshelf_headers():
    """Returns headers for Audiobookshelf API requests."""
    # Audiobookshelf uses a Bearer token (JWT)
    return {"Authorization": f"Bearer {AUDIOBOOKSHELF_API_KEY}"}

def _process_audiobookshelf_items(items):
    """Helper function to process raw Audiobookshelf items into a consistent format."""
    processed_items = []
    for item in items:
        media = item.get('media', {})
        metadata = media.get('metadata', {})
        
        # Flatten the nested metadata and extract the first genre for easier mapping
        flattened_data = {**item, **media, **metadata}
        genres = metadata.get('genres', [])
        flattened_data['genre'] = genres[0] if genres else ''
        
        # Pass all the flattened data to the mapping function
        display_title = mapping_manager.apply_mapping(flattened_data, 'audiobookshelf', 'book')
        processed_items.append({
            'title': display_title,
            'added_at': int(item.get('addedAt', 0)) // 1000 # Convert from milliseconds to seconds
        })
    return processed_items

# --- Tautulli Functions (Modified for clarity) ---

def _format_dates_in_response(data, date_format, now):
    """
    Helper to format 'added_at' timestamps in a data response object.
    This function mutates the data object.
    """
    if not date_format or not data:
        return

    for library_name, library_data in data.items():
        for item in library_data.get('items', []):
            if 'added_at' in item and isinstance(item['added_at'], int):
                timestamp = item['added_at']
                if date_format == 'short':
                    item['added_at'] = datetime.fromtimestamp(timestamp).strftime('%b %d')
                elif date_format == 'relative':
                    seconds = int(now - timestamp)
                    if seconds < 60:
                        item['added_at'] = f"{seconds} seconds ago"
                    elif seconds < 3600:
                        item['added_at'] = f"{seconds // 60} minutes ago"
                    elif seconds < 86400:
                        item['added_at'] = f"{seconds // 3600} hours ago"
                    elif seconds < 2592000: # 30 days
                        item['added_at'] = f"{seconds // 86400} day(s) ago"
                    elif seconds < 31536000: # 365 days
                        item['added_at'] = f"{seconds // 2592000} months ago"
                    else:
                        item['added_at'] = f"{seconds // 31536000} years ago"

def _get_date_format_from_request():
    """
    Reads and validates the 'dateFormat' query parameter from the request.
    """
    date_format = request.args.get('dateFormat')
    if date_format in ['short', 'relative']:
        return date_format
    return None

# --- Flask Routes ---
@app.route('/')
def index():
    if not any_source_configured:
        homepage_url = os.environ.get('HOMEPAGE_PREVIEW_URL', '')
        return render_template('css-gui.html', homepage_preview_url=homepage_url, any_source_configured=any_source_configured, enable_config_editor=ENABLE_CONFIG_EDITOR, enable_debug=ENABLE_DEBUG)
    return render_template('index.html', any_source_configured=any_source_configured, enable_config_editor=ENABLE_CONFIG_EDITOR, enable_debug=ENABLE_DEBUG)

@app.route('/api/version')
def get_version():
    """
    Get Application Version
    ---
    description: Returns the application version.
    responses:
      200:
        description: The current version of the application.
        schema:
          type: object
          properties:
            version:
              type: string
              example: 'dev'
    """
    return jsonify({"version": VERSION})

@app.route('/api/main-sources', methods=['GET'])
def get_main_sources():
    """
    Get Main Data Sources
    ---
    description: Returns a list of configured data sources intended for the main 'Recently Added' page. This excludes special-purpose sources like 'jellystat-activity'.
    responses:
      200:
        description: A list of configured data sources for the main page.
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: string
                example: 'tautulli'
              name:
                type: string
                example: 'Tautulli'
    """
    sources = []
    if TAUTULLI_URL and TAUTULLI_API_KEY:
        sources.append({"id": "tautulli", "name": "Tautulli"})
    if JELLYSTAT_URL and JELLYSTAT_API_KEY:
        sources.append({"id": "jellystat", "name": "Jellystat"})
    if AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_KEY:
        sources.append({"id": "audiobookshelf", "name": "Audiobookshelf"})
    return jsonify(sources)

@app.route('/api/sources', methods=['GET'])
def get_sources():
    """
    Get Configured Data Sources
    ---
    description: Returns a list of configured data sources (Tautulli, Jellystat, etc.).
    responses:
      200:
        description: A list of configured data sources.
        schema:
          type: array
          items:
            type: object
            properties:
              id:
                type: string
                example: 'tautulli'
              name:
                type: string
                example: 'Tautulli'
    """
    sources = []
    if TAUTULLI_URL and TAUTULLI_API_KEY:
        sources.append({"id": "tautulli", "name": "Tautulli"})
        if ENABLE_DEBUG:
            sources.append({"id": "tautulli-activity", "name": "Tautulli (Activity)"})
    if JELLYSTAT_URL and JELLYSTAT_API_KEY:
        sources.append({"id": "jellystat", "name": "Jellystat"})
        if ENABLE_DEBUG:
            sources.append({"id": "jellystat-activity", "name": "Jellystat (Activity)"})
            sources.append({"id": "jellystat-history", "name": "Jellystat (History)"})

    if AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_KEY:
        sources.append({"id": "audiobookshelf", "name": "Audiobookshelf"})
    return jsonify(sources)

@app.route('/api/host-info', methods=['GET'])
def get_host_info():
    """
    Get Host Information
    ---
    description: Returns information about the host, such as the port the app is running on.
    responses:
      200:
        description: Host information.
        schema:
          type: object
          properties:
            port:
              type: string
              example: '5000'
    """
    # This relies on the fact that Gunicorn binds to 0.0.0.0:port inside the container.
    port = os.environ.get('GUNICORN_CMD_ARGS', '--bind=0.0.0.0:5000').split(':')[-1]
    return jsonify({"port": port})

# --- Library Endpoints ---
@app.route('/api/tautulli/libraries', methods=['GET'])
def get_tautulli_libraries():
    """
    Get Tautulli Libraries
    ---
    description: Fetches the list of Tautulli libraries.
    responses:
      200:
        description: A list of Tautulli libraries with their details and counts.
      500:
        description: Tautulli is not configured on the server.
      502:
        description: Failed to communicate with Tautulli.
    """
    if not TAUTULLI_URL or not TAUTULLI_API_KEY:
        return jsonify({"error": "Tautulli is not configured on the server."}), 500

    try:
        params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
        response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        raw_libraries = response.json().get('response', {}).get('data', [])
        
        libraries = []
        for lib in raw_libraries:
            counts = {}
            section_type = lib.get('section_type')
            if section_type == 'show':
                counts['Shows'] = lib.get('count')
                counts['Seasons'] = lib.get('parent_count')
                counts['Episodes'] = lib.get('child_count')
            elif section_type == 'movie':
                counts['Movies'] = lib.get('count')
            elif section_type == 'artist':
                counts['Artists'] = lib.get('count')
                counts['Albums'] = lib.get('parent_count')

            libraries.append({
                "section_id": lib.get("section_id"),
                "section_name": lib.get("section_name"),
                "counts": counts,
                "section_type": section_type
            })
        return jsonify(libraries)
    except Exception as e:
        log.error(f"Failed to fetch Tautulli libraries: {e}")
        return jsonify({"error": "Failed to communicate with Tautulli."}), 502

# --- Jellystat Endpoints ---
@app.route('/api/jellystat/libraries', methods=['GET'])
def get_jellystat_libraries():
    """
    Get Jellystat Libraries
    ---
    description: Fetches the list of Jellystat libraries.
    responses:
      200:
        description: A list of Jellystat libraries with their details and counts.
      500:
        description: Jellystat is not configured on the server.
      502:
        description: Failed to communicate with Jellystat.
    """
    if not JELLYSTAT_URL or not JELLYSTAT_API_KEY:
        return jsonify({"error": "Jellystat is not configured on the server."}), 500

    # Add diagnostic logging to help debug authentication issues.
    # This will show the first 8 characters of the key being used.
    key_preview = JELLYSTAT_API_KEY[:8] if JELLYSTAT_API_KEY else "None"
    log.info(f"Attempting to fetch Jellystat libraries using API key starting with: {key_preview}...")

    try:
        base_url = _get_jellystat_base_url()
        
        # 1. Fetch all libraries to get their IDs and names.
        libs_response = requests.get(f"{base_url}/api/getLibraries", headers=_get_jellystat_headers(), timeout=REQUEST_TIMEOUT)
        libs_response.raise_for_status()
        libraries = libs_response.json()

        # 2. Fetch library stats to get the counts.
        stats_response = requests.get(f"{base_url}/stats/getLibraryOverview", headers=_get_jellystat_headers(), timeout=REQUEST_TIMEOUT)
        stats_response.raise_for_status()
        stats = stats_response.json()
        
        # 3. Create a map of library ID to its count.
        count_map = {stat['Id']: stat.get('Library_Count') for stat in stats}

        # 4. Combine the data into the format the frontend expects, including detailed counts.
        formatted_libs = []
        for lib in libraries:
            section_type = None
            counts = {}
            stat_details = next((s for s in stats if s['Id'] == lib.get('Id')), None)
            collection_type = stat_details.get('CollectionType') if stat_details else None

            if collection_type == 'tvshows':
                section_type = 'show'
                counts['Shows'] = stat_details.get('Library_Count')
                counts['Seasons'] = stat_details.get('Season_Count')
                counts['Episodes'] = stat_details.get('Episode_Count')
            elif collection_type == 'movies':
                section_type = 'movie'
                counts['Movies'] = stat_details.get('Library_Count')
            elif collection_type == 'music':
                section_type = 'artist'
                # Jellystat's Library_Count for music appears to be the track count.
                counts['Tracks'] = stat_details.get('Library_Count')

            formatted_libs.append({
                "section_id": lib.get("Id"),
                "section_name": lib.get("Name"),
                "counts": counts,
                "section_type": section_type
            })
        return jsonify(formatted_libs)
    except Exception as e:
        log.error(f"Failed to fetch Jellystat libraries: {e}")
        return jsonify({"error": "Failed to communicate with Jellystat."}), 502

def _fetch_audiobookshelf_libraries_data():
    """
    Internal helper to fetch and format Audiobookshelf library data.
    This function does not use any Flask context and can be called from anywhere.
    """
    if not AUDIOBOOKSHELF_URL or not AUDIOBOOKSHELF_API_KEY:
        raise Exception("Audiobookshelf is not configured on the server.")

    try:
        headers = _get_audiobookshelf_headers()
        # 1. Get the list of all libraries
        libs_response = requests.get(f"{AUDIOBOOKSHELF_URL}/api/libraries", headers=headers, timeout=REQUEST_TIMEOUT)
        libs_response.raise_for_status()
        raw_libraries = libs_response.json().get('libraries', [])
        
        def fetch_stats(library):
            """Fetches stats for a single library to get the item count."""
            try:
                stats_response = requests.get(f"{AUDIOBOOKSHELF_URL}/api/libraries/{library['id']}/stats", headers=headers, timeout=REQUEST_TIMEOUT)
                stats_response.raise_for_status()
                stats_json = stats_response.json()
                total_items = stats_json.get('totalItems', 0)
                total_authors = stats_json.get('totalAuthors', 0)
                counts = {'Books': total_items}
                if total_authors > 0:
                    counts['Authors'] = total_authors
                return {
                    "section_id": library.get("id"),
                    "section_name": library.get("name"),
                    "counts": counts,
                }
            except Exception as e:
                log.warning(f"Could not fetch stats for Audiobookshelf library {library.get('name')}: {e}")
                return None

        # 2. Fetch stats for all libraries concurrently
        with ThreadPoolExecutor(max_workers=10) as executor:
            results = executor.map(fetch_stats, raw_libraries)
        return [lib for lib in results if lib is not None]
    except Exception as e:
        log.error(f"Failed to fetch Audiobookshelf libraries: {e}")
        raise Exception("Failed to communicate with Audiobookshelf.") from e

@app.route('/api/audiobookshelf/libraries', methods=['GET'])
def get_audiobookshelf_libraries():
    """
    Get Audiobookshelf Libraries
    ---
    description: Fetches the list of Audiobookshelf libraries.
    responses:
      200:
        description: A list of Audiobookshelf libraries with their details and counts.
      500:
        description: Audiobookshelf is not configured on the server.
      502:
        description: Failed to communicate with Audiobookshelf.
    """
    if not AUDIOBOOKSHELF_URL or not AUDIOBOOKSHELF_API_KEY:
        return jsonify({"error": "Audiobookshelf is not configured on the server."}), 500
    try:
        libraries = _fetch_audiobookshelf_libraries_data()
        return jsonify(libraries)
    except Exception as e:
        # The internal function already logged the detailed error
        return jsonify({"error": str(e)}), 502

@app.route('/api/activity', methods=['GET'])
def get_activity():
    """
    Get User Activity
    ---
    tags:
      - Data
    description: Fetches current user activity and last played items from a specified source.
    parameters:
      - name: source
        in: query
        type: string
        required: true
        description: The data source to query.
        enum: {activity_sources}
      - name: dateFormat
        in: query
        type: string
        required: false
        description: "The desired date format for 'last played' items."
        enum: ['short', 'relative']
    responses:
      200:
        description: A list of active and last-played sessions.
      400:
        description: The 'source' query parameter is missing or invalid.
      500:
        description: The requested source is not configured on the server.
      502:
        description: Failed to communicate with the source.
    """
    source = request.args.get('source')
    if not source:
        return jsonify({"error": "A 'source' query parameter is required."}), 400
        
    now = time.time()
    date_format = _get_date_format_from_request()

    if source == 'jellystat':
        if not JELLYSTAT_URL or not JELLYSTAT_API_KEY:
            return jsonify({"error": "Jellystat is not configured on the server."}), 500
        try:
            base_url = _get_jellystat_base_url()
            headers = _get_jellystat_headers()
            with ThreadPoolExecutor(max_workers=2) as executor:
                sessions_future = executor.submit(requests.get, f"{base_url}/proxy/getSessions", headers=headers, timeout=REQUEST_TIMEOUT)
                history_future = executor.submit(requests.get, f"{base_url}/stats/getAllUserActivity", headers=headers, timeout=REQUEST_TIMEOUT)
                sessions_response, history_response = sessions_future.result(), history_future.result()
            sessions_response.raise_for_status()
            history_response.raise_for_status()
            sessions = sessions_response.json()
            history = history_response.json()

            playing_items, last_played_items, active_user_ids = [], [], set()

            for session in sessions:
                if not session.get('NowPlayingItem'): continue
                active_user_ids.add(session.get('UserId'))
                now_playing = session.get('NowPlayingItem', {})
                play_state = session.get('PlayState', {})
                transcoding_info = session.get('TranscodingInfo') or {} # Ensure transcoding_info is a dict
                full_session_data = {**session, **now_playing, **play_state, **transcoding_info}

                if play_state.get('IsPaused'):
                    full_session_data['status'] = "Paused"
                    full_session_data['status_dot'] = '🟡'
                else:
                    full_session_data['status'] = "Playing"
                    full_session_data['status_dot'] = '🟢'

                position_ticks, runtime_ticks = play_state.get('PositionTicks', 0), now_playing.get('RunTimeTicks', 0)
                full_session_data['PositionTicks_hhmmss'], full_session_data['RunTimeTicks_hhmmss'] = _ticks_to_hhmmss(position_ticks), _ticks_to_hhmmss(runtime_ticks)

                # Ensure CompletionPercentage is always available, calculating it if necessary.
                if 'CompletionPercentage' not in full_session_data:
                    if runtime_ticks and runtime_ticks > 0:
                        percentage = (position_ticks / runtime_ticks) * 100
                        full_session_data['CompletionPercentage'] = round(percentage, 2)
                    else:
                        full_session_data['CompletionPercentage'] = 0

                formatted_parts = mapping_manager.apply_activity_mapping(full_session_data, source='jellystat', sub_type='activity')
                playing_items.append({"title": formatted_parts.get('title', 'Unknown Title'), "user": formatted_parts.get('user', 'Unknown User')})

            # Process last played items for users who are not currently active
            for item in history:
                if item.get('UserId') in active_user_ids: continue
                
                # Prepare data for mapping
                item['status'] = 'Last Played'
                item['status_dot'] = '🔴'

                # Format the date if requested
                last_activity_str = item.get('LastActivityDate')
                if last_activity_str and date_format:
                    try:
                        # Ensure the date string is in the correct ISO format with Z
                        if '.' in last_activity_str: last_activity_str = last_activity_str.split('.')[0] + 'Z'
                        utc_dt = datetime.strptime(last_activity_str, '%Y-%m-%dT%H:%M:%SZ').replace(tzinfo=timezone.utc)
                        timestamp = utc_dt.timestamp()
                        temp_item_for_formatting = {'added_at': int(timestamp)}
                        _format_dates_in_response({'temp': {'items': [temp_item_for_formatting]}}, date_format, now)
                        item['LastActivityDate_formatted'] = temp_item_for_formatting['added_at']
                    except (ValueError, TypeError) as e:
                        log.warning(f"Could not parse or format Jellystat LastActivityDate '{last_activity_str}': {e}")
                
                formatted_parts = mapping_manager.apply_activity_mapping(item, source='jellystat', sub_type='last_played_activity')
                last_played_items.append({"title": formatted_parts.get('title', 'Unknown Title'), "user": formatted_parts.get('user', 'Unknown User')})

            return jsonify(playing_items + last_played_items)
        except Exception as e:
            log.error(f"Failed to fetch Jellystat activity: {e}")
            return jsonify({"error": "Failed to communicate with Jellystat."}), 502

    elif source == 'tautulli':
        def format_last_played_date(item, date_format, now):
            """
            A dedicated date formatter for single 'last played' items.
            This avoids the complexity of the bulk formatter.
            """
            if not date_format or 'stopped' not in item:
                return
            
            timestamp = item['stopped']
            if date_format == 'short':
                item['stopped_formatted'] = datetime.fromtimestamp(timestamp).strftime('%b %d')
            elif date_format == 'relative':
                seconds = int(now - timestamp)
                if seconds < 60: item['stopped_formatted'] = f"{seconds}s ago"
                elif seconds < 3600: item['stopped_formatted'] = f"{seconds // 60}m ago"
                elif seconds < 86400: item['stopped_formatted'] = f"{seconds // 3600}h ago"
                elif seconds < 2592000: item['stopped_formatted'] = f"{seconds // 86400}d ago"
                elif seconds < 31536000: item['stopped_formatted'] = f"{seconds // 2592000}mo ago"
                else: item['stopped_formatted'] = f"{seconds // 31536000}y ago"


        if not TAUTULLI_URL or not TAUTULLI_API_KEY:
            return jsonify({"error": "Tautulli is not configured on the server."}), 500
        try:
            with ThreadPoolExecutor(max_workers=3) as executor:
                activity_future = executor.submit(requests.get, f"{TAUTULLI_URL}/api/v2", params={"apikey": TAUTULLI_API_KEY, "cmd": "get_activity"}, timeout=REQUEST_TIMEOUT)                
                history_future = executor.submit(requests.get, f"{TAUTULLI_URL}/api/v2", params={"apikey": TAUTULLI_API_KEY, "cmd": "get_history", "length": 250}, timeout=REQUEST_TIMEOUT)
                activity_response, history_response = activity_future.result(), history_future.result()
            activity_response.raise_for_status()
            history_response.raise_for_status()
            sessions = activity_response.json().get('response', {}).get('data', {}).get('sessions', [])
            history = history_response.json().get('response', {}).get('data', {}).get('data', [])
            playing_items, last_played_items, active_user_ids = [], [], set()
            for session in sorted(sessions, key=lambda s: s.get('state', 'z')):
                active_user_ids.add(str(session.get('user_id')))
                state = session.get('state', 'unknown').lower()
                if state == 'playing':
                    session['status_dot'] = '🟢'
                elif state == 'paused':
                    session['status_dot'] = '🟡'
                else:
                    session['status_dot'] = '⚪' # for buffering, etc.
                session['status'] = state.capitalize()

                # Add formatted time fields similar to Jellystat
                duration_ms = session.get('duration', 0)
                view_offset_ms = session.get('view_offset', 0)
                session['duration_hhmmss'] = _ms_to_hhmmss(duration_ms)
                session['view_offset_hhmmss'] = _ms_to_hhmmss(view_offset_ms)

                formatted_parts = mapping_manager.apply_activity_mapping(session, 'tautulli', 'activity')
                playing_items.append({"title": formatted_parts.get('title', 'Unknown Title'), "user": formatted_parts.get('user', 'Unknown User')})

            # Process history to find the last played item for each user not currently active.
            latest_history_by_user = {}
            for item in history:
                user_id = str(item.get('user_id'))
                if user_id not in active_user_ids and user_id not in latest_history_by_user:
                    latest_history_by_user[user_id] = item

            for user_id, last_played in latest_history_by_user.items():
                last_played['status'], last_played['status_dot'] = 'Last Played', '🔴'
                stopped_timestamp = last_played.get('stopped', 0)
                if stopped_timestamp and date_format:
                    format_last_played_date(last_played, date_format, now)
                formatted_parts = mapping_manager.apply_activity_mapping(last_played, 'tautulli', 'last_played_activity')
                last_played_items.append({"title": formatted_parts.get('title', 'Unknown Title'), "user": formatted_parts.get('user', 'Unknown User'), "stopped": stopped_timestamp})

            sorted_last_played = sorted(last_played_items, key=lambda x: x.get('stopped', 0), reverse=True)
            for item in sorted_last_played: del item['stopped']
            return jsonify(playing_items + sorted_last_played)
        except Exception as e:
            log.error(f"Failed to fetch Tautulli activity: {e}")
            return jsonify({"error": "Failed to communicate with Tautulli."}), 502
    else:
        return jsonify({"error": f"Source '{source}' not supported for activity."}), 400

get_activity.__doc__ = get_activity.__doc__.format(activity_sources=configured_activity_sources_list)


# --- Debug Endpoints ---
@debug_bp.route('/raw-data')
def get_raw_data():
    """
    Get Raw Data from Source
    ---
    tags:
      - Debug
    parameters:
      - name: source
        in: query
        type: string
        required: true
        description: The data source to query.
        enum: {debug_sources}
      - name: library_id
        in: query
        type: string
        required: true
        description: The section_id of the library to query. Use the appropriate library endpoint (e.g., /api/tautulli/libraries) to find the ID.
    responses:
      200:
        description: An array of raw item objects from the source API.
      400:
        description: Missing required query parameters.
      502:
        description: Failed to communicate with the source.
    description: Fetches raw, unprocessed 'recently added' data for a specific library. This is intended for debugging and discovering available fields for the Mappings Editor.
    """
    source = request.args.get('source')

    try:
        if source == 'tautulli':
            if not TAUTULLI_URL or not TAUTULLI_API_KEY:
                return jsonify({"error": "Tautulli not configured"}), 500

            # Fetch both the raw 'recently_added' and the detailed 'metadata' to show the complete picture.
            library_id = request.args.get('library_id')
            # This matches the data enrichment process used by the main /api/data endpoint.
            ra_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_recently_added", "section_id": library_id, "count": 5} # Keep this count low for debugging
            ra_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=ra_params, timeout=REQUEST_TIMEOUT)
            ra_response.raise_for_status()
            recently_added = ra_response.json().get('response', {}).get('data', {}).get('recently_added', [])

            def fetch_metadata(item):
                meta_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_metadata", "rating_key": item['rating_key']}
                meta_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=meta_params, timeout=REQUEST_TIMEOUT)
                if meta_response.ok:
                    return {**item, **meta_response.json().get('response', {}).get('data', {})}
                return item

            with ThreadPoolExecutor(max_workers=5) as executor:
                enriched_items = list(executor.map(fetch_metadata, recently_added))
            return jsonify(enriched_items)

        elif source == 'jellystat':
            if not JELLYSTAT_URL or not JELLYSTAT_API_KEY: return jsonify({"error": "Jellystat not configured"}), 500
            library_id = request.args.get('library_id')
            base_url = _get_jellystat_base_url()
            params = {'libraryid': library_id, 'limit': 5}
            response = requests.get(f"{base_url}/api/getRecentlyAdded", headers=_get_jellystat_headers(), params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return jsonify(response.json())

        elif source == 'jellystat-activity':
            if not JELLYSTAT_URL or not JELLYSTAT_API_KEY: return jsonify({"error": "Jellystat not configured"}), 500
            base_url = _get_jellystat_base_url()
            headers = _get_jellystat_headers()
            response = requests.get(f"{base_url}/proxy/getSessions", headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return jsonify(response.json())

        elif source == 'tautulli-activity':
            if not TAUTULLI_URL or not TAUTULLI_API_KEY: return jsonify({"error": "Tautulli not configured"}), 500
            params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_activity"}
            response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return jsonify(response.json().get('response', {}).get('data', {}))

        elif source == 'jellystat-history':
            if not JELLYSTAT_URL or not JELLYSTAT_API_KEY: return jsonify({"error": "Jellystat not configured"}), 500
            base_url = _get_jellystat_base_url()
            headers = _get_jellystat_headers()
            response = requests.get(f"{base_url}/stats/getAllUserActivity", headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return jsonify(response.json())

        elif source == 'audiobookshelf':
            if not AUDIOBOOKSHELF_URL or not AUDIOBOOKSHELF_API_KEY: return jsonify({"error": "Audiobookshelf not configured"}), 500
            library_id = request.args.get('library_id')
            response = requests.get(f"{AUDIOBOOKSHELF_URL}/api/libraries/{library_id}/items?sort=addedAt-desc&limit=5", headers=_get_audiobookshelf_headers(), timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return jsonify(response.json().get('results', []))

    except Exception as e:
        return jsonify({"error": f"Failed to fetch raw data from {source}: {e}"}), 502
get_raw_data.__doc__ = get_raw_data.__doc__.format(debug_sources=configured_debug_sources_list)


# Import and register blueprints after all routes and configurations are defined
from editor import editor_bp

# Register blueprints after all routes have been defined
app.register_blueprint(debug_bp, url_prefix='/api/debug')
app.register_blueprint(editor_bp, url_prefix='/editor')

# --- Cache for instant API response ---
_all_data_cache = {
    "data": None,
    "timestamp": 0
}
_cache_lock = threading.Lock()

def _fetch_all_tautulli_data_concurrently():
    """Internal function to fetch all Tautulli data concurrently."""
    # 1. Fetch all libraries first to get their IDs and details.
    libs_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
    libs_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=libs_params, timeout=REQUEST_TIMEOUT)
    libs_response.raise_for_status()
    all_libraries = libs_response.json().get('response', {}).get('data', [])

    def fetch_for_library(library):
        """Fetch raw recently added items for a single library."""
        ra_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_recently_added", "section_id": library['section_id'], "count": 15}
        ra_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=ra_params, timeout=REQUEST_TIMEOUT)
        ra_response.raise_for_status()
        return library.get('section_name'), ra_response.json().get('response', {}).get('data', {}).get('recently_added', [])

    # 2. Prepare the data structure.
    data_by_library = {}
    
    for lib in all_libraries:
        counts = {}
        section_type = lib.get('section_type')
        if section_type == 'show':
            counts['Shows'] = lib.get('count')
            counts['Seasons'] = lib.get('parent_count')
            counts['Episodes'] = lib.get('child_count')
        elif section_type == 'movie':
            counts['Movies'] = lib.get('count')
        elif section_type == 'artist':
            counts['Artists'] = lib.get('count')
            counts['Albums'] = lib.get('parent_count')

        data_by_library[lib['section_name']] = {
            'items': [],
            'counts': counts
        }

    # 3. Fetch 'recently added' for each library concurrently.
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_for_library, all_libraries)

    for library_name, items in results:
        if library_name in data_by_library:
            data_by_library[library_name]['items'] = items

    return data_by_library

def _get_tautulli_library_state():
    """
    Fetches a lightweight snapshot of library counts to detect changes.
    Returns a dictionary of {section_id: count} or None on error.
    """
    try:
        params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
        response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params, timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        libraries = response.json().get('response', {}).get('data', [])
        # Create a state signature from library counts
        return {str(lib['section_id']): lib.get('count', 0) for lib in libraries}
    except Exception as e:
        log.warning(f"State check: Could not fetch library state: {e}")
        return None

def _fetch_all_jellystat_data_concurrently():
    """Internal function to fetch all Jellystat data concurrently."""
    base_url = _get_jellystat_base_url()
    headers = _get_jellystat_headers()

    # 1. Fetch libraries and stats concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        libs_future = executor.submit(requests.get, f"{base_url}/api/getLibraries", headers=headers, timeout=REQUEST_TIMEOUT)
        stats_future = executor.submit(requests.get, f"{base_url}/stats/getLibraryOverview", headers=headers, timeout=REQUEST_TIMEOUT)
        all_libraries = libs_future.result().json()
        stats = stats_future.result().json()

    data_by_library = {}
    for lib in all_libraries:
        section_name = lib.get('Name')
        if section_name:
            stat_details = next((s for s in stats if s['Id'] == lib.get('Id')), None)
            counts = {}
            if stat_details:
                collection_type = stat_details.get('CollectionType')
                if collection_type == 'tvshows':
                    counts['Shows'] = stat_details.get('Library_Count')
                    counts['Seasons'] = stat_details.get('Season_Count')
                    counts['Episodes'] = stat_details.get('Episode_Count')
                elif collection_type == 'movies':
                    counts['Movies'] = stat_details.get('Library_Count')
                elif collection_type == 'music':
                    counts['Tracks'] = stat_details.get('Library_Count')
            data_by_library[section_name] = {'items': [], 'counts': counts}

    def fetch_for_library(library):
        """Fetch raw recently added items for a single library."""
        try:
            params = {'libraryid': library['Id'], 'limit': 15} # Keep this count low for performance
            response = requests.get(f"{base_url}/api/getRecentlyAdded", headers=headers, params=params, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            return library.get('Name'), response.json()
        except Exception as e:
            log.warning(f"Error fetching Jellystat recently added for library {library.get('Name')}: {e}")
            return library.get('Name'), []

    # 2. Fetch all 'recently_added' data sequentially to avoid overwhelming Jellystat.
    # Jellystat appears to be sensitive to concurrent requests.
    results = []
    for library in all_libraries:
        results.append(fetch_for_library(library))

    # 3. Process all results
    for library_name, raw_items in results:
        if library_name in data_by_library and raw_items:
            # Store raw items; processing will happen on-demand.
            data_by_library[library_name]['items'] = raw_items

    return data_by_library

def _get_jellystat_library_state():
    """Fetches a lightweight snapshot of Jellystat library counts to detect changes."""
    try:
        base_url = _get_jellystat_base_url()
        response = requests.get(f"{base_url}/stats/getLibraryOverview", headers=_get_jellystat_headers(), timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        stats = response.json()
        # Create a state signature from library counts
        return {stat['Id']: stat.get('Library_Count', 0) for stat in stats}
    except Exception as e:
        log.warning(f"Jellystat state check: Could not fetch library state: {e}")
        return None

def _fetch_all_audiobookshelf_data_concurrently():
    """Internal function to fetch all Audiobookshelf data concurrently."""
    headers = _get_audiobookshelf_headers()

    # 1. Get the list of all libraries
    libs_response = requests.get(f"{AUDIOBOOKSHELF_URL}/api/libraries", headers=headers, timeout=REQUEST_TIMEOUT)
    libs_response.raise_for_status()
    all_libraries = libs_response.json().get('libraries', [])

    data_by_library = {}

    def fetch_data_for_library(library):
        """Fetches both stats and recently added items for a single library."""
        library_name = library.get('name')
        if not library_name:
            return None, None, None

        try:
            # Fetch stats and items concurrently for each library
            with ThreadPoolExecutor(max_workers=2) as executor:
                stats_future = executor.submit(requests.get, f"{AUDIOBOOKSHELF_URL}/api/libraries/{library['id']}/stats", headers=headers, timeout=REQUEST_TIMEOUT)
                items_future = executor.submit(requests.get, f"{AUDIOBOOKSHELF_URL}/api/libraries/{library['id']}/items?sort=addedAt-desc&limit=15", headers=headers, timeout=REQUEST_TIMEOUT)

                stats_json = stats_future.result().json()
                items_json = items_future.result().json()

            total_items = stats_json.get('totalItems', 0)
            total_authors = stats_json.get('totalAuthors', 0)
            counts = {'Books': total_items, 'Authors': total_authors}

            items = items_json.get('results', [])
            return library_name, items, counts
        except Exception as e:
            log.warning(f"Error fetching data for Audiobookshelf library {library_name}: {e}")
            return library_name, [], {}

    # 2. Fetch all data for all libraries concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        for library_name, raw_items, counts in executor.map(fetch_data_for_library, all_libraries):
            if library_name:
                data_by_library[library_name] = {
                    # Store raw items; processing will happen on-demand.
                    'items': raw_items,
                    'counts': counts
                }

    return data_by_library

def _get_audiobookshelf_library_state():
    """Fetches a lightweight snapshot of Audiobookshelf library counts to detect changes."""
    # For Audiobookshelf, we can just re-use the library fetching logic as it's lightweight.
    try:
        libraries = _fetch_audiobookshelf_libraries_data()
        return {lib['section_id']: lib['counts'].get('Books', 0) for lib in libraries}
    except Exception as e:
        log.warning(f"Audiobookshelf state check: Could not fetch library state: {e}")
        return None

# Map source_id to its corresponding functions
source_map = {
    "tautulli": {
        "state_fetcher": _get_tautulli_library_state,
        "data_fetcher": _fetch_all_tautulli_data_concurrently,
    },
    "jellystat": {
        "state_fetcher": _get_jellystat_library_state,
        "data_fetcher": _fetch_all_jellystat_data_concurrently,
    },
    "audiobookshelf": {
        "state_fetcher": _get_audiobookshelf_library_state,
        "data_fetcher": _fetch_all_audiobookshelf_data_concurrently,
    }
}

def update_cache_in_background(source_id, initial_state):
    """
    Periodically checks for changes in a data source and updates the cache
    only when a change is detected. This runs in a background thread.
    """
    last_state = initial_state
    
    if source_id not in source_map:
        log.error(f"Unknown source '{source_id}' for background cache update.")
        return

    state_fetcher = source_map[source_id]["state_fetcher"]
    data_fetcher = source_map[source_id]["data_fetcher"]

    # This loop runs for a specific source_id (e.g., 'tautulli')
    while True:
        time.sleep(POLL_INTERVAL_SECONDS)
        current_state = state_fetcher()
        # A refresh is triggered if the source state has changed.
        if current_state and current_state != last_state:
            log.info(f"Change detected for {source_id}. Refreshing data cache...")
            try:
                data = data_fetcher()
                with _cache_lock:
                    _all_data_cache["data"][source_id] = data
                    _all_data_cache["timestamp"][source_id] = time.time()
                last_state = current_state
                log.info(f"Cache refresh for {source_id} successful.")
            except Exception as e:
                log.error(f"Error refreshing {source_id} cache: {e}")

@app.route('/api/counts', methods=['GET'])
def get_counts():
    """
    Get Library Counts
    ---
    tags:
      - Data
    parameters:
      - name: source
        in: query
        type: string
        required: true
        description: The data source to query.
        enum: {main_sources}
    responses:
      200:
        description: A dictionary of libraries and their media counts.
        schema:
          type: object
          additionalProperties:
            type: object
            properties:
              counts: {{type: 'object', example: {{'Movies': 1234}}}}
      400:
        description: The 'source' query parameter is missing.
      503:
        description: The service is starting and the cache is not yet populated.
    """
    source = request.args.get('source')
    if not source:
        return jsonify({"error": "A 'source' query parameter is required."}), 400

    with _cache_lock:
        data = _all_data_cache.get("data", {}).get(source)

    if data is None:
        return jsonify({"error": "Service is starting, data is being cached. Please try again."}), 503

    counts_data = {
        library_name: {"counts": library_data.get("counts", {})}
        for library_name, library_data in data.items()
    }
    return jsonify(counts_data)

get_counts.__doc__ = get_counts.__doc__.format(main_sources=configured_main_sources_list)

@app.route('/api/added', methods=['GET'])
def get_added():
    """
    Get Recently Added Items
    ---
    tags:
      - Data
    parameters:
      - name: source
        in: query
        type: string
        required: true
        description: The data source to query.
        enum: {main_sources}
      - name: dateFormat
        in: query
        type: string
        required: false
        description: "The desired date format."
        enum: ['short', 'relative']
      - name: count
        in: query
        type: integer
        required: false
        description: "The maximum number of items to return per library."
        default: 15
    responses:
      200:
        description: A dictionary of recently added items with formatted titles, grouped by library name.
        schema:
          type: object
          additionalProperties:
            $ref: '#/definitions/LibraryItems'
      400:
        description: The 'source' query parameter is missing.
      503:
        description: The service is starting and the cache is not yet populated.
    """
    now = time.time()
    date_format = request.args.get('dateFormat')
    source = request.args.get('source')
    count = request.args.get('count', default=15, type=int)

    if not source:
        return jsonify({"error": "A 'source' query parameter is required."}), 400

    with _cache_lock:
        data = _all_data_cache.get("data", {}).get(source)

    if data is None:
        return jsonify({"error": "Service is starting, data is being cached. Please try again."}), 503

    from copy import deepcopy
    # Deepcopy to avoid mutating the cache
    data_copy = deepcopy(data)

    # This is where we apply the mappings on-the-fly
    processed_data = {}
    for library_name, library_data in data_copy.items():
        processed_items = []
        raw_items = library_data.get("items", [])[:count] # Apply the count limit here

        if source == 'tautulli':
            for item in raw_items:
                formatted_title = mapping_manager.apply_mapping(item, 'tautulli', item.get('media_type', ''))
                processed_items.append({'title': formatted_title, 'added_at': int(item.get('added_at', 0))})
        elif source == 'jellystat':
            processed_items = _process_jellystat_items(raw_items)
        elif source == 'audiobookshelf':
            processed_items = _process_audiobookshelf_items(raw_items)
        else:
            # Fallback for unknown sources
            processed_items = raw_items

        processed_data[library_name] = {"items": processed_items}

    if date_format:
        _format_dates_in_response(processed_data, date_format, now)

    return jsonify(processed_data)

def prime_and_start_cache_threads(is_refresh=False):
    """
    Initializes the data cache for all configured sources and starts
    the background threads to keep them updated.
    """
    if not is_refresh:
        log.info("Application starting: Priming data caches...")
    else:
        # This is a manual refresh, likely from a mapping change.
        log.info("Refreshing all data caches...")

    with app.app_context():
        configured_sources = get_sources().get_json()

    if not configured_sources:
        log.warning("No data sources are configured. Caching will be skipped.")
        return

    new_data_cache = {}
    new_timestamp_cache = {}

    with ThreadPoolExecutor(max_workers=len(configured_sources) or 1) as executor:
        # Filter sources to only include those defined in the source_map for caching
        cacheable_sources = [s for s in configured_sources if s['id'] in source_map]

        def prime_and_start_thread(source):
            source_id = source['id']
            try:
                data_fetcher = source_map[source_id]["data_fetcher"]
                initial_data = data_fetcher()
                new_data_cache[source_id] = initial_data
                new_timestamp_cache[source_id] = time.time()
                log.info(f"Initial cache for {source_id} populated successfully.")

                # Only start background threads on the initial prime, not on a manual refresh
                if is_refresh:
                    return
                
                state_fetcher = source_map[source_id]["state_fetcher"]
                initial_state = state_fetcher()
                cache_thread = threading.Thread(target=update_cache_in_background, args=(source_id, initial_state), daemon=True)
                cache_thread.start()
                log.info(f"Background cache-refresh thread for {source_id} started.")
            except Exception as e:
                log.error(f"Could not perform initial cache for {source_id}. This source will be unavailable until the next restart. Error: {e}")

        # Run the priming process for each source
        executor.map(prime_and_start_thread, cacheable_sources)

    with _cache_lock:
        _all_data_cache["data"] = new_data_cache
        _all_data_cache["timestamp"] = new_timestamp_cache
    log.info("All data caches have been populated.")

# Initialize cache structure and start background threads
_all_data_cache["data"] = {}
_all_data_cache["timestamp"] = {}
prime_and_start_cache_threads()

get_added.__doc__ = get_added.__doc__.format(main_sources=configured_main_sources_list)