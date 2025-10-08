import os
import logging
from flask import Blueprint, jsonify, render_template, request

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
    return render_template('editor.html', homepage_preview_url=homepage_url)

@editor_bp.route('/css-gui')
def css_gui_index():
    """Serves the CSS GUI editor's frontend."""
    homepage_url = os.environ.get('HOMEPAGE_PREVIEW_URL', '')
    return render_template('css-gui.html', homepage_preview_url=homepage_url)

@editor_bp.route('/api/files', methods=['GET'])
def list_files():
    """Returns a list of editable configuration files found in the config directory."""
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
    """Returns the content of a specific configuration file."""
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
    """Saves content to a specific configuration file."""
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