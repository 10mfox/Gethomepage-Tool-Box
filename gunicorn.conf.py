import threading
import time
import logging
import os

# --- Gunicorn Configuration ---

# Bind to all network interfaces on port 5000, which is the port exposed by the container.
bind = "0.0.0.0:5000"

# Use gevent workers for asynchronous I/O
worker_class = 'gevent'

# Import config_manager to read settings from config.yaml or environment variables
try:
    from config_manager import get_config
    # Set the worker timeout. Increase if you have very large libraries.
    timeout = get_config('GUNICORN_TIMEOUT', 60, type_cast=int)
    version = get_config('VERSION', 'dev')
except ImportError:
    timeout = int(os.environ.get('GUNICORN_TIMEOUT', 60))
    version = os.environ.get('VERSION', 'dev')

log_format = f'[%(asctime)s] [%(process)d] [%(levelname)s] [v{version}] %(message)s'


# This file is used by Gunicorn to configure the application server.

def on_starting(server):
    # Configure logging for the entire application
    root_logger = logging.getLogger()
    handler = logging.StreamHandler()
    formatter = logging.Formatter(log_format)
    handler.setFormatter(formatter)
    root_logger.addHandler(handler)
    root_logger.setLevel(logging.INFO)