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
    from app import _fetch_all_data_concurrently, _get_library_state, _all_data_cache, update_cache_in_background

    # Configure logging for the entire application
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)

    # Gunicorn's own logs will now use this format.
    server.log.info("Gunicorn starting: Priming data cache...")
    try:
        initial_data = _fetch_all_data_concurrently()
        _all_data_cache["data"] = initial_data
        _all_data_cache["timestamp"] = time.time()
        initial_state = _get_library_state()
        server.log.info("Gunicorn: Initial cache populated successfully.")

        # Start the background thread to keep the cache warm
        cache_thread = threading.Thread(target=update_cache_in_background, args=(initial_state,), daemon=True)
        cache_thread.start()
        server.log.info("Gunicorn: Background cache-refresh thread started.")
    except Exception as e:
        server.log.error(f"FATAL: Could not perform initial cache. Error: {e}")
        exit(1)  # Exit if we can't get the initial data