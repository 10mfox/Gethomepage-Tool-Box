import os
import requests
from flask import Flask, render_template, request, jsonify
from flasgger import Swagger, swag_from
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import time

app = Flask(__name__, template_folder='.')
swagger = Swagger(app)

# --- Editor Blueprint ---
from editor import editor_bp
app.register_blueprint(editor_bp, url_prefix='/editor')

# Read configuration from environment variables
TAUTULLI_URL = os.environ.get('TAUTULLI_URL')
TAUTULLI_API_KEY = os.environ.get('TAUTULLI_API_KEY')
JELLYSTAT_URL = os.environ.get('JELLYSTAT_URL')
JELLYSTAT_API_KEY = os.environ.get('JELLYSTAT_API_KEY')
JELLYSTAT_CONTAINER_NAME = os.environ.get('JELLYSTAT_CONTAINER_NAME')
VERSION = os.environ.get('VERSION', 'dev')

log = logging.getLogger(__name__)

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
        display_title = item.get('Name', 'Unknown Title')
        if item.get('Type') == 'Episode':
            show_name = item.get('SeriesName', '')
            season_name = item.get('SeasonName', '')
            if show_name:
                display_title = f"{show_name} - {season_name} - {display_title}"
        elif item.get('Type') == 'Audio':
            artist_name = ', '.join(item.get('Artists', []))
            album_name = item.get('Album', '')
            if artist_name and album_name:
                display_title = f"{artist_name} - {album_name}"

        # Jellystat provides date as a string 'YYYY-MM-DDTHH:MM:SSZ'
        added_at_str = item.get('DateCreated')
        added_at_ts = 0
        if added_at_str:
            added_at_ts = int(datetime.fromisoformat(added_at_str.replace('Z', '+00:00')).timestamp())

        processed_items.append({
            'title': display_title,
            'year': item.get('ProductionYear', ''),
            'added_at': added_at_ts
        })
    return processed_items

# --- Tautulli Functions (Modified for clarity) ---
def _process_tautulli_items(items, history_map={}):
    """
    Helper function to process raw Tautulli items: formats titles and adds history IDs.
    This function performs no network requests.
    """
    processed_items = []
    for item in items:
        history_id = history_map.get(str(item.get('rating_key')))
        display_title = item.get('title', 'Unknown Title')
        if item.get('media_type') == 'episode':
            show_name = item.get('grandparent_title', '')
            season_num = item.get('parent_media_index', '??')
            episode_num = item.get('media_index', '??')
            if show_name:
                display_title = f"{show_name} - S{season_num}E{episode_num} - {display_title}"
        elif item.get('media_type') == 'track':
            artist_name = item.get('parent_title', '')
            album_name = item.get('title', '')
            if artist_name and album_name:
                display_title = f"{artist_name} - {album_name}"

        processed_items.append({
            'id': history_id,
            'title': display_title,
            'year': item.get('year', ''),
            'type': item.get('media_type', 'unknown'),
            'added_at': int(item.get('added_at'))
        })
    return processed_items

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
                        item['added_at'] = f"{seconds // 86400} days ago"
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
    return render_template('index.html')

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
    if JELLYSTAT_URL and JELLYSTAT_API_KEY:
        sources.append({"id": "jellystat", "name": "Jellystat"})
    return jsonify(sources)

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
        schema:
          type: array
          items:
            $ref: '#/definitions/Library'
      500:
        description: Tautulli is not configured on the server.
      502:
        description: Failed to communicate with Tautulli.
    definitions:
      Library:
        type: object
        properties:
          section_id: {type: string, example: '1'}
          section_name: {type: string, example: 'Movies'}
          counts: {type: object, example: {Movies: 1234}}
    """
    if not TAUTULLI_URL or not TAUTULLI_API_KEY:
        return jsonify({"error": "Tautulli is not configured on the server."}), 500

    try:
        params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
        response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params)
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
        schema:
          type: array
          items:
            $ref: '#/definitions/Library'
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
        libs_response = requests.get(f"{base_url}/api/getLibraries", headers=_get_jellystat_headers())
        libs_response.raise_for_status()
        libraries = libs_response.json()

        # 2. Fetch library stats to get the counts.
        stats_response = requests.get(f"{base_url}/stats/getLibraryOverview", headers=_get_jellystat_headers())
        stats_response.raise_for_status()
        stats = stats_response.json()
        
        # 3. Create a map of library ID to its count.
        count_map = {stat['Id']: stat.get('Library_Count') for stat in stats}

        # 4. Combine the data into the format the frontend expects, including detailed counts.
        formatted_libs = []
        for lib in libraries:
            counts = {}
            stat_details = next((s for s in stats if s['Id'] == lib.get('Id')), None)
            collection_type = stat_details.get('CollectionType') if stat_details else None

            if collection_type == 'tvshows':
                counts['Shows'] = stat_details.get('Library_Count')
                counts['Seasons'] = stat_details.get('Season_Count')
                counts['Episodes'] = stat_details.get('Episode_Count')
            elif collection_type == 'movies':
                counts['Movies'] = stat_details.get('Library_Count')
            elif collection_type == 'music':
                counts['Albums'] = stat_details.get('Library_Count') # Jellystat provides album count here

            formatted_libs.append({
                "section_id": lib.get("Id"),
                "section_name": lib.get("Name"),
                "counts": counts,
            })
        return jsonify(formatted_libs)
    except Exception as e:
        log.error(f"Failed to fetch Jellystat libraries: {e}")
        return jsonify({"error": "Failed to communicate with Jellystat."}), 502

# --- Cache for instant API response ---
_all_data_cache = {
    "data": None,
    "timestamp": 0
}
_cache_lock = threading.Lock()
POLL_INTERVAL_SECONDS = 15  # Check for changes every 15 seconds

def _fetch_all_tautulli_data_concurrently():
    """Internal function to fetch all Tautulli data concurrently."""
    # 1. Fetch libraries and history concurrently
    with ThreadPoolExecutor(max_workers=2) as executor:
        libs_future = executor.submit(requests.get, f"{TAUTULLI_URL}/api/v2", params={"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"})
        history_future = executor.submit(requests.get, f"{TAUTULLI_URL}/api/v2", params={"apikey": TAUTULLI_API_KEY, "cmd": "get_history", "length": 250})

        all_libraries = libs_future.result().json().get('response', {}).get('data', [])
        history_data = history_future.result().json().get('response', {}).get('data', {}).get('data', [])
        history_map = {str(item.get('rating_key')): item.get('history_id') for item in history_data if item.get('rating_key') and item.get('history_id')}

    data_by_library = {}
    for lib in all_libraries:
        section_name = lib.get('section_name')
        if section_name:
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
            data_by_library[section_name] = {'items': [], 'counts': counts}

    def fetch_for_library(library):
        """Fetch raw recently added items for a single library."""
        try:
            params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_recently_added", "section_id": library['section_id'], "count": 25}
            response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params)
            response.raise_for_status()
            items = response.json().get('response', {}).get('data', {}).get('recently_added', [])
            return library.get('section_name'), items
        except Exception as e:
            log.warning(f"Error fetching recently added for library {library.get('section_name')}: {e}")
            return library.get('section_name'), []

    # 2. Fetch all 'recently_added' data concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_for_library, all_libraries)

    # 3. Process all results using the single history map
    for library_name, raw_items in results:
        if library_name in data_by_library and raw_items:
            data_by_library[library_name]['items'] = _process_tautulli_items(raw_items, history_map)

    return data_by_library

def _get_tautulli_library_state():
    """
    Fetches a lightweight snapshot of library counts to detect changes.
    Returns a dictionary of {section_id: count} or None on error.
    """
    try:
        params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
        response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params, timeout=10)
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
        libs_future = executor.submit(requests.get, f"{base_url}/api/getLibraries", headers=headers)
        stats_future = executor.submit(requests.get, f"{base_url}/stats/getLibraryOverview", headers=headers)
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
                    counts['Albums'] = stat_details.get('Library_Count')
            data_by_library[section_name] = {'items': [], 'counts': counts}

    def fetch_for_library(library):
        """Fetch raw recently added items for a single library."""
        try:
            params = {'libraryid': library['Id']}
            response = requests.get(f"{base_url}/api/getRecentlyAdded", headers=headers, params=params)
            response.raise_for_status()
            return library.get('Name'), response.json()
        except Exception as e:
            log.warning(f"Error fetching Jellystat recently added for library {library.get('Name')}: {e}")
            return library.get('Name'), []

    # 2. Fetch all 'recently_added' data concurrently
    with ThreadPoolExecutor(max_workers=10) as executor:
        results = executor.map(fetch_for_library, all_libraries)

    # 3. Process all results
    for library_name, raw_items in results:
        if library_name in data_by_library and raw_items:
            data_by_library[library_name]['items'] = _process_jellystat_items(raw_items)

    return data_by_library

def _get_jellystat_library_state():
    """Fetches a lightweight snapshot of Jellystat library counts to detect changes."""
    try:
        base_url = _get_jellystat_base_url()
        response = requests.get(f"{base_url}/stats/getLibraryOverview", headers=_get_jellystat_headers(), timeout=10)
        response.raise_for_status()
        stats = response.json()
        # Create a state signature from library counts
        return {stat['Id']: stat.get('Library_Count', 0) for stat in stats}
    except Exception as e:
        log.warning(f"Jellystat state check: Could not fetch library state: {e}")
        return None

def update_cache_in_background(source_id, initial_state):
    """
    Periodically checks for changes in a data source and updates the cache
    only when a change is detected. This runs in a background thread.
    """
    last_state = initial_state
    
    # Map source_id to its corresponding functions
    source_map = {
        "tautulli": {
            "state_fetcher": _get_tautulli_library_state,
            "data_fetcher": _fetch_all_tautulli_data_concurrently,
        },
        "jellystat": {
            "state_fetcher": _get_jellystat_library_state,
            "data_fetcher": _fetch_all_jellystat_data_concurrently,
        }
    }
    
    if source_id not in source_map:
        log.error(f"Unknown source '{source_id}' for background cache update.")
        return

    state_fetcher = source_map[source_id]["state_fetcher"]
    data_fetcher = source_map[source_id]["data_fetcher"]

    while True:
        current_state = state_fetcher()
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
        time.sleep(POLL_INTERVAL_SECONDS)

@app.route('/api/data', methods=['GET'])
def get_data():
    """
    Get All Recently Added Data for a Source (from Cache)
    ---
    parameters:
      - name: source
        in: query
        type: string
        required: true
        description: The data source to query (e.g., 'tautulli' or 'jellystat').
      - name: source
        in: query
        type: string
        required: true
        description: The data source to query (e.g., 'tautulli' or 'jellystat').
      - name: dateFormat
        in: query
        type: string
        required: false
        description: "The desired date format. Options: 'short', 'relative'."
    responses:
      200:
        description: A dictionary of recently added items, grouped by library name.
      400:
        description: The 'source' query parameter is missing.
      503:
        description: The service is starting and the cache is not yet populated.
    """
    now = time.time()
    from copy import deepcopy
    date_format = request.args.get('dateFormat')
    source = request.args.get('source')

    if not source:
        return jsonify({"error": "A 'source' query parameter is required."}), 400
    
    with _cache_lock:
        # The background thread keeps this data fresh. We just serve it.
        data = _all_data_cache.get("data", {}).get(source)

    # Handle case where cache is not yet populated on startup
    if data is None:
        return jsonify({"error": "Service is starting, data is being cached. Please try again in a few moments."}), 503

    # If a date format is specified, work on a copy to avoid mutating the cache.
    if date_format:
        data_copy = deepcopy(data)
        _format_dates_in_response(data_copy, date_format, now)
        return jsonify(data_copy)

    return jsonify(data)