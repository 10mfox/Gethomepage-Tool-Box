import threading
import time
import logging
import os

# --- Gunicorn Configuration ---

# Bind to all network interfaces on port 5000, which is the port exposed by the container.
bind = "0.0.0.0:5000"

version = os.environ.get('VERSION', 'dev')

# Use gevent workers for asynchronous I/O
worker_class = 'gevent'

# Set the worker timeout. Defaults to 30 seconds.
timeout = int(os.environ.get('GUNICORN_TIMEOUT', 30))
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