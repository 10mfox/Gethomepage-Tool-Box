# Roadmap

## Completed
- [x] **Core Data Sources**:
    - [x] Added Tautulli Support
    - [x] Added Jellystat Support
    - [x] Added Audiobookshelf Support
- [x] **API & Endpoints**:
    - [x] API for "Recently Added" and "Counts" for all sources.
    - [x] API for Tautulli & Jellystat "User Activity" (currently playing/paused).
    - [x] API for Tautulli & Jellystat "Last Watched" for inactive users.
- [x] High-Performance Caching for API to reduce CPU usage and increase speed.
- [x] Intelligent cache invalidation to automatically refresh data when changes are detected.
- [x] Added Swagger UI for API Documentation (`/apidocs`).
- [x] **Editor Suite**:
    - [x] Live editor for all `gethomepage` configuration files (`/editor`).
    - [x] Visual CSS GUI editor for live theme customization (`/editor/css-gui`).
    - [x] Mappings editor for custom title formatting (`/editor/mappings`).
        - [x] Added support for creating multiple custom templates for each media type.
    - [x] Raw data viewer for debugging and field discovery (`/editor/debug-raw`).
- [x] Fixed Jellystat integration issues.
- [x] Added optional environment variables (`ENABLE_CONFIG_EDITOR`, `ENABLE_DEBUG`) to simplify the default UI.
- [x] **YAML Widget Generator**:
    - [x] Added to Mappings Editor.
    - [x] Added dropdowns to select templates for the left and right side of the widget.
- [x] Ensured all sources stay up-to-date with background polling.

## Planned
- [ ] Add Radarr/Sonarr Support
- [ ] Final Documentation Review
- [ ] Final Performance Optimization & Testing

---

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/S6S6S178E)
