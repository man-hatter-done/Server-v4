"""
File management API endpoints for Termux-like file access.
These endpoints provide a RESTful interface for managing files and directories.
"""

import os
import shutil
from datetime import datetime
from flask import jsonify, request, send_file
from werkzeug.utils import secure_filename

def register_file_management_endpoints(app, get_session):
    """
    Register all file management endpoints with the Flask app.
    
    Args:
        app: The Flask application instance
        get_session: Function to retrieve a valid session
    """
    
    @app.route('/files', methods=['GET'])
    def list_files():
        """List files and directories in a path relative to the user's home directory"""
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        path = request.args.get('path', '')
        # Sanitize path to prevent path traversal
        base_dir = session['home_dir']
        target_path = os.path.normpath(os.path.join(base_dir, path))
        
        # Ensure the path is within the user's home directory
        if not target_path.startswith(base_dir):
            return jsonify({'error': 'Invalid path'}), 403
        
        try:
            if not os.path.exists(target_path):
                return jsonify({'error': 'Path does not exist'}), 404
                
            if os.path.isfile(target_path):
                return jsonify({'error': 'Path is a file, not a directory'}), 400
                
            files = []
            for item in os.listdir(target_path):
                item_path = os.path.join(target_path, item)
                item_stat = os.stat(item_path)
                files.append({
                    'name': item,
                    'path': os.path.relpath(item_path, base_dir),
                    'is_dir': os.path.isdir(item_path),
                    'size': item_stat.st_size,
                    'modified': datetime.fromtimestamp(item_stat.st_mtime).isoformat()
                })
                
            return jsonify({
                'path': path,
                'files': files
            })
        except Exception as e:
            return jsonify({'error': f'Failed to list files: {str(e)}'}), 500

    @app.route('/files/download', methods=['GET'])
    def download_file():
        """Download a file from the user's directory"""
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        path = request.args.get('path', '')
        if not path:
            return jsonify({'error': 'Path is required'}), 400
            
        # Sanitize path to prevent path traversal
        base_dir = session['home_dir']
        target_path = os.path.normpath(os.path.join(base_dir, path))
        
        # Ensure the path is within the user's home directory
        if not target_path.startswith(base_dir):
            return jsonify({'error': 'Invalid path'}), 403
        
        try:
            if not os.path.exists(target_path):
                return jsonify({'error': 'File does not exist'}), 404
                
            if not os.path.isfile(target_path):
                return jsonify({'error': 'Path is not a file'}), 400
                
            return send_file(target_path, as_attachment=True)
        except Exception as e:
            return jsonify({'error': f'Failed to download file: {str(e)}'}), 500

    @app.route('/files/upload', methods=['POST'])
    def upload_file():
        """Upload a file to the user's directory"""
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        path = request.form.get('path', '')
        
        # Sanitize path to prevent path traversal
        base_dir = session['home_dir']
        target_dir = os.path.normpath(os.path.join(base_dir, path))
        
        # Ensure the path is within the user's home directory
        if not target_dir.startswith(base_dir):
            return jsonify({'error': 'Invalid path'}), 403
        
        # Create directory if it doesn't exist
        os.makedirs(target_dir, exist_ok=True)
        
        if 'file' not in request.files:
            return jsonify({'error': 'No file part'}), 400
            
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No selected file'}), 400
            
        filename = secure_filename(file.filename)
        file_path = os.path.join(target_dir, filename)
        
        try:
            file.save(file_path)
            return jsonify({
                'message': 'File uploaded successfully',
                'path': os.path.relpath(file_path, base_dir),
                'name': filename,
                'size': os.path.getsize(file_path)
            })
        except Exception as e:
            return jsonify({'error': f'Failed to upload file: {str(e)}'}), 500

    @app.route('/files', methods=['DELETE'])
    def delete_file():
        """Delete a file or directory from the user's directory"""
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        path = request.args.get('path', '')
        if not path:
            return jsonify({'error': 'Path is required'}), 400
            
        # Sanitize path to prevent path traversal
        base_dir = session['home_dir']
        target_path = os.path.normpath(os.path.join(base_dir, path))
        
        # Ensure the path is within the user's home directory
        if not target_path.startswith(base_dir):
            return jsonify({'error': 'Invalid path'}), 403
        
        try:
            if not os.path.exists(target_path):
                return jsonify({'error': 'Path does not exist'}), 404
                
            if os.path.isfile(target_path):
                os.remove(target_path)
                return jsonify({'message': 'File deleted successfully'})
            else:
                shutil.rmtree(target_path)
                return jsonify({'message': 'Directory deleted successfully'})
        except Exception as e:
            return jsonify({'error': f'Failed to delete: {str(e)}'}), 500

    @app.route('/files/mkdir', methods=['POST'])
    def make_directory():
        """Create a new directory in the user's directory"""
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        data = request.json or {}
        path = data.get('path', '')
        
        # Sanitize path to prevent path traversal
        base_dir = session['home_dir']
        target_path = os.path.normpath(os.path.join(base_dir, path))
        
        # Ensure the path is within the user's home directory
        if not target_path.startswith(base_dir):
            return jsonify({'error': 'Invalid path'}), 403
        
        try:
            os.makedirs(target_path, exist_ok=True)
            return jsonify({
                'message': 'Directory created successfully',
                'path': os.path.relpath(target_path, base_dir)
            })
        except Exception as e:
            return jsonify({'error': f'Failed to create directory: {str(e)}'}), 500
