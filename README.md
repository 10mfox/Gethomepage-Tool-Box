# Media Manager & Homepage Tool-Box

A powerful, fast, and efficient web-based tool to manage your self-hosted services. It provides a "Recently Added" viewer for your media servers (Plex via Tautulli, Jellyfin/Emby via Jellystat, Audiobookshelf) and includes a suite of live editors for your `gethomepage` configuration files. If no media servers are configured, it defaults to the CSS GUI Editor for immediate use.

:arrow_right: **Click here to see my project roadmap**

https://github.com/user-attachments/assets/30afe333-712b-468c-9506-4c3c38011ed8

## Features

- **Multi-Source Support**: Connects to Tautulli (for Plex), Jellystat (for Jellyfin/Emby), and Audiobookshelf, allowing you to switch between them seamlessly.
- **Live Activity Monitoring**:
    - View currently playing and paused sessions from Tautulli and Jellystat.
    - See the last played item for users who are not currently active.
- **Configuration Editor Suite**:
    - **File Editor** (`/editor`): A full-featured editor to modify all your `gethomepage` YAML, CSS, and JS configuration files. (Optional, enable with `ENABLE_CONFIG_EDITOR=true`)
    - **CSS GUI Editor** (`/editor/css-gui`): A visual editor with color pickers and sliders to customize your `gethomepage` theme and see the results instantly in a live preview pane.
    - **Mappings Editor** (`/editor/mappings`): Customize how media titles are displayed using templates and available data fields from your media servers.
    - **Raw Data Viewer** (`/editor/debug-raw`): A tool to inspect the raw data from your media servers, perfect for discovering fields to use in your title mappings. (Optional, enable with `ENABLE_DEBUG=true`)
- **YAML Widget Generator**: A tool within the Mappings Editor to quickly generate the necessary YAML configuration for "Recently Added" and "User Activity" widgets for your homepage.
- **Smart Library Selection**: Dynamically fetches and lists your libraries from the selected source, with all libraries selected by default for immediate viewing.
- **Grouped Display**: Displays recently added items grouped by library for clarity.
- **Flexible Date Formatting**: Choose how to display the "added at" timestamp:
    - **Relative**: Human-readable time ago (e.g., `2 days ago`)
    - **Short**: Abbreviated date (e.g., `Oct 01`)
- **High Performance**: Utilizes a background caching mechanism for all data sources. The application pre-loads all data on startup and then intelligently polls for changes, ensuring the UI loads instantly without making the user wait for API calls.
- **API Documentation**: Includes a built-in Swagger UI to explore and test the backend API endpoints. Accessible at `/apidocs`.

## How It Works

The tool is composed of a Python Flask backend and a vanilla JavaScript frontend.

- The **backend** communicates with the Tautulli, Jellystat, and Audiobookshelf APIs to:
    1.  **Prime a cache on startup** by fetching all "recently added" data from all configured sources.
    2.  Run a **background thread** for each source that polls periodically to check for library changes (e.g., new media added).
    3.  If a change is detected, it **automatically refreshes the cache** with the latest data.
    4.  Serve all data to the frontend from the high-speed in-memory cache.
- The **frontend** provides a user interface to select a data source, filter by library, and display the cached data. It updates dynamically as you make selections.

## Setup and Installation
This application is designed to be run as a Docker container.

### Prerequisites

- Docker and Docker Compose.
- A running instance of Tautulli (for Plex), Jellystat (for Jellyfin/Emby), and/or Audiobookshelf.
- A folder containing your `gethomepage` configuration files (e.g., `services.yaml`, `custom.css`).

### 1. Create `docker-compose.yml`

Create a file named `docker-compose.yml` in the same directory. This file will define the service and its configuration.

```dockercompose
services:
  redis:
    image: "redis:alpine"
    container_name: media-manager-redis
    restart: unless-stopped

  media-manager:
    image: ghcr.io/10mfox/gethomepage-tool-box:latest
    container_name: media-manager
    depends_on:
      - redis
    ports:
      - "5000:5000" # Map host port 5000 to container port 5000
    env_file:
      - .env
    restart: unless-stopped
    volumes:
      # Mount your local gethomepage config folder into the container
      - /path/to/your/homepage/config:/app/config
```

**Important:** Be sure to add your .env variables for what you are using to a .env file located same place as docker-compose.yaml.

Here is an Example .env
```env
# --- Tool-Box Env --- #

# --- Required In Env --- #
REDIS_HOST=redis
TZ=America/New_York # Replace with your timezone from https://en.wikipedia.org/wiki/List_of_tz_database_time_zones

# ---------- Only Add What You Are Using Below This Point ---------- #

# --- Optional: Add your Tautulli details here --- #
TAUTULLI_URL=http://Your-Ip:8181
TAUTULLI_API_KEY=Your-Api-Key

# --- Optional: Add your Jellystat details here --- #
JELLYSTAT_URL=http://Your-Ip:3033
JELLYSTAT_API_KEY=Your-Api-Key

# --- Optional: Add your Audiobookshelf details here --- #
AUDIOBOOKSHELF_URL=http://Your-Ip:13378
AUDIOBOOKSHELF_API_KEY=Your-Api-Key

# --- Optional: Add your Homepage URL For Preview In CSS Editor --- #
HOMEPAGE_PREVIEW_URL=http://Your-Ip:3000

# ---------- Advanced settings ---------- #

# --- Optional: Advanced settings --- #
POLL_INTERVAL=15 # How often (in seconds) to check for library updates. Default: 15
REQUEST_TIMEOUT=30 # How long (in seconds) to wait for API responses. Default: 30
GUNICORN_TIMEOUT=60 # Gunicorn worker timeout. Increase if you have very large libraries. Default: 30

# --- Optional: Enable advanced editor features --- #
ENABLE_CONFIG_EDITOR=true # Set to true to enable the full config file editor
ENABLE_DEBUG=true # Set to true to enable the raw data viewer
```

**Important:** Replace the `TAUTULLI_URL` or `JELLYSTAT_URL` or 'AUDIOBOOKSHELF_URL' and `TAUTULLI_API_KEY` or `JELLYSTAT_API_KEY` or 'AUDIOBOOKSHELF_API_KEY' with your actual Tautulli URL or Jellystat URL or Audiobookshelf URL, and API key if they differ from the example.

### 3. Run the Application

Open a terminal in the project directory and run the following command:

```sh
docker-compose up -d
```

The application will now be running and accessible at `http://localhost:5000` (or whichever host port you configured).
