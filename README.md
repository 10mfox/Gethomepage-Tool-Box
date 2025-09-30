# Tautulli - Recently Added Viewer

A simple, fast, and efficient web-based tool to view the "Recently Added" media from your Plex server via the Tautulli API.

 <!-- It's recommended to replace this with an actual screenshot -->

## Features

- **Smart Library Selection**: Dynamically fetches and lists your Plex libraries, with all libraries selected by default for immediate viewing.
- **Grouped Display**: Displays recently added items grouped by library for clarity.
- **Detailed Information**: Shows the item's title (formatted for movies, TV shows, and music), year, and when it was added.
- **Flexible Date Formatting**: Choose how to display the "added at" timestamp:
    - **Date & Time**: Full timestamp (e.g., `10/1/2023, 5:00:00 PM`)
    - **Relative**: Human-readable time ago (e.g., `2 days ago`)
    - **Short**: Abbreviated date (e.g., `Oct 01`)
- **High Performance**: Utilizes a background caching mechanism. The application pre-loads all data on startup and then intelligently polls Tautulli for changes, ensuring the UI loads instantly without making the user wait for API calls.

## How It Works

The tool is composed of a Python Flask backend and a vanilla JavaScript frontend.

- The **backend** communicates with the Tautulli API to:
    1.  **Prime a cache on startup** by fetching all "recently added" data from Tautulli.
    2.  Run a **background thread** that polls Tautulli every 15 seconds to check for library changes (e.g., new media added).
    3.  If a change is detected, it **automatically refreshes the cache** with the latest data.
    4.  Provide API endpoints that allow the frontend to request data for specific libraries on-demand.
- The **frontend** provides the user interface to make selections and displays the data fetched by the backend. It updates dynamically as you select different libraries or date formats.

## Setup and Installation
This application is designed to be run as a Docker container.

### Prerequisites

- Docker and Docker Compose.
- A running instance of Tautulli connected to your Plex Media Server.
- Your Tautulli URL and API Key. You can find the API key in Tautulli under `Settings` > `Web Interface` > `API`.

### 1. Create `requirements.txt`

Your project should contain a `requirements.txt` file with the following content to specify the Python dependencies:

```txt
Flask==3.0.3
requests==2.32.3
gunicorn==22.0.0
```

### 2. Create `docker-compose.yml`

Create a file named `docker-compose.yml` in the same directory. This file will define the service and its configuration.

```yaml
services:
  media-manager:
    build: .
    container_name: media-manager
    ports:
      - "5054:5000" # Map host port 5054 to container port 5000
    environment:
      - TAUTULLI_URL=http://192.168.0.10:8181
      - TAUTULLI_API_KEY=YOUR_TAUTULLI_API_KEY
    restart: unless-stopped
    volumes:
      - .:/usr/src/app
```

**Important:** Replace the `TAUTULLI_URL` and `TAUTULLI_API_KEY` with your actual Tautulli URL and API key if they differ from the example.

### 3. Create `Dockerfile`

Create a file named `Dockerfile` in the same directory. This tells Docker how to build the application image.

```dockerfile
FROM python:3.11-slim

WORKDIR /usr/src/app

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["flask", "run", "--host=0.0.0.0", "--port=5000"]
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