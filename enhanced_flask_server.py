#!/usr/bin/env python3
"""
Enhanced Flask Server for iOS Terminal
with integrated WebSocket terminal and no separate file operations endpoints.

This implementation provides a robust Linux terminal emulation with
all file operations integrated into the terminal commands.
"""

import os
import uuid
import time
import json
import sys
import signal
import threading
import logging
import eventlet
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template, make_response
from flask_cors import CORS
from flask_compress import Compress
from flask_socketio import SocketIO, emit, join_room, leave_room
from terminal_command_handler import TerminalCommandHandler
from session_manager import SessionManager
from environment_setup import EnvironmentSetup

# Use eventlet for WebSocket support
eventlet.monkey_patch()

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/flask_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("enhanced_flask_server")

# Configuration from environment variables
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
PORT = int(os.environ.get('PORT', 3000))
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))  # 1 hour in seconds
USER_DATA_DIR = os.environ.get('USER_DATA_DIR', 'user_data')
SCRIPT_DIR = os.environ.get('SCRIPT_DIR', 'user_scripts')

# Create a Flask app
app = Flask(__name__, static_folder='static')
app.config['JSON_SORT_KEYS'] = False
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # Cache static files for 1 day
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', os.urandom(24).hex())

# Enable compression
compress = Compress()
compress.init_app(app)

# Enable CORS
CORS(app, supports_credentials=True)

# Add security headers
@app.after_request
def add_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    return response

# Initialize SocketIO
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode='eventlet',
    ping_timeout=30,
    ping_interval=15
)

# Initialize core components
terminal_handler = TerminalCommandHandler()
session_manager = SessionManager(session_timeout=SESSION_TIMEOUT, user_data_dir=USER_DATA_DIR)
environment_setup = EnvironmentSetup(script_dir=SCRIPT_DIR)

# Map of active WebSocket connections to sessions
socket_sessions = {}

# =========================================================
# Documentation Routes (Preserved)
# =========================================================

@app.route('/')
def index():
    """Serve documentation page"""
    return send_file('static/index.html')

@app.route('/status')
def status_page():
    """Serve status page"""
    return send_file('static/status.html')

# =========================================================
# WebSocket Events for Terminal Communication
# =========================================================

@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    logger.debug(f"Client connected: {request.sid}")
    
    # Check for existing session ID in the connection request
    session_id = request.args.get('sessionId')
    if session_id:
        # Get the session
        session = session_manager.get_session(session_id)
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
            
            logger.debug(f"Socket {request.sid} reconnected to session {session_id}")
    
    socketio.emit('status', {'status': 'connected'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    logger.debug(f"Client disconnected: {request.sid}")
    
    # Clean up any running processes for this socket
    if request.sid in socket_sessions:
        session_id = socket_sessions[request.sid]
        terminal_handler.terminate_process(session_id)
        
        # Remove socket session mapping
        del socket_sessions[request.sid]
        logger.debug(f"Removed socket session mapping for {request.sid}")

@socketio.on('create_session')
def handle_create_session(data):
    """Create a new terminal session"""
    try:
        user_id = data.get('userId', f'socket-user-{str(uuid.uuid4())}')
        client_ip = request.remote_addr
        
        # Create a new session
        session_data = session_manager.create_session(user_id, client_ip)
        
        if 'error' in session_data:
            socketio.emit('session_created', {
                'error': session_data['error']
            }, to=request.sid)
            return
        
        session_id = session_data['sessionId']
        
        # Map socket ID to session ID
        socket_sessions[request.sid] = session_id
        
        # Join the session room
        join_room(session_id)
        
        # Return session information
        socketio.emit('session_created', session_data, to=request.sid)
        
        logger.info(f"Created session {session_id} for user {user_id}")
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        socketio.emit('session_created', {
            'error': f'Failed to create session: {str(e)}'
        }, to=request.sid)

@socketio.on('join_session')
def handle_join_session(data):
    """Join a specific session room"""
    session_id = data.get('session_id')
    if not session_id:
        socketio.emit('error', {'error': 'No session ID provided'}, to=request.sid)
        return
    
    # Get the session
    session = session_manager.get_session(session_id)
    if not session:
        socketio.emit('session_expired', {'message': 'Session expired or invalid'}, to=request.sid)
        return
    
    # Join the session room
    join_room(session_id)
    
    # Map socket ID to session ID
    socket_sessions[request.sid] = session_id
    
    logger.debug(f"Socket {request.sid} joined session {session_id}")
    socketio.emit('session_joined', {'sessionId': session_id}, to=request.sid)

@socketio.on('end_session')
def handle_end_session(data):
    """End a terminal session"""
    session_id = data.get('session_id')
    preserve_data = data.get('preserve_data', False)
    
    if not session_id:
        socketio.emit('error', {'error': 'No session ID provided'}, to=request.sid)
        return
    
    try:
        # Terminate any running processes
        terminal_handler.terminate_process(session_id)
        
        # End session
        success = session_manager.end_session(session_id, preserve_data)
        
        # Leave the session room
        leave_room(session_id)
        
        # Remove socket session mapping
        if request.sid in socket_sessions:
            del socket_sessions[request.sid]
        
        if success:
            socketio.emit('session_ended', {'message': 'Session terminated successfully'}, to=request.sid)
        else:
            socketio.emit('error', {'error': 'Failed to end session: Session not found'}, to=request.sid)
            
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        socketio.emit('error', {'error': f'Failed to end session: {str(e)}'}, to=request.sid)

@socketio.on('execute_command')
def handle_execute_command(data):
    """Execute a command in the terminal session with real-time output streaming"""
    try:
        # Validate input
        if not isinstance(data, dict):
            socketio.emit('command_error', {'error': 'Invalid command format'}, to=request.sid)
            return
            
        command = data.get('command')
        session_id = data.get('session_id')
        
        if not command or not isinstance(command, str):
            socketio.emit('command_error', {'error': 'No command provided or invalid format'}, to=request.sid)
            return
            
        if len(command) > 4096:  # Reasonable limit for command length
            socketio.emit('command_error', {'error': 'Command too long'}, to=request.sid)
            return
        
        if not session_id or not isinstance(session_id, str):
            socketio.emit('command_error', {'error': 'No session ID provided or invalid format'}, to=request.sid)
            return
        
        # Get the session
        session = session_manager.get_session(session_id)
        
        # Auto-renew session if expired
        auto_renewed = False
        if not session:
            try:
                # Create a new session
                logger.info(f"Session {session_id} expired, creating a new session")
                
                # Use socket ID as user ID for the new session
                user_id = f'socket-user-{str(uuid.uuid4())}'
                client_ip = request.remote_addr
                
                # Create a new session
                session_data = session_manager.create_session(user_id, client_ip)
                
                if 'error' in session_data:
                    socketio.emit('command_error', {
                        'error': f"Failed to create new session: {session_data['error']}"
                    }, to=request.sid)
                    return
                
                new_session_id = session_data['sessionId']
                
                # Update socket session mapping
                socket_sessions[request.sid] = new_session_id
                
                # Join the new session room
                join_room(new_session_id)
                
                # Get the new session
                session = session_manager.get_session(new_session_id)
                session_id = new_session_id
                auto_renewed = True
                
                # Notify client of session renewal
                socketio.emit('command_output', {
                    'output': f"Session expired. Created new session: {session_id[:8]}...\n",
                    'sessionRenewed': True,
                    'newSessionId': session_id
                }, to=request.sid)
                
            except Exception as e:
                logger.error(f"Error creating new session: {str(e)}")
                socketio.emit('command_error', {
                    'error': f"Failed to create new session: {str(e)}"
                }, to=request.sid)
                return
        
        # Initialize the environment if needed
        if not os.path.exists(os.path.join(session['home_dir'], '.bashrc')):
            environment_setup.setup_user_environment(session['home_dir'])
        
        # Define callback function for streaming output
        def output_callback(text, exit_code=None):
            if exit_code is not None:
                # Command completed
                socketio.emit('command_complete', {
                    'exitCode': exit_code,
                    'sessionRenewed': auto_renewed,
                    'newSessionId': session_id if auto_renewed else None
                }, to=request.sid)
            else:
                # Stream output
                socketio.emit('command_output', {'output': text}, to=request.sid)
        
        # Execute the command
        terminal_handler.execute_command(command, session_id, session, output_callback)
        
    except Exception as e:
        logger.error(f"Error handling command execution: {str(e)}")
        socketio.emit('command_error', {
            'error': f"Server error: {str(e)}"
        }, to=request.sid)

# =========================================================
# HTTP API for Terminal Communication
# =========================================================

@app.route('/create-session', methods=['POST'])
def create_session():
    """Create a new terminal session (HTTP API)"""
    try:
        data = request.json or {}
        user_id = data.get('userId', f'http-user-{str(uuid.uuid4())}')
        client_ip = request.remote_addr
        
        # Create a new session
        session_data = session_manager.create_session(user_id, client_ip)
        
        return jsonify(session_data)
        
    except Exception as e:
        logger.error(f"Error creating session: {str(e)}")
        return jsonify({'error': f'Failed to create session: {str(e)}'}), 500

@app.route('/execute-command', methods=['POST'])
def execute_command():
    """Execute a terminal command (HTTP API)"""
    try:
        # Validate inputs
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
            
        data = request.json or {}
        command = data.get('command')
        if not command:
            return jsonify({'error': 'Command is required'}), 400
        
        # Get the session
        session = session_manager.get_session(session_id)
        if not session:
            return jsonify({'error': 'Invalid or expired session'}), 401
        
        # Initialize the environment if needed
        if not os.path.exists(os.path.join(session['home_dir'], '.bashrc')):
            environment_setup.setup_user_environment(session['home_dir'])
        
        # Execute the command
        result = terminal_handler.execute_command(command, session_id, session)
        
        if 'error' in result:
            return jsonify({'error': result['error'], 'exitCode': result.get('exit_code', 1)}), 400
            
        return jsonify({
            'output': result.get('output', ''),
            'exitCode': result.get('exit_code', 0)
        })
        
    except Exception as e:
        logger.error(f"Error executing command: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

@app.route('/session', methods=['DELETE'])
def end_session_api():
    """End a terminal session (HTTP API)"""
    try:
        # Validate inputs
        session_id = request.headers.get('X-Session-Id')
        if not session_id:
            return jsonify({'error': 'Session ID is required'}), 400
        
        preserve_data = request.args.get('preserve', 'false').lower() == 'true'
        
        # End the session
        success = session_manager.end_session(session_id, preserve_data)
        
        if success:
            return jsonify({'message': 'Session ended successfully'})
        else:
            return jsonify({'error': 'Session not found'}), 404
            
    except Exception as e:
        logger.error(f"Error ending session: {str(e)}")
        return jsonify({'error': f'Server error: {str(e)}'}), 500

# =========================================================
# Error Handlers
# =========================================================

@app.errorhandler(404)
def not_found(error):
    """Handle 404 errors"""
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Endpoint not found'}), 404
    return send_file('static/index.html')

@app.errorhandler(Exception)
def handle_exception(e):
    """Global exception handler"""
    logger.error(f"Unhandled exception: {str(e)}")
    
    if request.path.startswith('/api/'):
        return jsonify({'error': 'Internal server error'}), 500
        
    return "Internal Server Error", 500

# =========================================================
# Static Routes
# =========================================================

@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)

# =========================================================
# Main Entry Point
# =========================================================

if __name__ == '__main__':
    # Create required directories
    os.makedirs(USER_DATA_DIR, exist_ok=True)
    
    # Print startup information
    logger.info(f"Starting Enhanced iOS Terminal Server on port {PORT}")
    logger.info(f"Debug mode: {DEBUG}")
    logger.info(f"Session timeout: {SESSION_TIMEOUT} seconds")
    logger.info(f"User data directory: {USER_DATA_DIR}")
    
    # Run the server
    socketio.run(
        app,
        host="0.0.0.0",
        port=PORT,
        debug=DEBUG,
        use_reloader=DEBUG
    )
