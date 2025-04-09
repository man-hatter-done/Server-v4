"""
Session and file management enhancements for the iOS Terminal server.
This module provides improved session persistence and file access security.
"""

import os
import time
import json
from functools import wraps
from flask import request, jsonify
from flask_socketio import join_room, leave_room

# Map of user IDs to their active sessions for cross-endpoint session tracking
user_sessions = {}

# Track file operations by session for improved security and debugging
file_access_log = {}

def enhance_session_management(app, socketio, sessions, session_lock, socket_sessions):
    """
    Enhance session management to improve persistence between terminal and file operations
    
    Args:
        app: Flask app instance
        socketio: SocketIO instance
        sessions: The sessions dictionary
        session_lock: Thread lock for sessions
        socket_sessions: Map of socket IDs to session IDs
    """
    
    # Original get_session function to be wrapped
    original_get_session = app.config.get('get_session', None)
    
    def enhanced_get_session(session_id, update_access=True):
        """
        Enhanced session retrieval with improved persistence and tracking
        
        Args:
            session_id: ID of the session to retrieve
            update_access: Whether to update last accessed time
            
        Returns:
            session dict or None if not found/expired
        """
        if not session_id:
            return None
            
        with session_lock:
            # Check if session exists in our main session store
            if session_id in sessions:
                session = sessions[session_id]
                if update_access:
                    # Update last accessed time
                    session['last_accessed'] = time.time()
                    
                    # Track active sessions by user ID for cross-endpoint persistence
                    if 'user_id' in session and session['user_id']:
                        user_sessions[session['user_id']] = session_id
                        
                return session
                
            # If not found, check if user has other active sessions
            session_data = request.headers.get('X-Session-Data')
            if session_data:
                try:
                    # Try to parse session data from headers
                    data = json.loads(session_data)
                    if 'userId' in data and data['userId'] in user_sessions:
                        alt_session_id = user_sessions[data['userId']]
                        if alt_session_id in sessions:
                            # Log the session redirection
                            print(f"Redirecting to alternate session {alt_session_id} for user {data['userId']}")
                            
                            # Track the redirection for security auditing
                            log_session_redirect(session_id, alt_session_id, data['userId'])
                            
                            # Return the alternate session
                            return sessions[alt_session_id]
                except:
                    # Ignore parsing errors
                    pass
                
        # Session not found anywhere
        return None
        
    # Store the enhanced function in app config for global access
    app.config['get_session'] = enhanced_get_session
    
    # If there was an original, preserve it
    if original_get_session:
        app.config['original_get_session'] = original_get_session
    
    # Enhance the WebSocket connection handler
    original_connect_handler = socketio.handlers['/']['connect']
    
    @wraps(original_connect_handler)
    def enhanced_connect_handler(*args, **kwargs):
        """Enhanced connect handler that improves session persistence"""
        # Call the original handler first
        result = original_connect_handler(*args, **kwargs)
        
        # Check for existing session ID in the connection request
        session_id = request.args.get('sessionId')
        if session_id:
            # Try to get the session
            session = enhanced_get_session(session_id)
            if session:
                # Join the session room
                join_room(session_id)
                
                # Map socket ID to session ID
                socket_sessions[request.sid] = session_id
                
                # Notify the client that their session was reconnected
                socketio.emit('session_reconnected', {
                    'sessionId': session_id,
                    'message': 'Reconnected to existing session'
                }, to=request.sid)
                
                print(f"Socket {request.sid} reconnected to session {session_id}")
                
        return result
        
    # Replace the original handler with our enhanced version
    socketio.handlers['/']['connect'] = enhanced_connect_handler
    
    # Add security middleware for file access
    @app.before_request
    def secure_file_access():
        """Ensure users can only access their own files"""
        # Only apply to file management endpoints
        if not request.path.startswith('/files/'):
            return None
            
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return None
            
        # Get the session
        session = enhanced_get_session(session_id)
        if not session:
            return None
            
        # Check if the request is trying to access a file
        path = request.args.get('path', '')
        if not path:
            return None
            
        # Get the normalized target path
        base_dir = session.get('home_dir', '')
        if not base_dir:
            return None
            
        target_path = os.path.normpath(os.path.join(base_dir, path))
        
        # Strict security: ensure path is within the user's home directory
        if not target_path.startswith(base_dir):
            return jsonify({'error': 'Access denied: path outside user directory'}), 403
            
        # Log file access for security auditing
        log_file_access(session_id, target_path, request.method)
        
        return None
        
    print("Enhanced session management initialized")
    return enhanced_get_session
    
def log_session_redirect(original_session_id, new_session_id, user_id):
    """Log session redirections for security auditing"""
    log_entry = {
        'timestamp': time.time(),
        'original_session_id': original_session_id,
        'new_session_id': new_session_id,
        'user_id': user_id
    }
    
    # In a production environment, you might want to store this in a database
    print(f"Session redirect: {original_session_id} → {new_session_id} for user {user_id}")
    
def log_file_access(session_id, path, method):
    """Log file access for security auditing"""
    if session_id not in file_access_log:
        file_access_log[session_id] = []
        
    file_access_log[session_id].append({
        'timestamp': time.time(),
        'path': path,
        'method': method
    })
    
    # Keep the log from growing too large
    if len(file_access_log[session_id]) > 100:
        file_access_log[session_id] = file_access_log[session_id][-100:]
