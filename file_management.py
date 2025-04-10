"""
File management API endpoints for Termux-like file access.
These endpoints provide a RESTful interface for managing files and directories.
"""

import os
import shutil
import time
import logging
from datetime import datetime
from functools import lru_cache
import sys

# Create a safe logging wrapper to prevent "logger not defined" errors
def safe_log(level, message):
    """Safely log a message without causing errors if logger isn't defined."""
    try:
        if level == 'error':
            logging.getLogger("file_management").error(message)
        elif level == 'warning':
            logging.getLogger("file_management").warning(message)
        elif level == 'info':
            logging.getLogger("file_management").info(message)
        elif level == 'debug':
            logging.getLogger("file_management").debug(message)
    except Exception as e:
        # Fallback to printing if logging fails
        print(f"LOG ({level}): {message}", file=sys.stderr)

# Create logger or use the safe wrapper
try:
    logger = logging.getLogger("file_management")
except Exception:
    # Create a dummy logger that uses safe_log
    class DummyLogger:
        def warning(self, msg): safe_log('warning', msg)
        def error(self, msg): safe_log('error', msg)
        def info(self, msg): safe_log('info', msg)
        def debug(self, msg): safe_log('debug', msg)
    
    logger = DummyLogger()
from flask import jsonify, request, send_file, make_response
from werkzeug.utils import secure_filename

# Ensure we don't have undefined logger issues
try:
    logger
except NameError:
    # Fall back to a dummy logger if the real one isn't available
    class DummyLogger:
        def warning(self, msg): print(f"WARNING: {msg}")
        def error(self, msg): print(f"ERROR: {msg}")
        def info(self, msg): print(f"INFO: {msg}")
        def debug(self, msg): pass
    
    logger = DummyLogger()

# Path cache to avoid repeated disk stats for directories that rarely change
# Keyed by (session_id, path) and stores the directory listing with a timestamp
path_cache = {}
PATH_CACHE_TIMEOUT = 10  # 10 seconds cache for directory listings
PATH_CACHE_SIZE = 100    # Maximum number of cached directory listings

@lru_cache(maxsize=100)
def get_directory_stats(dir_path, last_modified=None):
    """Get directory stats with caching based on last modification time"""
    # If last_modified is None or the directory has been changed, recalculate
    if last_modified is None or os.path.getmtime(dir_path) > last_modified:
        last_modified = os.path.getmtime(dir_path)
        item_stats = []
        for item in os.listdir(dir_path):
            item_path = os.path.join(dir_path, item)
            try:
                item_stat = os.stat(item_path)
                item_stats.append({
                    'name': item,
                    'path': item_path,
                    'is_dir': os.path.isdir(item_path),
                    'size': item_stat.st_size,
                    'modified': datetime.fromtimestamp(item_stat.st_mtime).isoformat()
                })
            except (FileNotFoundError, PermissionError):
                # Skip files that can't be accessed
                pass
        return item_stats, last_modified
    return None, last_modified

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
        start_time = time.time()
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        path = request.args.get('path', '')
        
        # Sanitize path to prevent path traversal
        base_dir = session['home_dir']
        
        # Clean the path parameter
        if path and (path.strip() == '.' or path.strip() == '..' or '/.' in path or '/..' in path):
            return jsonify({'error': 'Invalid path containing . or .. references'}), 403
            
        # Remove any null bytes which can be used in path traversal attacks
        if path and '\0' in path:
            return jsonify({'error': 'Invalid path containing null bytes'}), 403
            
        # Remove any URL encoded attacks (%2e%2e/, etc.)
        from urllib.parse import unquote
        decoded_path = unquote(path)
        if path != decoded_path:
            if '..' in decoded_path or '/.' in decoded_path:
                return jsonify({'error': 'Invalid encoded path'}), 403
        
        # Normalize path and check for directory traversal
        target_path = os.path.normpath(os.path.join(base_dir, path))
        
        # Double-check the path is within the user's home directory
        if not os.path.commonpath([target_path, base_dir]) == base_dir:
            logger.warning(f"Path traversal attempt detected: {path} -> {target_path} (outside {base_dir})")
            return jsonify({'error': 'Invalid path - directory traversal detected'}), 403
        
        try:
            if not os.path.exists(target_path):
                return jsonify({'error': 'Path does not exist'}), 404
                
            if os.path.isfile(target_path):
                return jsonify({'error': 'Path is a file, not a directory'}), 400
            
            # Check if we have a valid cached response
            cache_key = (session_id, path)
            current_time = time.time()
            
            if (cache_key in path_cache and 
                current_time - path_cache[cache_key]['timestamp'] < PATH_CACHE_TIMEOUT):
                # Use cached directory listing
                result = path_cache[cache_key]['data']
                response = jsonify(result)
                # Add performance header for debugging
                response.headers['X-Cache'] = 'HIT'
                response.headers['X-Response-Time'] = f"{(time.time() - start_time):.4f}s"
                return response
            
            # Not in cache or expired, get fresh listing
            files = []
            dir_items, last_modified = get_directory_stats(target_path, None)
            
            for item in dir_items:
                item['path'] = os.path.relpath(item['path'], base_dir)
                files.append(item)
            
            result = {
                'path': path,
                'files': files
            }
            
            # Store in cache with timestamp
            path_cache[cache_key] = {
                'data': result,
                'timestamp': current_time
            }
            
            # Keep cache size under control
            if len(path_cache) > PATH_CACHE_SIZE:
                # Remove oldest entries
                oldest = sorted(
                    path_cache.items(), 
                    key=lambda x: x[1]['timestamp']
                )[:len(path_cache) - PATH_CACHE_SIZE]
                
                for key, _ in oldest:
                    del path_cache[key]
            
            # Add performance headers
            response = jsonify(result)
            response.headers['X-Cache'] = 'MISS'
            response.headers['X-Response-Time'] = f"{(time.time() - start_time):.4f}s"
            return response
            
        except Exception as e:
            return jsonify({'error': f'Failed to list files: {str(e)}'}), 500

    # Simple cache for small files - don't cache large files
    small_file_cache = {}
    SMALL_FILE_CACHE_SIZE = 50     # Maximum number of files to cache
    SMALL_FILE_MAX_SIZE = 1024*128 # Only cache files under 128KB
    
    @app.route('/files/download', methods=['GET'])
    def download_file():
        """Download a file from the user's directory"""
        start_time = time.time()
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        session = get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        path = request.args.get('path', '')
        if not path:
            return jsonify({'error': 'Path is required'}), 400
        
        # Get content type header if any
        content_type = request.args.get('content_type', None)
            
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
            
            # Check file size for caching decision
            file_size = os.path.getsize(target_path)
            file_mtime = os.path.getmtime(target_path)
            cache_key = f"{session_id}:{path}"
            
            # For small text files, we use caching
            if file_size <= SMALL_FILE_MAX_SIZE and path.endswith(('.txt', '.md', '.json', '.yml', '.yaml', '.csv', '.log')):
                # Check if we have it cached and the mtime hasn't changed
                if (cache_key in small_file_cache and 
                    small_file_cache[cache_key]['mtime'] == file_mtime):
                    # Use cached file data
                    file_data = small_file_cache[cache_key]['data']
                    mimetype = small_file_cache[cache_key]['mimetype']
                    
                    response = make_response(file_data)
                    response.headers['Content-Type'] = mimetype
                    response.headers['Content-Disposition'] = f'attachment; filename="{os.path.basename(target_path)}"'
                    response.headers['X-Cache'] = 'HIT'
                    response.headers['X-Response-Time'] = f"{(time.time() - start_time):.4f}s"
                    return response
                
                # Not in cache or modified - read the file
                with open(target_path, 'rb') as f:
                    file_data = f.read()
                
                # Determine mime type based on extension
                mimetype = content_type or 'application/octet-stream'
                if path.endswith('.txt'):
                    mimetype = 'text/plain'
                elif path.endswith('.json'):
                    mimetype = 'application/json'
                elif path.endswith('.md'):
                    mimetype = 'text/markdown'
                elif path.endswith('.csv'):
                    mimetype = 'text/csv'
                elif path.endswith(('.yml', '.yaml')):
                    mimetype = 'application/x-yaml'
                
                # Store in cache
                small_file_cache[cache_key] = {
                    'data': file_data,
                    'mtime': file_mtime,
                    'mimetype': mimetype
                }
                
                # Trim cache if needed
                if len(small_file_cache) > SMALL_FILE_CACHE_SIZE:
                    # Remove oldest accessed entries
                    keys_to_remove = list(small_file_cache.keys())[:-SMALL_FILE_CACHE_SIZE]
                    for key in keys_to_remove:
                        del small_file_cache[key]
                
                # Return optimized response
                response = make_response(file_data)
                response.headers['Content-Type'] = mimetype
                response.headers['Content-Disposition'] = f'attachment; filename="{os.path.basename(target_path)}"'
                response.headers['X-Cache'] = 'MISS'
                response.headers['X-Response-Time'] = f"{(time.time() - start_time):.4f}s"
                return response
            
            # For larger or binary files, use the standard send_file
            response = send_file(
                target_path, 
                as_attachment=True,
                mimetype=content_type
            )
            response.headers['X-Response-Time'] = f"{(time.time() - start_time):.4f}s"
            return response
            
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
