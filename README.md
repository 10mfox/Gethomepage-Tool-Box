# Media Manager & Homepage Tool-Box

A powerful, fast, and efficient web-based tool to manage your self-hosted services. It provides a "Recently Added" viewer for your media servers (Plex via Tautulli, Jellyfin/Emby via Jellystat) and includes a live front-end editor for your `gethomepage` configuration files.

# Roadmap

## Completed
- [x] Added Tautulli Support
- [x] Added Jellystat Support
- [x] Basic Api For Tautulli and Jellystat Recently Added and Counts
- [x] High-Performance Caching for API to reduce CPU usage and increase speed.
- [x] Intelligent cache invalidation to automatically refresh data when changes are detected.
- [x] Added Swagger UI for API Documentation.
- [x] Live editor for all `gethomepage` configuration files (`/editor`).
- [x] Visual CSS GUI editor for live theme customization (`/editor/css-gui`).

## In Progress
- [ ] Working on Jellystat currently broken.
- [ ] Currently working on Tautulli not keeping api up to date  

## Planned
- [ ] Add Audiobookshelf Support for "Recently Added".
- [ ] Testing
- [ ] Documentation
- [ ] Final Deployment
- [ ] Final Performance Optimization

 <!-- It's recommended to replace this with an actual screenshot -->

## Features

- **Multi-Source Support**: Connects to both Tautulli (for Plex) and Jellystat (for Jellyfin/Emby) and allows you to switch between them seamlessly.
- **Live Configuration Editor**: A full-featured editor at `/editor` that allows you to view and modify all of your `gethomepage` YAML, CSS, and JS configuration files directly from the browser.
- **Live CSS GUI Editor**: A visual editor at `/editor/css-gui` with color pickers and sliders to customize your `gethomepage` theme and see the results instantly in a live preview pane.
- **Smart Library Selection**: Dynamically fetches and lists your libraries from the selected source, with all libraries selected by default for immediate viewing.
- **Grouped Display**: Displays recently added items grouped by library for clarity.
- **Detailed Information**: Shows the item's title (formatted for movies, TV shows, and music), year, and when it was added.
- **Flexible Date Formatting**: Choose how to display the "added at" timestamp:
    - **Date & Time**: Full timestamp (e.g., `10/1/2023, 5:00:00 PM`)
    - **Relative**: Human-readable time ago (e.g., `2 days ago`)
    - **Short**: Abbreviated date (e.g., `Oct 01`)
- **High Performance**: Utilizes a background caching mechanism for all data sources. The application pre-loads all data on startup and then intelligently polls for changes, ensuring the UI loads instantly without making the user wait for API calls.
- **API Documentation**: Includes a built-in Swagger UI to explore and test the backend API endpoints. Accessible at `/apidocs`.

## How It Works

The tool is composed of a Python Flask backend and a vanilla JavaScript frontend.

- The **backend** communicates with the Tautulli and Jellystat APIs to:
    1.  **Prime a cache on startup** by fetching all "recently added" data from all configured sources.
    2.  Run a **background thread** for each source that polls periodically to check for library changes (e.g., new media added).
    3.  If a change is detected, it **automatically refreshes the cache** with the latest data.
    4.  Serve all data to the frontend from the high-speed in-memory cache.
- The **frontend** provides a user interface to select a data source, filter by library, and display the cached data. It updates dynamically as you make selections.

## Setup and Installation
This application is designed to be run as a Docker container.

### Prerequisites

- Docker and Docker Compose.
- A running instance of Tautulli (for Plex) and/or Jellystat (for Jellyfin/Emby).
- A folder containing your `gethomepage` configuration files (e.g., `services.yaml`, `custom.css`).

### 1. Create `docker-compose.yml`

Create a file named `docker-compose.yml` in the same directory. This file will define the service and its configuration.

```dockercompose
services:
  redis:
    image: "redis:alpine"
    container_name: gethomepage-tool-box-redis
    restart: unless-stopped

  media-manager:
    image: ghcr.io/10mfox/gethomepage-tool-box:latest
    container_name: gethomepage-tool-box
    depends_on:
      - redis
    ports:
      - "5054:5000"
    environment:
      # --- Tautulli / Jellystat Configuration ---
      - TAUTULLI_URL=http://0.0.0.0:1234
      - TAUTULLI_API_KEY=your_tautulli_key
      - JELLYSTAT_URL=http://0.0.0.0:1234
      - JELLYSTAT_API_KEY=your_jellystat_key
      
      # --- Homepage Editor Preview URL ---
      - HOMEPAGE_PREVIEW_URL=https://your.homepage.url
      
      # --- Redis Configuration ---
      - REDIS_HOST=redis
    restart: unless-stopped
    volumes:
      # Mount your local gethomepage config folder into the container
      - /path/to/your/homepage/config:/app/config
```

**Important:** Replace the `TAUTULLI_URL` or `JELLYSTAT_URL` and `TAUTULLI_API_KEY` or `JELLYSTAT_API_KEY` with your actual Tautulli URL or Jellystat URL, and API key if they differ from the example.

### 3. Run the Application

Open a terminal in the project directory and run the following command:

```sh
docker-compose up -d
```

The application will now be running and accessible at `http://localhost:5054` (or whichever host port you configured).

## API Endpoints

The backend provides several API endpoints. For a full, interactive experience with live testing, visit `/apidocs` on your running instance (e.g., `http://localhost:5053/apidocs`).

### `GET /api/sources`

Returns a list of the data sources (Tautulli, Jellystat) that are configured on the server.

*   **Response (200 OK):**
    ```json
    [
      {
        "id": "tautulli",
        "name": "Tautulli"
      },
      {
        "id": "jellystat",
        "name": "Jellystat"
      }
    ]
    ```

### `GET /api/tautulli/libraries` and `GET /api/jellystat/libraries`

Fetches the list of all available libraries, including media counts, for the specified source.

*   **Response (200 OK):** A JSON array of library objects.
    ```json
    [
      {
        "section_id": "1",
        "section_name": "Movies",
        "counts": { "Movies": 1234 }
      }
    ]
    ```

### `GET /api/data` (Cached)

Fetches all recently added items for a given source from the in-memory cache. This is the primary endpoint for the frontend and is extremely fast.

*   **Query Parameters:**
    *   `source` (required): The data source to query. Example: `?source=tautulli`
    *   `dateFormat` (optional): The format for dates. Options: `short`, `relative`. Example: `?source=tautulli&dateFormat=relative`

*   **Response (200 OK):** A JSON object containing the data grouped by library name.

    ```json
    {
      "Movies": {
        "items": [
          {
            "added_at": 1672531200,
            "title": "The Matrix",
            "year": "1999",
            "id": "hist_12345"
          }
        ],
        "counts": {
          "Movies": 1234
        }
      },
      "TV Shows": {
        "items": [
          {
            "added_at": 1672617600,
            "title": "The Simpsons - S04E12 - Marge vs. the Monorail",
            "year": "1993"
          }
        ],
        "counts": { "Shows": 150, "Seasons": 10, "Episodes": 300 }
      }
    }
    ```
