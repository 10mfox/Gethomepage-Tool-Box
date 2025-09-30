import os
import requests
from flask import Flask, render_template, request, jsonify
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
import threading
import time

app = Flask(__name__, template_folder='.')

# Read configuration from environment variables
TAUTULLI_URL = os.environ.get('TAUTULLI_URL')
TAUTULLI_API_KEY = os.environ.get('TAUTULLI_API_KEY')

# --- Tautulli Functions ---
def _process_tautulli_items(items, history_map):
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


# --- Flask Routes ---
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/libraries', methods=['GET'])
def get_libraries():
    """Fetches the list of Tautulli libraries."""
    if not TAUTULLI_URL or not TAUTULLI_API_KEY:
        return jsonify({"error": "Tautulli is not configured on the server."}), 500

    try:
        params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_libraries"}
        response = requests.get(f"{TAUTULLI_URL}/api/v2", params=params)
        response.raise_for_status()
        libraries = response.json().get('response', {}).get('data', [])
        return jsonify(libraries)
    except Exception as e:
        return jsonify({"error": str(e)}), 502

@app.route('/api/data', methods=['GET'])
def get_data():
    """Fetches recently added data for one or more library sections."""
    section_ids_str = request.args.get('section_id')
    if not section_ids_str:
        return jsonify({"error": "Missing required query parameter: 'section_id'"}), 400

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
        library_map = {str(lib['section_id']): lib['section_name'] for lib in libraries}
    except Exception as e:
        return jsonify({"error": f"Failed to fetch library list: {e}"}), 502

    # --- Efficient Data Fetching ---
    # 1. Fetch history ONCE for all selected libraries.
    try:
        history_params = {"apikey": TAUTULLI_API_KEY, "cmd": "get_history", "length": 250}
        history_response = requests.get(f"{TAUTULLI_URL}/api/v2", params=history_params)
        history_response.raise_for_status()
        history_data = history_response.json().get('response', {}).get('data', {}).get('data', [])
        history_map = {str(item.get('rating_key')): item.get('history_id') for item in history_data if item.get('rating_key') and item.get('history_id')}
    except Exception as e:
        return jsonify({"error": f"Failed to fetch Tautulli history: {e}"}), 502

    section_ids = section_ids_str.split(',')
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
            
            library_name = library_map.get(section_id)
            if library_name:
                data_by_library[library_name] = processed_items
        except Exception as e:
            if not first_error:
                first_error = str(e)

    return jsonify({
        'data': data_by_library,
        'error': first_error
    })

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
            return library['section_name'], items
        except Exception as e:
            print(f"Error fetching for library {library['section_name']}: {e}")
            return library['section_name'], []

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
        print(f"State check: Could not fetch library state: {e}")
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
            print("Change detected. Refreshing Tautulli data cache...")
            try:
                data = _fetch_all_data_concurrently()
                with _cache_lock:
                    _all_data_cache["data"] = data
                    _all_data_cache["timestamp"] = time.time()
                last_state = current_state
                print("Cache refresh successful.")
            except Exception as e:
                print(f"Error refreshing cache: {e}")
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
        data = deepcopy(data)

    if date_format == 'short':
        # Need to iterate through the new structure
        for library_name, library_data in data.items():
            for item in library_data.get('items', []):
                if 'added_at' in item and isinstance(item['added_at'], int):
                    item['added_at'] = datetime.fromtimestamp(item['added_at']).strftime('%b %d')

    elif date_format == 'relative':
        for library_name, library_data in data.items():
            for item in library_data.get('items', []):
                if 'added_at' in item and isinstance(item['added_at'], int):
                    seconds = int(now - item['added_at'])
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

    return jsonify(data)