import os
import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
import logging
import time

app = Flask(__name__, template_folder='.')

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
            added_at_ts = int(datetime.strptime(added_at_str.split('.')[0], '%Y-%m-%dT%H:%M:%S').timestamp())

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
    """Returns the application version."""
    return jsonify({"version": VERSION})

@app.route('/api/sources', methods=['GET'])
def get_sources():
    """Returns a list of configured data sources (Tautulli, Jellystat, etc.)."""
    sources = []
    if TAUTULLI_URL and TAUTULLI_API_KEY:
        sources.append({"id": "tautulli", "name": "Tautulli"})
    if JELLYSTAT_URL and JELLYSTAT_API_KEY:
        sources.append({"id": "jellystat", "name": "Jellystat"})
    return jsonify(sources)

# --- Tautulli Endpoints ---
@app.route('/api/tautulli/libraries', methods=['GET'])
def get_tautulli_libraries():
    """Fetches the list of Tautulli libraries."""
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

@app.route('/api/tautulli/data', methods=['GET'])
def get_tautulli_data():
    """Fetches Tautulli recently added data for one or more library sections."""
    section_ids_str = request.args.get('section_id')
    if not TAUTULLI_URL or not TAUTULLI_API_KEY:
        return jsonify({
            'data': None, 'error': 'Tautulli URL or API Key is not configured on the server.'
        }), 500
    
    try:
        # Fetch all libraries to map section_id to section_name
        libs_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
        libs_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=libs_params)
        libs_response.raise_for_status()
        libraries = libs_response.json().get('response', {}).get('data', [])
        
        library_info = {
            str(lib['section_id']): {
                'name': lib['section_name'],
                'counts': (
                    {'Shows': lib.get('count'), 'Seasons': lib.get('parent_count'), 'Episodes': lib.get('child_count')}
                    if lib.get('section_type') == 'show'
                    else {'Movies': lib.get('count')}
                    if lib.get('section_type') == 'movie'
                    else {'Artists': lib.get('count'), 'Albums': lib.get('parent_count')}
                    if lib.get('section_type') == 'artist'
                    else {}
                )
            }
            for lib in libraries
        }
    except Exception as e:
        log.error(f"Failed to fetch library list for /api/data: {e}")
        return jsonify({"error": "Failed to fetch library list from Tautulli."}), 502

    # If no section_id is provided, default to all libraries.
    if not section_ids_str:
        section_ids = list(library_info.keys())
    else:
        section_ids = section_ids_str.split(',')

    # --- Efficient Data Fetching ---
    # 1. Fetch history ONCE for all selected libraries.
    try:
        history_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_history", "length": 250}
        history_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=history_params)
        history_response.raise_for_status()
        history_data = history_response.json().get('response', {}).get('data', {}).get('data', [])
        history_map = {str(item.get('rating_key')): item.get('history_id') for item in history_data if item.get('rating_key') and item.get('history_id')}
    except Exception as e:
        log.error(f"Failed to fetch Tautulli history: {e}")
        return jsonify({"error": "Failed to fetch history from Tautulli."}), 502

    data_by_library = {}
    first_error = None

    # 2. Fetch recently added for each library and process using the single history map.
    for section_id in section_ids:
        try:
            recent_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_recently_added", "section_id": section_id, "count": 25}
            recent_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=recent_params)
            recent_response.raise_for_status()
            raw_items = recent_response.json().get('response', {}).get('data', {}).get('recently_added', [])
            
            processed_items = _process_tautulli_items(raw_items, history_map)
            
            lib_info = library_info.get(section_id)
            if lib_info and lib_info.get('name'):
                data_by_library[lib_info['name']] = {
                    'items': processed_items,
                    'counts': lib_info.get('counts')
                }
        except Exception as e:
            if not first_error:
                first_error = str(e)

    # Apply date formatting if requested
    date_format = _get_date_format_from_request()
    if date_format:
        from copy import deepcopy
        data_by_library = deepcopy(data_by_library)
        _format_dates_in_response(data_by_library, date_format, time.time())

    return jsonify({
        'data': data_by_library,
        'error': first_error
    })

# --- Jellystat Endpoints ---
@app.route('/api/jellystat/libraries', methods=['GET'])
def get_jellystat_libraries():
    """Fetches the list of Jellystat libraries."""
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

@app.route('/api/jellystat/data', methods=['GET'])
def get_jellystat_data():
    """Fetches Jellystat recently added data for one or more library sections."""
    section_ids_str = request.args.get('section_id')
    if not JELLYSTAT_URL or not JELLYSTAT_API_KEY:
        return jsonify({'data': None, 'error': 'Jellystat is not configured.'}), 500

    # To get library names and counts, we need to fetch from two endpoints.
    try:
        base_url = _get_jellystat_base_url()
        libs_response = requests.get(f"{base_url}/api/getLibraries", headers=_get_jellystat_headers())
        libs_response.raise_for_status()
        libraries = libs_response.json()

        stats_response = requests.get(f"{base_url}/stats/getLibraryOverview", headers=_get_jellystat_headers())
        stats_response.raise_for_status()
        stats = stats_response.json()
        
        library_info = {
            lib.get('Id'): {
                'name': lib.get('Name'),
                'counts': (
                    lambda s: {
                        'Shows': s.get('Library_Count'),
                        'Seasons': s.get('Season_Count'),
                        'Episodes': s.get('Episode_Count')
                    } if s and s.get('CollectionType') == 'tvshows'
                    else {'Movies': s.get('Library_Count')} if s and s.get('CollectionType') == 'movies'
                    else {'Albums': s.get('Library_Count')} if s and s.get('CollectionType') == 'music'
                    else {}
                )(next((s for s in stats if s['Id'] == lib.get('Id')), None))
            }
            for lib in libraries
        }
    except Exception as e:
        log.error(f"Failed to fetch Jellystat library list for /api/data: {e}")
        return jsonify({"error": "Failed to fetch library list from Jellystat."}), 502

    # If no section_id is provided, default to all libraries.
    if not section_ids_str:
        section_ids = list(library_info.keys())
    else:
        section_ids = section_ids_str.split(',')

    data_by_library = {}
    first_error = None

    # Fetch 'recently added' for each library individually for better performance.
    for section_id in section_ids:
        try:
            base_url = _get_jellystat_base_url()
            # Use the 'libraryid' query parameter for targeted requests.
            params = {'libraryid': section_id}
            recent_response = requests.get(f"{base_url}/api/getRecentlyAdded", headers=_get_jellystat_headers(), params=params)
            recent_response.raise_for_status()
            raw_items = recent_response.json()
            
            processed_items = _process_jellystat_items(raw_items)
            
            lib_info = library_info.get(section_id)
            if lib_info and lib_info.get('name'):
                data_by_library[lib_info['name']] = {
                    'items': processed_items,
                    'counts': lib_info.get('counts')
                }
        except Exception as e:
            if not first_error:
                first_error = str(e)
                log.error(f"Failed to fetch Jellystat recently added for library {section_id}: {e}")

    # Apply date formatting if requested
    date_format = _get_date_format_from_request()
    if date_format:
        from copy import deepcopy
        data_by_library = deepcopy(data_by_library)
        _format_dates_in_response(data_by_library, date_format, time.time())

    return jsonify({'data': data_by_library, 'error': first_error})

# --- Cache for instant API response ---
_all_data_cache = {
    "data": None,
    "timestamp": 0
}
_cache_lock = threading.Lock()
POLL_INTERVAL_SECONDS = 15  # Check for changes every 15 seconds

def _fetch_all_data_concurrently():
    """Internal function to fetch all data concurrently."""
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
                counts['show'] = int(lib.get('count', 0))
                counts['season'] = int(lib.get('parent_count', 0))
                counts['episode'] = int(lib.get('child_count', 0))
            elif section_type == 'movie':
                counts['movie'] = int(lib.get('count', 0))
            elif section_type == 'artist':
                counts['artist'] = int(lib.get('count', 0))
                counts['album'] = int(lib.get('parent_count', 0))
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

def _get_library_state():
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

def update_cache_in_background(initial_state):
    """
    Periodically checks for changes in Tautulli and updates the cache only when
    a change is detected. This runs in a background thread.
    """
    last_state = initial_state
    while True:
        current_state = _get_library_state()
        if current_state and current_state != last_state:
            log.info("Change detected. Refreshing Tautulli data cache...")
            try:
                data = _fetch_all_data_concurrently()
                with _cache_lock:
                    _all_data_cache["data"] = data
                    _all_data_cache["timestamp"] = time.time()
                last_state = current_state
                log.info("Cache refresh successful.")
            except Exception as e:
                log.error(f"Error refreshing cache: {e}")
        time.sleep(POLL_INTERVAL_SECONDS)

@app.route('/api/all_data', methods=['GET'])
def get_all_data():
    """
    Serves recently added data for ALL libraries from the in-memory cache.
    Accepts an optional 'dateFormat' query parameter (e.g., ?dateFormat=short).
    """
    now = time.time()
    from copy import deepcopy
    date_format = request.args.get('dateFormat')
    
    with _cache_lock:
        # The background thread keeps this data fresh. We just serve it.
        data = _all_data_cache.get("data")

    # Handle case where cache is not yet populated on startup
    if data is None:
        return jsonify({"error": "Service is starting, data is being cached. Please try again in a few moments."}), 503

    # If a date format is specified, work on a copy to avoid mutating the cache.
    if date_format:
        data_copy = deepcopy(data)
        _format_dates_in_response(data_copy, date_format, now)
        return jsonify(data_copy)

    return jsonify(data)