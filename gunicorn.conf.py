import threading
import time
import logging
import os

# --- Gunicorn Configuration ---

version = os.environ.get('VERSION', 'dev')
log_format = f'[%(asctime)s] [%(process)d] [%(levelname)s] [v{version}] %(message)s'


# This file is used by Gunicorn to configure the application server.

def on_starting(server):
    """
    This hook is called just before the master process is initialized.
    It's the perfect place to prime our cache.
    """
    # We need to import the app components here
    from app import (
        app, _all_data_cache, update_cache_in_background, get_sources,
        _fetch_all_tautulli_data_concurrently, _get_tautulli_library_state,
        _fetch_all_jellystat_data_concurrently, _get_jellystat_library_state
    )
    # Initialize cache structure
    _all_data_cache["data"] = {}
    _all_data_cache["timestamp"] = {}
    
    # Configure logging for the entire application
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Gunicorn's own logs will now use this format.
    server.log.info("Gunicorn starting: Priming data caches...")

    # Determine which sources are configured by calling the get_sources endpoint internally
    with app.app_context():
        configured_sources = get_sources().get_json()

    if not configured_sources:
        server.log.warning("No data sources (Tautulli/Jellystat) are configured. Caching will be skipped.")
        return

    for source in configured_sources:
        source_id = source['id']
        server.log.info(f"Priming cache for source: {source_id}...")
        try:
            if source_id == 'tautulli':
                initial_data = _fetch_all_tautulli_data_concurrently()
                initial_state = _get_tautulli_library_state()
            elif source_id == 'jellystat':
                initial_data = _fetch_all_jellystat_data_concurrently()
                initial_state = _get_jellystat_library_state()
            else:
                server.log.warning(f"Unknown source '{source_id}' found. Skipping cache.")
                continue

            _all_data_cache["data"][source_id] = initial_data
            _all_data_cache["timestamp"][source_id] = time.time()
            server.log.info(f"Initial cache for {source_id} populated successfully.")

            if initial_state is not None:
                # Start a dedicated background thread for this source
                cache_thread = threading.Thread(target=update_cache_in_background, args=(source_id, initial_state), daemon=True)
                cache_thread.start()
                server.log.info(f"Background cache-refresh thread for {source_id} started.")
            else:
                server.log.warning(f"Could not get initial state for {source_id}. Background refresh will not start.")
        except Exception as e:
            server.log.error(f"FATAL: Could not perform initial cache for {source_id}. Error: {e}")
            # We don't exit here, to allow other sources to potentially work.