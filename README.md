# Media Manager & Homepage Tool-Box

A powerful, fast, and efficient web-based tool to manage your self-hosted services. It provides a "Recently Added" viewer for your media servers (Plex via Tautulli, Jellyfin/Emby via Jellystat, Audiobookshelf) and includes a suite of live editors for your `gethomepage` configuration files.

:arrow_right: **[Click here to see my project roadmap](./Roadmap.md)**

## Features

- **Multi-Source Support**: Connects to Tautulli (for Plex), Jellystat (for Jellyfin/Emby), and Audiobookshelf, allowing you to switch between them seamlessly.
- **Configuration Editor Suite**:
    - **File Editor** (`/editor`): A full-featured editor to modify all your `gethomepage` YAML, CSS, and JS configuration files.
    - **CSS GUI Editor** (`/editor/css-gui`): A visual editor with color pickers and sliders to customize your `gethomepage` theme and see the results instantly in a live preview pane.
    - **Mappings Editor** (`/editor/mappings`): Customize how media titles are displayed using templates and available data fields from your media servers.
    - **Raw Data Viewer** (`/editor/debug-raw`): A tool to inspect the raw data from your media servers, perfect for discovering fields to use in your title mappings.
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
      - "5054:5000" # Map host port 5054 to container port 5000
    environment:
      - TAUTULLI_URL=http://0.0.0.0:1234
      - TAUTULLI_API_KEY=your_tautulli_api_key
      # --- Optional: Add your Jellystat details here ---
      - JELLYSTAT_URL=http://0.0.0.0:1234
      - JELLYSTAT_API_KEY=your_jellystat_api_key
      # --- Optional: Add your Audiobookshelf details here ---
      - AUDIOBOOKSHELF_URL=http://0.0.0.0:1234
      - AUDIOBOOKSHELF_API_KEY=your_audiobookshelf_api_key
      # --- Homepage Editor Preview URL ---
      - HOMEPAGE_PREVIEW_URL=https://your-homepage-instance.com
      # --- Redis Configuration ---
      - REDIS_HOST=redis
    restart: unless-stopped
    volumes:
      # Mount your local gethomepage config folder into the container
      - /path/to/your/homepage/config:/app/config
```

**Important:** Replace the `TAUTULLI_URL` or `JELLYSTAT_URL` or `AUDIOBOOKSHELF_URL` and `TAUTULLI_API_KEY` or `JELLYSTAT_API_KEY` or `AUDIOBOOKSHELF_API_KEY` with your actual Tautulli URL or Jellystat URL or Audiobookshelf URL, and API key if they differ from the example.

### 3. Run the Application

Open a terminal in the project directory and run the following command:

```sh
docker-compose up -d
```

The application will now be running and accessible at `http://localhost:5054` (or whichever host port you configured).

## API Endpoints

The backend provides several API endpoints. For a full, interactive experience with live testing, visit `/apidocs` on your running instance (e.g., `http://localhost:5054/apidocs`).
