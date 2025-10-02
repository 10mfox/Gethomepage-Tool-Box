# Media Manager - Recently Added Viewer

# Roadmap

## Completed
- [x] Added Tautulli Support
- [x] Added Jellystat Support
- [x] Basic Api For Tautulli and Jellystat Recently Added and Counts

## In Progress
- [ ] Trying Too Speedup Api Without High Cpu Usage From This Container Or The Source Container Right Now It Is Very Slow And High Cpu Usage

## Planned
- [ ] Add Audiobookshelf Support
- [ ] Add A Way To Modify The Custom Api To Your Liking
- [ ] Testing
- [ ] Documentation
- [ ] Final Deployment
- [ ] Final Performance Optimization


A simple, fast, and efficient web-based tool to view the "Recently Added" media from your media servers via the Tautulli and Jellystat APIs.

 <!-- It's recommended to replace this with an actual screenshot -->

## Features

- **Multi-Source Support**: Connects to both Tautulli (for Plex) and Jellystat (for Jellyfin/Emby) and allows you to switch between them seamlessly.
- **Smart Library Selection**: Dynamically fetches and lists your libraries from the selected source, with all libraries selected by default for immediate viewing.
- **Grouped Display**: Displays recently added items grouped by library for clarity.
- **Detailed Information**: Shows the item's title (formatted for movies, TV shows, and music), year, and when it was added.
- **Flexible Date Formatting**: Choose how to display the "added at" timestamp:
    - **Date & Time**: Full timestamp (e.g., `10/1/2023, 5:00:00 PM`)
    - **Relative**: Human-readable time ago (e.g., `2 days ago`)
    - **Short**: Abbreviated date (e.g., `Oct 01`)
- **High Performance (Tautulli)**: Utilizes a background caching mechanism for Tautulli. The application pre-loads all data on startup and then intelligently polls Tautulli for changes, ensuring the UI loads instantly without making the user wait for API calls.

## How It Works

The tool is composed of a Python Flask backend and a vanilla JavaScript frontend.

- The **backend** communicates with the Tautulli API to:
    1.  **Prime a cache on startup** by fetching all "recently added" data from Tautulli.
    2.  Run a **background thread** that polls Tautulli periodically to check for library changes (e.g., new media added).
    3.  If a change is detected, it **automatically refreshes the cache** with the latest data.
    4.  Provide on-demand API endpoints for both Tautulli and Jellystat.
- The **frontend** provides the user interface to select a data source, choose libraries, and displays the data fetched from the backend. It updates dynamically as you make selections.

## Setup and Installation
This application is designed to be run as a Docker container.

### Prerequisites

- Docker and Docker Compose.
- A running instance of Tautulli connected to your Plex Media Server.
- A running instance of Jellystat connected to your Jellyfin/Emby server.
- Your Tautulli URL and API Key (found in Tautulli under `Settings` > `Web Interface` > `API`).
- Your Jellystat URL and API Key (found in Jellystat under `Settings` > `General` > `API Keys`).
### 1. Create `requirements.txt`

Your project should contain a `requirements.txt` file with the following content to specify the Python dependencies:

```txt
Flask==3.0.3
requests==2.32.3
gunicorn==22.0.0
```

### 2. Create `docker-compose.yml`

Create a file named `docker-compose.yml` in the same directory. This file will define the service and its configuration.

```dockercompose
services:
  media-manager:
    build:
      context: .
      args:
        - VERSION=${VERSION:-dev}
    container_name: media-manager
    ports:
      - "5053:5000" # Map host port 5053 to container port 5000
    environment:
      - TAUTULLI_URL=http://192.168.0.10:8181
      - TAUTULLI_API_KEY=54bcef21d7084082b189a11ca7f6bf6a
      # --- Optional: Add your Jellystat details here ---
      - JELLYSTAT_URL=http://192.168.0.10:3033
      - JELLYSTAT_API_KEY=b8026968-cce4-40a2-8fba-73c4939a5183
    restart: unless-stopped
    volumes:
      - .:/usr/src/app
```

**Important:** Replace the `TAUTULLI_URL` and `TAUTULLI_API_KEY` with your actual Tautulli URL and API key if they differ from the example.

### 3. Create a `Dockerfile`

Create a file named `Dockerfile` in the same directory. This tells Docker how to build the application image.

```dockerfile
FROM python:3.11-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["gunicorn", "-c", "gunicorn.conf.py", "app:app"]
```

### 4. Run the Application

Open a terminal in the project directory and run the following command:

```sh
docker-compose up -d
```

The application will now be running and accessible at `http://localhost:5054` (or whichever host port you configured).

## API Endpoints

The backend provides several API endpoints that the frontend consumes. You can also use these for your own integrations.

### `GET /api/libraries`

Fetches the list of all available libraries from your Tautulli instance.

*   **Response (200 OK):** A JSON array of library objects.

    ```json
    [
      {
        "section_id": "1",
        "section_name": "Movies",
        "section_type": "movie",
        "count": "1234"
      },
      {
        "section_id": "2",
        "section_name": "TV Shows",
        "section_type": "show",
        "count": "150"
      }
    ]
    ```

### `GET /api/data`

Fetches the recently added items for one or more specified libraries.

*   **Query Parameters:**
    *   `section_id` (required): A comma-separated string of library `section_id`s. Example: `?section_id=1,2`

*   **Response (200 OK):** A JSON object containing the data grouped by library name.

    ```json
    {
      "data": {
        "Movies": [
          {
            "added_at": 1672531200,
            "id": "hist_12345",
            "title": "The Matrix",
            "type": "movie",
            "year": "1999"
          }
        ],
        "TV Shows": [
          {
            "added_at": 1672617600,
            "id": "hist_12346",
            "title": "The Simpsons - S04E12 - Marge vs. the Monorail",
            "type": "episode",
            "year": "1993"
          }
        ]
      },
      "error": null
    }
    ```
