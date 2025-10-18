import os
import logging
from flask import Blueprint, jsonify, render_template, request
from app import any_source_configured, ENABLE_CONFIG_EDITOR, ENABLE_DEBUG, TAUTULLI_URL, TAUTULLI_API_KEY, JELLYSTAT_URL, JELLYSTAT_API_KEY, AUDIOBOOKSHELF_URL, AUDIOBOOKSHELF_API_KEY

from mapping_manager import get_mappings, get_default_mappings, save_mappings
editor_bp = Blueprint('editor', __name__, template_folder='.')
log = logging.getLogger(__name__)

CONFIG_PATH = '/app/config'

ALLOWED_FILES = [
    'authentication.yaml', 'bookmarks.yaml', 'custom.js', 'custom.css',
    'docker.yaml', 'kubernetes.yaml', 'proxmox.yaml', 'services.yaml',
    'settings.yaml', 'widgets.yaml'
]

@editor_bp.route('/')
def editor_index():
    """Serves the editor's frontend."""
    homepage_url = os.environ.get('HOMEPAGE_PREVIEW_URL', '')
    return render_template('editor.html', homepage_preview_url=homepage_url, any_source_configured=any_source_configured, enable_config_editor=ENABLE_CONFIG_EDITOR, enable_debug=ENABLE_DEBUG)

@editor_bp.route('/css-gui')
def css_gui_index():
    """Serves the CSS GUI editor's frontend."""
    homepage_url = os.environ.get('HOMEPAGE_PREVIEW_URL', '')
    return render_template('css-gui.html', homepage_preview_url=homepage_url, any_source_configured=any_source_configured, enable_config_editor=ENABLE_CONFIG_EDITOR, enable_debug=ENABLE_DEBUG)

@editor_bp.route('/mappings')
def mappings_editor_index():
    """Serves the Mappings editor's frontend."""
    return render_template('mappings-editor.html', any_source_configured=any_source_configured, enable_config_editor=ENABLE_CONFIG_EDITOR, enable_debug=ENABLE_DEBUG)

@editor_bp.route('/debug-raw')
def debug_raw_index():
    """Serves the Raw Data Viewer's frontend."""
    return render_template('debug-raw.html', any_source_configured=any_source_configured, enable_config_editor=ENABLE_CONFIG_EDITOR, enable_debug=ENABLE_DEBUG)


@editor_bp.route('/api/files', methods=['GET'])
def list_files():
    """List Editable Config Files
    ---
    tags:
      - Editor
    description: Returns a list of editable configuration files found in the config directory.
    responses:
      200:
        description: A list of filenames.
        schema: {type: array, items: {type: string, example: 'services.yaml'}}
    """
    found_files = []
    if not os.path.isdir(CONFIG_PATH):
        log.error(f"Config directory not found at {CONFIG_PATH}. Did you mount the volume?")
        return jsonify([])
        
    for filename in ALLOWED_FILES:
        if os.path.exists(os.path.join(CONFIG_PATH, filename)):
            found_files.append(filename)
    return jsonify(found_files)

@editor_bp.route('/api/files/<filename>', methods=['GET'])
def get_file(filename):
    """Get File Content
    ---
    tags:
      - Editor
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: The name of the file to retrieve.
    responses:
      200:
        description: The content of the file.
        schema: {type: object, properties: {content: {type: string}}}
      403:
        description: File is not in the allowed list.
      404:
        description: File not found.
      500:
        description: Error reading the file.
    """
    if filename not in ALLOWED_FILES:
        return jsonify({"error": "File not allowed"}), 403

    filepath = os.path.join(CONFIG_PATH, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found"}), 404

    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            content = f.read()
        return jsonify({"content": content})
    except Exception as e:
        log.error(f"Error reading file {filename}: {e}")
        return jsonify({"error": f"Could not read file: {e}"}), 500

@editor_bp.route('/api/files/<filename>', methods=['POST'])
def save_file(filename):
    """Save File Content
    ---
    tags:
      - Editor
    parameters:
      - name: filename
        in: path
        type: string
        required: true
        description: The name of the file to save.
      - name: body
        in: body
        required: true
        schema:
          type: object
          properties:
            content: {type: string, description: "The new content of the file."}
    responses:
      200: {description: "Success message."}
      400: {description: "Missing content in request body."}
      403: {description: "File is not in the allowed list."}
      500: {description: "Error writing to the file."}
    """
    if filename not in ALLOWED_FILES:
        return jsonify({"message": "File not allowed"}), 403

    filepath = os.path.join(CONFIG_PATH, filename)
    data = request.get_json()

    if 'content' not in data:
        return jsonify({"message": "Missing 'content' in request"}), 400

    try:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(data['content'])
        return jsonify({"message": f"Successfully saved {filename}"})
    except Exception as e:
        log.error(f"Error writing to file {filename}: {e}")
        return jsonify({"message": f"Could not save file: {e}"}), 500

@editor_bp.route('/api/mappings', methods=['GET'])
def get_mappings_api():
    """Get Current Mappings
    ---
    tags:
      - Mappings
    description: Returns the current title-formatting mappings, from mappings.yaml or default.
    responses:
      200:
        description: The current mapping configuration.
    """
    mappings = get_mappings()
    filtered_mappings = {}
    if TAUTULLI_URL and TAUTULLI_API_KEY and 'tautulli' in mappings:
        filtered_mappings['tautulli'] = mappings['tautulli']
    if JELLYSTAT_URL and JELLYSTAT_API_KEY and 'jellystat' in mappings:
        filtered_mappings['jellystat'] = mappings['jellystat']
    if AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_KEY and 'audiobookshelf' in mappings:
        filtered_mappings['audiobookshelf'] = mappings['audiobookshelf']
    return jsonify(filtered_mappings)

@editor_bp.route('/api/mappings/default', methods=['GET'])
def get_default_mappings_api():
    """Get Default Mappings
    ---
    tags:
      - Mappings
    description: Returns the hardcoded default title-formatting mappings.
    responses:
      200:
        description: The default mapping configuration.
    """
    mappings = get_default_mappings()
    filtered_mappings = {}
    if TAUTULLI_URL and TAUTULLI_API_KEY and 'tautulli' in mappings:
        filtered_mappings['tautulli'] = mappings['tautulli']
    if JELLYSTAT_URL and JELLYSTAT_API_KEY and 'jellystat' in mappings:
        filtered_mappings['jellystat'] = mappings['jellystat']
    if AUDIOBOOKSHELF_URL and AUDIOBOOKSHELF_API_KEY and 'audiobookshelf' in mappings:
        filtered_mappings['audiobookshelf'] = mappings['audiobookshelf']
    return jsonify(filtered_mappings)

@editor_bp.route('/api/mappings', methods=['POST'])
def save_mappings_api():
    """Save Mappings
    ---
    tags:
      - Mappings
    description: Saves the provided mapping configuration to mappings.yaml.
    parameters:
      - name: body
        in: body
        required: true
        description: The mapping configuration object to save.
        schema:
          type: object
          example:
            tautulli:
              episode:
                template: "{grandparent_title} - S{parent_media_index}E{media_index}"
                fields: ["grandparent_title", "parent_media_index", "media_index"]
    responses:
      200:
        description: Success message.
      500:
        description: Error saving the mappings file.
    """
    data = request.get_json()
    success, message = save_mappings(data)
    if success:
        return jsonify({"message": message})
    else:
        return jsonify({"message": message}), 500