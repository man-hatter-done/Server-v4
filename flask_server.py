import os
import uuid
import time
import json
import sys
import shutil
import signal
import subprocess
import threading
import atexit
import functools
import cachetools.func
import re
import hashlib
import logging
from datetime import datetime
from container_pool import ContainerPool
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template, make_response
from flask_cors import CORS
from flask_compress import Compress
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.security import generate_password_hash, check_password_hash
import select
import io
import eventlet
from file_management import register_file_management_endpoints

# Initialize cache before anything else
# In-memory cache for responses
response_cache = {}
response_cache_size = 1000  # Maximum cache entries
response_cache_hits = 0
response_cache_misses = 0

# Simple LRU cache for file content
file_content_cache = cachetools.func.lru_cache(maxsize=100) 

# Caching decorator for route responses
def cached_response(timeout=300):
    def decorator(f):
        @functools.wraps(f)
        def decorated_function(*args, **kwargs):
            global response_cache, response_cache_hits, response_cache_misses
            
            # Skip cache for authenticated/session routes
            if 'X-Session-Id' in request.headers or 'X-API-Key' in request.headers:
                return f(*args, **kwargs)
            
            # Create a cache key from the request path and query string
            cache_key = f"{request.path}?{request.query_string.decode('utf-8')}"
            
            # Check if we have a cached response and it's still valid
            if cache_key in response_cache:
                cached_item = response_cache[cache_key]
                if time.time() - cached_item['timestamp'] < timeout:
                    response_cache_hits += 1
                    return cached_item['response']
            
            # Cache miss - call the original function
            response_cache_misses += 1
            response = f(*args, **kwargs)
            
            # Cache the response
            response_cache[cache_key] = {
                'response': response,
                'timestamp': time.time()
            }
            
            # Limit cache size by removing oldest entries if needed
            if len(response_cache) > response_cache_size:
                # Get the oldest cache key
                oldest_key = min(response_cache.keys(), 
                                key=lambda k: response_cache[k]['timestamp'])
                # Remove it
                del response_cache[oldest_key]
            
            return response
        return decorated_function
    return decorator

# Use eventlet for WebSocket support
eventlet.monkey_patch()

# Create a Flask app with optimized settings
app = Flask(__name__, static_folder='static')
app.config['JSON_SORT_KEYS'] = False  # Faster JSON responses
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # Cache static files for 1 day
app.config['COMPRESS_ALGORITHM'] = ['gzip', 'deflate']  # Enable response compression
app.config['COMPRESS_LEVEL'] = 6  # Medium compression level - good balance between CPU and size
app.config['COMPRESS_MIN_SIZE'] = 500  # Only compress responses larger than 500 bytes
app.config['START_TIME'] = time.time()  # Track app startup time for uptime reporting
app.config['SERVER_VERSION'] = 'flask-2.0.0'  # Server version for consistent reporting
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Limit request size to 16MB
app.config['PROPAGATE_EXCEPTIONS'] = True  # Make sure exceptions are properly propagated
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'dev_key_change_in_production')  # Required for SocketIO

# Add initialization logging to help diagnose worker issues
print(f"Flask app initialization starting at {time.time()}")
print(f"Python version: {sys.version}")
print(f"System platform: {sys.platform}")

# Initialize logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("flask_server.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("flask_server")

# Initialize container pool for multi-user isolation
# These values can be overridden with environment variables
MAX_CONTAINERS = int(os.environ.get('MAX_CONTAINERS', 10))
USERS_PER_CONTAINER = int(os.environ.get('USERS_PER_CONTAINER', 20))
CONTAINER_IMAGE = os.environ.get('CONTAINER_IMAGE', 'terminal-multi-user:latest')
MULTI_CONTAINER_MODE = os.environ.get('MULTI_CONTAINER_MODE', 'false').lower() == 'true'

# Global container pool instance - only initialize if we're using containers
USE_CONTAINERS = os.environ.get('USE_CONTAINERS', 'false').lower() == 'true'
container_pool = None

if USE_CONTAINERS:
    try:
        if MULTI_CONTAINER_MODE:
            logger.info("Initializing container pool in multi-container mode...")
            logger.info(f"Will distribute users across up to {MAX_CONTAINERS} containers")
        else:
            logger.info("Initializing container pool in single-container mode...")
            logger.info("All users will share one container")
            
        container_pool = ContainerPool(
            max_containers=MAX_CONTAINERS,
            users_per_container=USERS_PER_CONTAINER,
            image_name=CONTAINER_IMAGE,
            multi_container_mode=MULTI_CONTAINER_MODE
        )
        
        container_mode = "multi-container" if MULTI_CONTAINER_MODE else "single-container"
        logger.info(f"Container pool initialized in {container_mode} mode with {USERS_PER_CONTAINER} users per container")
    except Exception as e:
        logger.error(f"Failed to initialize container pool: {str(e)}")
        logger.warning("Falling back to directory-based isolation")
else:
    logger.info("Using directory-based isolation (container mode disabled)")

try:
    import psutil
    mem = psutil.virtual_memory()
    print(f"Available memory: {mem.available / (1024*1024):.1f}MB / {mem.total / (1024*1024):.1f}MB")
except ImportError:
    print("psutil not available - skipping memory check")

# Initialize Flask-Compress for response compression
compress = Compress()
compress.init_app(app)

# Enable CORS with optimized settings
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, max_age=86400)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='eventlet', ping_timeout=30, 
                    ping_interval=15, max_http_buffer_size=1024 * 1024)
print(f"SocketIO initialized with mode: {socketio.async_mode}")

# Map of active WebSocket sessions to their corresponding terminal sessions
socket_sessions = {}

# Map of terminal session IDs to active command processes
socket_processes = {}

# Add at app startup to enable WebSocket support
import eventlet
eventlet.monkey_patch()

# Debug WebSocket connection issues
print("WebSocket support enabled with eventlet")
print(f"Current eventlet version: {eventlet.__version__}")

# Note: We'll register file management endpoints after get_session is defined

# WebSocket event handlers
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    print(f"Client connected: {request.sid}")
    
    # Check for existing session ID in the connection request
    session_id = request.args.get('sessionId')
    if session_id:
        # Try to get the session
        session = get_session(session_id)
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
    
    socketio.emit('status', {'status': 'connected'}, to=request.sid)

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    print(f"Client disconnected: {request.sid}")
    # Clean up any running processes for this socket
    if request.sid in socket_sessions:
        session_id = socket_sessions[request.sid]
        if session_id in socket_processes:
            try:
                # Terminate process
                process_info = socket_processes[session_id]
                os.killpg(os.getpgid(process_info['process'].pid), signal.SIGTERM)
                del socket_processes[session_id]
                print(f"Terminated process for session {session_id}")
            except Exception as e:
                print(f"Error terminating process: {str(e)}")
        # Remove socket session mapping
        del socket_sessions[request.sid]

@socketio.on('create_session')
def handle_create_session(data):
    """Create a new terminal session"""
    try:
        user_id = data.get('userId', f'socket-user-{str(uuid.uuid4())}')
        client_ip = request.remote_addr
        
        # Create a new session
        session_id = str(uuid.uuid4())
        home_dir = os.path.join('user_data', session_id)
        
        # Set up the user environment with necessary files
        setup_user_environment(home_dir)
        
        with session_lock:
            sessions[session_id] = {
                'user_id': user_id,
                'client_ip': client_ip,
                'created': time.time(),
                'last_accessed': time.time(),
                'home_dir': home_dir
            }
        
        # Map socket ID to session ID
        socket_sessions[request.sid] = session_id
        
        # Log activity
        log_activity('session', {
            'action': 'created_websocket',
            'session_id': session_id,
            'user_id': user_id,
            'client_ip': client_ip,
            'socket_id': request.sid
        })
        
        # Return session information
        socketio.emit('session_created', {
            'sessionId': session_id,
            'expiresIn': SESSION_TIMEOUT * 1000,  # Convert to milliseconds
            'workingDirectory': '~',
            'message': 'Session created successfully'
        }, to=request.sid)
        
    except Exception as e:
        print(f"Error creating session: {str(e)}")
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
    session = get_session(session_id)
    if not session:
        socketio.emit('session_expired', {'message': 'Session expired or invalid'}, to=request.sid)
        return
    
    # Join the session room
    join_room(session_id)
    
    # Map socket ID to session ID
    socket_sessions[request.sid] = session_id
    
    print(f"Socket {request.sid} joined session {session_id}")

@socketio.on('end_session')
def handle_end_session(data):
    """End a terminal session"""
    session_id = data.get('session_id')
    if not session_id:
        socketio.emit('error', {'error': 'No session ID provided'}, to=request.sid)
        return
    
    try:
        # Clean up any running processes
        if session_id in socket_processes:
            try:
                process_info = socket_processes[session_id]
                os.killpg(os.getpgid(process_info['process'].pid), signal.SIGTERM)
                del socket_processes[session_id]
            except Exception as e:
                print(f"Error terminating process during session end: {str(e)}")
        
        # Remove session
        with session_lock:
            if session_id in sessions:
                del sessions[session_id]
        
        # Leave the session room
        leave_room(session_id)
        
        # Remove socket session mapping
        if request.sid in socket_sessions:
            del socket_sessions[request.sid]
        
        # Log activity
        log_activity('session', {
            'action': 'ended_websocket',
            'session_id': session_id,
            'socket_id': request.sid
        })
        
        socketio.emit('session_ended', {'message': 'Session terminated successfully'}, to=request.sid)
        
    except Exception as e:
        print(f"Error ending session: {str(e)}")
        socketio.emit('error', {'error': f'Failed to end session: {str(e)}'}, to=request.sid)

@socketio.on('execute_command')
def handle_execute_command(data):
    """Execute a command in the terminal session with real-time output streaming"""
    command = data.get('command')
    session_id = data.get('session_id')
    
    if not command:
        socketio.emit('command_error', {'error': 'No command provided'}, to=request.sid)
        return
    
    if not session_id:
        socketio.emit('command_error', {'error': 'No session ID provided'}, to=request.sid)
        return
    
    # Get the session
    session = get_session(session_id)
    
    # If session expired, create a new one automatically
    auto_renewed = False
    if not session:
        try:
            # Create a new session
            print(f"Session {session_id} expired, creating a new session")
            
            # Use socket ID as user ID for the new session
            user_id = request.sid
            client_ip = request.remote_addr
            
            # Create a new session
            new_session_id = str(uuid.uuid4())
            home_dir = os.path.join('user_data', new_session_id)
            
            # Set up the user environment with necessary files
            setup_user_environment(home_dir)
            
            with session_lock:
                sessions[new_session_id] = {
                    'user_id': user_id,
                    'client_ip': client_ip,
                    'created': time.time(),
                    'last_accessed': time.time(),
                    'home_dir': home_dir
                }
            
            # Update socket session mapping
            socket_sessions[request.sid] = new_session_id
            
            # Join the new session room
            join_room(new_session_id)
            
            # Log activity
            log_activity('session', {
                'action': 'auto_renewed_websocket',
                'old_session_id': session_id,
                'new_session_id': new_session_id,
                'user_id': user_id,
                'client_ip': client_ip,
                'socket_id': request.sid
            })
            
            # Use the new session
            session_id = new_session_id
            session = sessions[session_id]
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
    
    # Reset the last_accessed time to prevent timeout during command execution
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['last_accessed'] = time.time()
    
    # If using container pool, execute the command there
    if USE_CONTAINERS and container_pool is not None:
        try:
            logger.debug(f"WebSocket: Executing command via container pool: {command}")
            
            # Define a callback function to stream output
            def output_callback(text):
                if text:
                    socketio.emit('command_output', {'output': text}, to=request.sid)
            
            # Execute the command with streaming output
            result = container_pool.execute_command_stream(
                session['user_id'], 
                command, 
                output_callback
            )
            
            # Send completion message
            socketio.emit('command_complete', {
                'exitCode': result.get('exit_code', 0),
                'sessionRenewed': auto_renewed,
                'newSessionId': session_id if auto_renewed else None
            }, to=request.sid)
            
            # If it's a command that might give container info, send it separately
            if 'container-info' in command.lower() or 'hostname' in command.lower() or 'whoami' in command.lower():
                socketio.emit('container_info', {
                    'containerId': result.get('container_id', ''),
                    'username': result.get('username', '')
                }, to=request.sid)
            
            return
            
        except Exception as e:
            logger.error(f"WebSocket: Container execution error: {str(e)}")
            # Fall back to directory-based execution
            logger.info("WebSocket: Falling back to directory-based execution")
            # Continue with execution flow below
    
    # Directory-based execution - verify the user directory exists
    if not os.path.isdir(session['home_dir']):
        try:
            os.makedirs(session['home_dir'], exist_ok=True)
            logger.info(f"Created missing user directory: {session['home_dir']}")
            # Since we had to create the directory, we should set up the environment
            setup_user_environment(session['home_dir'])
        except Exception as e:
            logger.error(f"Error creating user directory: {str(e)}")
            socketio.emit('command_error', {
                'error': f"Could not access user directory: {str(e)}"
            }, to=request.sid)
            return
    
    # Handle terminal-based editors (nano, vim, emacs, etc.)
    terminal_editors = ['nano', 'vim', 'vi', 'emacs', 'pico', 'joe', 'ed']
    for editor in terminal_editors:
        if command.strip().startswith(f"{editor} "):
            # Extract filename from command
            parts = command.strip().split()
            if len(parts) > 1:
                filename = parts[1]
                # Check if file exists, create it if it doesn't
                filepath = os.path.join(session['home_dir'], filename)
                try:
                    # Create parent directories if they don't exist
                    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                    
                    # Create the file if it doesn't exist
                    if not os.path.exists(filepath):
                        with open(filepath, 'w') as f:
                            f.write('')
                            
                    # Send message explaining that web-based editors aren't supported
                    socketio.emit('command_output', {
                        'output': f"Terminal-based editors like {editor} aren't fully supported in the web terminal.\n\n"
                                 f"The file '{filename}' has been created. You can use these alternatives:\n"
                                 f"1. Use 'cat > {filename}' to create/edit the file (Ctrl+D to save)\n"
                                 f"2. Use 'echo \"content\" > {filename}' to write to the file\n"
                                 f"3. Use 'cat {filename}' to view the file contents"
                    }, to=request.sid)
                    
                    socketio.emit('command_complete', {
                        'exitCode': 0,
                        'sessionRenewed': auto_renewed,
                        'newSessionId': session_id if auto_renewed else None
                    }, to=request.sid)
                    return
                    
                except Exception as e:
                    socketio.emit('command_error', {
                        'error': f"Failed to create file: {str(e)}",
                        'sessionRenewed': auto_renewed,
                        'newSessionId': session_id if auto_renewed else None
                    }, to=request.sid)
                    return
            else:
                socketio.emit('command_output', {
                    'output': f"Terminal-based editors like {editor} aren't fully supported in the web terminal.\n"
                             f"Please specify a filename, e.g., {editor} filename.txt"
                }, to=request.sid)
                
                socketio.emit('command_complete', {
                    'exitCode': 0,
                    'sessionRenewed': auto_renewed,
                    'newSessionId': session_id if auto_renewed else None
                }, to=request.sid)
                return
    
    # First, clean the command - remove any accidental leading $ characters from copy/paste
    cleaned_command = command.strip()
    if cleaned_command.startswith('$'):
        cleaned_command = cleaned_command[1:].strip()
        print(f"Removed leading $ from command: {cleaned_command}")
        command = cleaned_command  # Update the command for further processing
        
    # Handle Python code execution (if it looks like Python code)
    python_patterns = ['print(', 'def ', 'import ', 'for ', 'while ', 'if ', 'class ', 'from ', 
                     'with ', 'try:', 'except:', 'finally:', 'else:', 'elif ', 'lambda ',
                     'async ', 'await ', 'yield ', '"""', "'''"]
    python_functions = ['len(', 'range(', 'list(', 'dict(', 'set(', 'int(', 'str(', 'float(', 'bool(', 'tuple(']
    
    # Add more patterns to detect Python code
    is_python_code = False
    
    # Check if command starts with any Python patterns
    for pattern in python_patterns:
        if command.strip().startswith(pattern):
            is_python_code = True
            print(f"Detected Python code by pattern: {pattern}")
            break
            
    # Check for common Python functions
    if not is_python_code:
        for func in python_functions:
            if func in command:
                is_python_code = True
                print(f"Detected Python code by function: {func}")
                break
    
    # Look for Python syntax patterns if not yet detected
    if not is_python_code:
        # Check for variable assignment pattern (x = y)
        if re.search(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*.+$', command.strip()):
            is_python_code = True
            print("Detected Python code by assignment pattern")
            
        # Check for list/dict literals
        elif '[' in command and ']' in command:
            is_python_code = True
            print("Detected Python code by list/dict pattern")
            
        # Check for parentheses which might indicate function calls
        elif '(' in command and ')' in command:
            is_python_code = True
            print("Detected Python code by parentheses pattern")
    
    if is_python_code:
        # Wrap the command in python -c
        python_cmd = command.replace('"', '\\"')  # Escape double quotes
        command = f'python3 -c "{python_cmd}"'
        print(f"Executing as Python: {command}")
    
        
    # Special handling for OpenSSL commands - use our wrapper if available
    if command.strip().startswith('openssl '):
        socketio.emit('command_output', {
            'output': "Setting up OpenSSL environment...\n"
        }, to=request.sid)
        
        # Force a complete environment setup instead of just checking for existence
        try:
            # Get absolute path for home_dir
            abs_home_dir = os.path.abspath(session['home_dir'])
            print(f"OpenSSL command - ensuring environment in: {abs_home_dir}")
            
            # Let the user know we're working on it
            socketio.emit('command_output', {
                'output': f"Preparing environment for OpenSSL...\n"
            }, to=request.sid)
            
            # Run the setup with robust error handling
            setup_result = setup_user_environment(abs_home_dir)
            if not setup_result and setup_result is not None:  # Only if it explicitly failed (returned False)
                socketio.emit('command_error', {
                    'error': f"Failed to set up user environment. Please try again in a moment.",
                    'sessionRenewed': auto_renewed,
                    'newSessionId': session_id if auto_renewed else None
                }, to=request.sid)
                return
                
            # Find and prepare the OpenSSL wrapper with all possible methods
            local_bin_dir = os.path.join(abs_home_dir, '.local', 'bin')
            openssl_wrapper = os.path.join(local_bin_dir, 'openssl-wrapper')
            source_wrapper = os.path.join('user_scripts', 'openssl-wrapper')
            abs_source_wrapper = os.path.abspath(source_wrapper)
            
            # Extra diagnostic logging
            print(f"OpenSSL wrapper paths:")
            print(f"  Target: {openssl_wrapper}")
            print(f"  Source: {source_wrapper}")
            print(f"  Abs source: {abs_source_wrapper}")
            
            # Try multiple paths for the source wrapper
            wrapper_source_paths = [
                source_wrapper,
                abs_source_wrapper,
                '/app/user_scripts/openssl-wrapper',
                os.path.join(os.getcwd(), 'user_scripts', 'openssl-wrapper')
            ]
            
            wrapper_found = False
            # Check all possible source paths
            for src_path in wrapper_source_paths:
                if os.path.exists(src_path):
                    print(f"Found source wrapper at: {src_path}")
                    wrapper_found = True
                    # Try all copy methods with this source
                    try:
                        # Method 1: Direct file read/write
                        with open(src_path, 'rb') as src:
                            wrapper_content = src.read()
                            with open(openssl_wrapper, 'wb') as dst:
                                dst.write(wrapper_content)
                        os.chmod(openssl_wrapper, 0o777)
                        print(f"Successfully copied wrapper script (Method 1)")
                        break  # Successfully copied
                    except Exception as copy_error:
                        print(f"Method 1 failed: {str(copy_error)}")
                        try:
                            # Method 2: shutil
                            shutil.copy2(src_path, openssl_wrapper)
                            os.chmod(openssl_wrapper, 0o777)
                            print(f"Successfully copied wrapper script (Method 2)")
                            break
                        except Exception as copy_error:
                            print(f"Method 2 failed: {str(copy_error)}")
                            try:
                                # Method 3: Shell command
                                subprocess.run(["cp", src_path, openssl_wrapper], check=True)
                                subprocess.run(["chmod", "777", openssl_wrapper], check=False)
                                print(f"Successfully copied wrapper script (Method 3)")
                                break
                            except Exception as copy_error:
                                print(f"All wrapper copy methods failed: {str(copy_error)}")
            
            if not wrapper_found:
                print(f"ERROR: OpenSSL wrapper source was not found in any location!")
                # List current directory contents
                try:
                    print(f"Current directory: {os.getcwd()}")
                    print(f"Contents: {os.listdir('.')}")
                    if os.path.exists('user_scripts'):
                        print(f"user_scripts contents: {os.listdir('user_scripts')}")
                except Exception as e:
                    print(f"Error listing directories: {str(e)}")
                
                socketio.emit('command_output', {
                    'output': "Warning: OpenSSL wrapper script not found. Using direct OpenSSL command.\n"
                }, to=request.sid)
            
            # Verify the wrapper exists and is executable with extensive diagnostics
            wrapper_status = "Not found"
            if os.path.exists(openssl_wrapper):
                if os.access(openssl_wrapper, os.X_OK):
                    wrapper_status = "Found and executable"
                else:
                    wrapper_status = "Found but not executable"
                    # Try to fix permissions again
                    try:
                        os.chmod(openssl_wrapper, 0o777)
                        subprocess.run(["chmod", "777", openssl_wrapper], check=False)
                        wrapper_status = "Permissions fixed"
                    except Exception as e:
                        print(f"Failed to fix permissions: {str(e)}")
            
            print(f"OpenSSL wrapper status: {wrapper_status}")
            
            # Now handle the actual command execution
            if os.path.exists(openssl_wrapper) and os.access(openssl_wrapper, os.X_OK):
                # Extract the openssl subcommand and arguments
                openssl_parts = command.strip().split(' ')
                if len(openssl_parts) > 1:
                    openssl_cmd = ' '.join(openssl_parts[1:])
                    # Use full path to wrapper and specify bash directly to avoid PATH issues
                    command = f"/bin/bash {openssl_wrapper} {openssl_cmd}"
                    print(f"Using OpenSSL wrapper: {command}")
                    socketio.emit('command_output', {
                        'output': "Using enhanced OpenSSL wrapper script...\n"
                    }, to=request.sid)
            else:
                # Fallback to direct execution with preset passphrase for OpenSSL
                print(f"Using direct openssl command (wrapper not available at {openssl_wrapper})")
                socketio.emit('command_output', {
                    'output': "Notice: Using direct OpenSSL command without wrapper.\n"
                }, to=request.sid)
                
        except Exception as e:
            print(f"Critical error in OpenSSL setup: {str(e)}")
            socketio.emit('command_error', {
                'error': f"Error setting up OpenSSL environment: {str(e)}",
                'sessionRenewed': auto_renewed,
                'newSessionId': session_id if auto_renewed else None
            }, to=request.sid)
            return

        
        # Ensure user .local/bin directory exists
        local_bin_dir = os.path.join(session['home_dir'], '.local', 'bin')
        try:
            os.makedirs(local_bin_dir, exist_ok=True)
            os.chmod(local_bin_dir, 0o755)  # Make sure directory is accessible
        except Exception as e:
            print(f"Error creating .local/bin directory: {str(e)}")
            socketio.emit('command_error', {
                'error': f"Could not create necessary directories: {str(e)}",
                'sessionRenewed': auto_renewed,
                'newSessionId': session_id if auto_renewed else None
            }, to=request.sid)
            return
        
        # Check local user openssl-wrapper
        openssl_wrapper = os.path.join(local_bin_dir, 'openssl-wrapper')
        
        # If wrapper doesn't exist or is not executable, copy it from source script dir
        if not os.path.exists(openssl_wrapper) or not os.access(openssl_wrapper, os.X_OK):
            try:
                # Copy the script from the source location
                source_wrapper = os.path.join('user_scripts', 'openssl-wrapper')
                if os.path.exists(source_wrapper):
                    shutil.copy2(source_wrapper, openssl_wrapper)
                    os.chmod(openssl_wrapper, 0o755)
                    print(f"Copied openssl-wrapper to {openssl_wrapper}")
                else:
                    print(f"Source openssl-wrapper not found at {source_wrapper}")
                    socketio.emit('command_output', {
                        'output': "Warning: OpenSSL wrapper script not found. Using direct OpenSSL command."
                    }, to=request.sid)
            except Exception as e:
                print(f"Failed to copy openssl-wrapper: {str(e)}")
                socketio.emit('command_output', {
                    'output': f"Warning: Could not set up OpenSSL wrapper: {str(e)}\nWill try to use direct command."
                }, to=request.sid)

        # Now check if the wrapper exists and use it if possible
        if os.path.exists(openssl_wrapper) and os.access(openssl_wrapper, os.X_OK):
            # Extract the openssl subcommand and arguments
            openssl_parts = command.strip().split(' ')
            if len(openssl_parts) > 1:
                openssl_cmd = ' '.join(openssl_parts[1:])
                # Use full path to wrapper and specify bash directly to avoid PATH issues
                command = f"/bin/bash {openssl_wrapper} {openssl_cmd}"
                print(f"Using OpenSSL wrapper: {command}")
        else:
            # Fallback to direct execution with preset passphrase for OpenSSL
            print(f"Using direct openssl command (wrapper not available at {openssl_wrapper})")
            socketio.emit('command_output', {
                'output': "Notice: Using direct OpenSSL command without wrapper."
            }, to=request.sid)
    
    # Add environment variables to help user-level installations
    env = os.environ.copy()
    env['HOME'] = session['home_dir']  
    env['PYTHONUSERBASE'] = os.path.join(session['home_dir'], '.local')
    env['PATH'] = os.path.join(session['home_dir'], '.local', 'bin') + ':' + env.get('PATH', '')
    env['USER'] = 'terminal-user'  # Provide a username for commands that need it
    env['OPENSSL_PASSPHRASE'] = 'termux_secure_passphrase'  # Default passphrase for OpenSSL operations
    
    # Source .profile instead of just .bashrc to get all environment variables
    profile_path = os.path.join(session['home_dir'], '.profile')
    if os.path.exists(profile_path):
        source_cmd = f"source {profile_path}"
    else:
        source_cmd = "source .bashrc 2>/dev/null || true"
    
    # Execute command with bash to ensure profile or bashrc is sourced
    full_command = f'cd {session["home_dir"]} && {source_cmd}; {command}'
    
    try:
        # Track if we need to update working directory
        update_working_dir = command.strip() == 'pwd' or command.strip().startswith('cd ')
        
        # Start process in its own process group with stdout and stderr piped
        process = subprocess.Popen(
            full_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,  # Line buffered
            cwd=session['home_dir'],
            env=env,
            preexec_fn=os.setsid  # Create new process group
        )
        
        # Store process information
        socket_processes[session_id] = {
            'process': process,
            'start_time': time.time()
        }
        
        # Stream output in a separate thread to avoid blocking
        def stream_output():
            try:
                # File descriptors for select
                fd_stdout = process.stdout.fileno()
                fd_stderr = process.stderr.fileno()
                readable = [fd_stdout, fd_stderr]
                
                # Buffer for output
                stdout_buffer = ""
                stderr_buffer = ""
                
                # Stream output while process is running
                while process.poll() is None:
                    # Check for available output using select with timeout
                    ready, _, _ = select.select(readable, [], [], 0.1)
                    
                    if fd_stdout in ready:
                        output = os.read(fd_stdout, 1024).decode('utf-8', errors='replace')
                        if output:
                            # Emit output to client
                            socketio.emit('command_output', {'output': output}, to=request.sid)
                            stdout_buffer += output
                    
                    if fd_stderr in ready:
                        error = os.read(fd_stderr, 1024).decode('utf-8', errors='replace')
                        if error:
                            # Emit error to client
                            socketio.emit('command_output', {'output': error}, to=request.sid)
                            stderr_buffer += error
                
                # Get any remaining output
                stdout_remainder = process.stdout.read()
                if stdout_remainder:
                    socketio.emit('command_output', {'output': stdout_remainder}, to=request.sid)
                    stdout_buffer += stdout_remainder
                
                stderr_remainder = process.stderr.read()
                if stderr_remainder:
                    socketio.emit('command_output', {'output': stderr_remainder}, to=request.sid)
                    stderr_buffer += stderr_remainder
                
                # Process finished
                exit_code = process.wait()
                
                # Clean up process tracking
                if session_id in socket_processes:
                    del socket_processes[session_id]
                
                # Update working directory if needed
                if update_working_dir and exit_code == 0:
                    try:
                        if command.strip() == 'pwd':
                            # Extract working directory from output
                            if stdout_buffer:
                                working_dir = stdout_buffer.strip()
                                socketio.emit('working_directory', {'path': working_dir}, to=request.sid)
                        elif command.strip().startswith('cd '):
                            # Get working directory after cd command
                            pwd_process = subprocess.Popen(
                                f'cd {session["home_dir"]} && {source_cmd}; pwd',
                                shell=True,
                                stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE,
                                text=True,
                                cwd=session['home_dir'],
                                env=env
                            )
                            pwd_output, _ = pwd_process.communicate(timeout=5)
                            if pwd_output:
                                working_dir = pwd_output.strip()
                                socketio.emit('working_directory', {'path': working_dir}, to=request.sid)
                    except Exception as e:
                        print(f"Error updating working directory: {str(e)}")
                
                # Send command completion event
                socketio.emit('command_complete', {
                    'exitCode': exit_code,
                    'sessionRenewed': auto_renewed,
                    'newSessionId': session_id if auto_renewed else None,
                    'workingDirectory': None  # Would be set by working_directory event
                }, to=request.sid)
                
            except Exception as e:
                print(f"Error in stream_output thread: {str(e)}")
                socketio.emit('command_error', {
                    'error': f"Error streaming command output: {str(e)}",
                    'sessionRenewed': auto_renewed,
                    'newSessionId': session_id if auto_renewed else None
                }, to=request.sid)
        
        # Start output streaming in a separate thread
        threading.Thread(target=stream_output, daemon=True).start()
        
    except Exception as e:
        print(f"Error executing command: {str(e)}")
        socketio.emit('command_error', {
            'error': f"Failed to execute command: {str(e)}",
            'sessionRenewed': auto_renewed,
            'newSessionId': session_id if auto_renewed else None
        }, to=request.sid)

# Route to serve WebSocket terminal page
@app.route('/ws')
@cached_response(timeout=3600)  # Cache for 1 hour
def websocket_terminal():
    """Serve WebSocket terminal interface"""
    return send_file('static/socket-terminal.html')

# Function to get file contents with caching
@file_content_cache
def get_cached_file_content(file_path):
    """Get file content with caching for frequently accessed files"""
    with open(file_path, 'rb') as f:
        return f.read()

# Configuration
DEBUG = os.environ.get('DEBUG', 'False').lower() == 'true'
PORT = int(os.environ.get('PORT', 3000))
SESSION_TIMEOUT = int(os.environ.get('SESSION_TIMEOUT', 3600))  # 1 hour in seconds
USE_AUTH = os.environ.get('USE_AUTH', 'False').lower() == 'true'
API_KEY = os.environ.get('API_KEY', 'change-this-in-production')
COMMAND_TIMEOUT = int(os.environ.get('COMMAND_TIMEOUT', 300))  # 5 minutes in seconds
ENABLE_SYSTEM_COMMANDS = os.environ.get('ENABLE_SYSTEM_COMMANDS', 'True').lower() == 'true'

# Session pool configuration from environment
SESSION_POOL_SIZE = int(os.environ.get('SESSION_POOL_SIZE', 10))
MAX_POOL_AGE = int(os.environ.get('MAX_POOL_AGE', 1800))  # 30 minutes in seconds

# Create required directories
os.makedirs('logs', exist_ok=True)
os.makedirs('user_data', exist_ok=True)

# Setup memory monitor to prevent OOM killer
def monitor_memory_usage():
    """
    Monitor memory usage and take action if it gets too high
    This runs in a background thread to prevent OOM killer
    """
    import gc
    import time
    import psutil
    import logging
    
    logging.basicConfig(
        filename='logs/memory_monitor.log',
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    
    # Configure thresholds
    WARNING_THRESHOLD = 70  # Percent
    CRITICAL_THRESHOLD = 85  # Percent
    EMERGENCY_THRESHOLD = 95  # Percent
    CHECK_INTERVAL = 15  # Seconds - reduced interval for faster response
    
    # Track worker process ID for logging
    worker_pid = os.getpid()
    
    logging.info(f"Memory monitor started for worker {worker_pid}")
    print(f"Memory monitor starting for worker {worker_pid}")
    
    # Record startup memory usage as baseline
    try:
        process = psutil.Process(worker_pid)
        startup_mem = process.memory_info().rss / (1024 * 1024)
        logging.info(f"Initial memory usage: {startup_mem:.1f} MB")
        print(f"Initial memory usage: {startup_mem:.1f} MB")
    except Exception as e:
        logging.error(f"Error getting baseline memory: {str(e)}")
    
    while True:
        try:
            # Get current memory usage
            process = psutil.Process(worker_pid)
            mem_info = process.memory_info()
            mem_percent = process.memory_percent()
            mem_mb = mem_info.rss / (1024 * 1024)
            
            # Always log status for debugging worker failures
            logging.info(f"Memory usage: {mem_percent:.1f}% ({mem_mb:.1f} MB)")
            
            # Warning level - run garbage collection
            if mem_percent > WARNING_THRESHOLD:
                logging.warning(f"Worker {worker_pid} high memory usage: {mem_percent:.1f}% ({mem_mb:.1f} MB)")
                logging.info("Running garbage collection")
                gc.collect()
                
                # Log memory after GC
                gc_mem = psutil.Process(worker_pid).memory_info().rss / (1024 * 1024)
                logging.info(f"Memory after GC: {gc_mem:.1f} MB (saved {mem_mb - gc_mem:.1f} MB)")
            
            # Critical level - release caches
            if mem_percent > CRITICAL_THRESHOLD:
                logging.warning(f"Worker {worker_pid} critical memory usage - releasing caches")
                # Clear file content cache
                file_content_cache.cache_clear()
                # Clear response cache
                response_cache.clear()
                # Reset script cache
                script_cache.clear()
                # Force garbage collection
                gc.collect()
                
                # Log memory after cache clearing
                cache_clear_mem = psutil.Process(worker_pid).memory_info().rss / (1024 * 1024)
                logging.info(f"Memory after cache clearing: {cache_clear_mem:.1f} MB (saved {mem_mb - cache_clear_mem:.1f} MB)")
            
            # Emergency level - take drastic action
            if mem_percent > EMERGENCY_THRESHOLD:
                logging.error(f"Worker {worker_pid} emergency memory usage - removing expired sessions")
                # Remove expired sessions
                with session_lock:
                    current_time = time.time()
                    expired_sessions = []
                    
                    # Find expired or old sessions
                    for session_id, session in sessions.items():
                        if current_time - session['last_accessed'] > SESSION_TIMEOUT / 2:
                            expired_sessions.append(session_id)
                    
                    # Remove expired sessions
                    for session_id in expired_sessions:
                        terminate_process(session_id)
                        del sessions[session_id]
                        logging.info(f"Removed session {session_id} to save memory")
                
                # Force garbage collection again
                gc.collect()
                
                # Final memory check
                final_mem = psutil.Process(worker_pid).memory_info().rss / (1024 * 1024)
                logging.info(f"Memory after emergency actions: {final_mem:.1f} MB (saved {mem_mb - final_mem:.1f} MB)")
        
        except Exception as e:
            logging.error(f"Memory monitor error in worker {worker_pid}: {str(e)}")
        
        # Sleep before next check
        time.sleep(CHECK_INTERVAL)

# Start memory monitor in background thread
try:
    import psutil
    # Print memory info before starting monitor to help diagnose worker failures
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    print(f"Worker {os.getpid()} starting with {mem_info.rss / (1024 * 1024):.1f} MB memory usage")
    
    memory_monitor_thread = threading.Thread(target=monitor_memory_usage, daemon=True)
    memory_monitor_thread.start()
except ImportError:
    print("Warning: psutil not installed. Memory monitoring disabled.")
except Exception as e:
    print(f"Failed to start memory monitor: {str(e)}")
    # Continue without memory monitoring

# Session storage
sessions = {}
running_processes = {}  # Stores active subprocesses by session_id
session_lock = threading.Lock()

# Initialize session pool for pre-creating sessions
session_pool = []
session_pool_lock = threading.Lock()
pool_initialization_in_progress = False


def log_activity(log_type, data):
    """Log activity to a file"""
    log_file = os.path.join('logs', f"{log_type}.log")
    timestamp = datetime.now().isoformat()
    log_entry = {
        'timestamp': timestamp,
        **data
    }
    
    with open(log_file, 'a') as f:
        f.write(json.dumps(log_entry) + '\n')


# Templates for fast file creation
BASHRC_TEMPLATE = """
# Auto-activate Python virtual environment
if [ -d "$HOME/venv" ] ; then
    source "$HOME/venv/bin/activate"
fi

# Set up environment variables
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUSERBASE="$HOME/.local"

# Set prompt
export PS1="\\[\\033[01;32m\\]\\u@terminal\\[\\033[00m\\]:\\[\\033[01;34m\\]\\w\\[\\033[00m\\]\\$ "

# Aliases
alias ll='ls -la'
alias python=python3

# Helper functions
pip-user() {
    pip install --user "$@"
}

apt-get() {
    echo "System apt-get is disabled. Use pip-user for Python packages."
    echo "Example: pip-user numpy pandas requests"
    return 1
}

apt() {
    echo "System apt is disabled. Use pip-user for Python packages."
    echo "Example: pip-user numpy pandas requests"
    return 1
}

# Display welcome message on login
echo "iOS Terminal - Type 'help' for available commands"
echo "For package installation, use: pip-user PACKAGE_NAME"
"""

HELP_TEMPLATE = """iOS Terminal Help
===============

Package Installation
-------------------
- Install Python packages:  pip-user PACKAGE_NAME
- Update pip:              pip-user --upgrade pip
- Install NodeJS packages: npm install -g PACKAGE_NAME
- Install Ruby gems:       gem install --user-install PACKAGE_NAME

Command Examples
---------------
- File management:         ls, cp, mv, rm, mkdir, cat, nano, vim
- Network tools:           curl, wget, netstat, ping
- Process management:      ps, kill, top
- Python development:      python, pip-user
- Web development:         node, npm
- Version control:         git clone, git pull, git push

Special Commands
---------------
- help                     Display this help message
- install-python           Set up Python environment
- install-node             Set up NodeJS environment

Tips
----
- Your files are preserved between sessions
- Python packages are installed in your user space
- Use .local/bin for your custom executables
- The virtual environment is auto-activated
- Long-running commands will continue in background
"""

# Cache for faster session creation
script_cache = {}

def setup_user_environment(home_dir):
    """Set up a user environment with necessary files and directories - optimized for speed and reliability"""
    start_time = time.time()
    success = False
    
    # Ensure parent directory (user_data) exists and has proper permissions
    parent_dir = os.path.dirname(os.path.abspath(home_dir))
    try:
        os.makedirs(parent_dir, exist_ok=True)
        os.chmod(parent_dir, 0o777)  # Make parent directory fully writable
        print(f"Ensured parent directory exists with proper permissions: {parent_dir}")
    except Exception as e:
        print(f"Warning: Could not set up parent directory: {str(e)}")
        # Continue anyway as the directory might already exist
    
    # Ensure home_dir is absolute path
    if not home_dir.startswith('/'):
        print(f"WARN: Received relative path for home_dir: {home_dir}")
        abs_home_dir = os.path.abspath(home_dir)
        print(f"Converting relative path {home_dir} to absolute path {abs_home_dir}")
        home_dir = abs_home_dir
    
    try:
        print(f"Setting up user environment in {home_dir} (Process ID: {os.getpid()}, User: {os.getuid()}, Group: {os.getgid()})")
        
        # Try to create the directory if it doesn't exist, with multiple methods for robustness
        if not os.path.exists(home_dir):
            try:
                print(f"Creating directory {home_dir} with os.makedirs")
                os.makedirs(home_dir, exist_ok=True)
            except Exception as e:
                print(f"Warning: Could not create directory with os.makedirs: {str(e)}")
                try:
                    # Try shell command as fallback
                    print(f"Trying mkdir -p as fallback")
                    subprocess.run(["mkdir", "-p", home_dir], check=True)
                except Exception as e2:
                    print(f"ERROR: Both directory creation methods failed: {str(e2)}")
                    return False
        
        # Verify the directory exists now
        if not os.path.exists(home_dir):
            print(f"ERROR: Directory {home_dir} still does not exist after creation attempts")
            # Try one more desperate measure - create parent directories one by one
            try:
                parent_dir = os.path.dirname(home_dir)
                if not os.path.exists(parent_dir):
                    print(f"Creating parent directory {parent_dir}")
                    os.makedirs(parent_dir, exist_ok=True)
                print(f"Creating directory {home_dir} directly")
                os.mkdir(home_dir)
            except Exception as e:
                print(f"FATAL: Could not create directory {home_dir}: {str(e)}")
                return False
        
        # Fix permissions - ensure all users can access the directory
        try:
            # Make directory and all subdirectories accessible
            print(f"Setting permissions on {home_dir}")
            os.chmod(home_dir, 0o777)  # More permissive for debugging
            # Try a shell command as well for extra assurance
            subprocess.run(["chmod", "777", home_dir], check=False)
        except Exception as e:
            print(f"Warning: Could not set permissions for {home_dir}: {str(e)}")
        
        # Create all required directories at once
        dirs_to_create = [
            os.path.join(home_dir, 'projects'),
            os.path.join(home_dir, 'downloads'),
            os.path.join(home_dir, '.local', 'bin'),
            os.path.join(home_dir, '.config'),
            os.path.join(home_dir, '.ssl'),
            os.path.join(home_dir, '.pkg'),
            os.path.join(home_dir, '.fifo'),  # For interactive commands
        ]
        
        # Create all required directories with robust error handling
        for directory in dirs_to_create:
            try:
                print(f"Creating directory: {directory}")
                os.makedirs(directory, exist_ok=True)
                
                # Set proper permissions and check if successful
                try:
                    os.chmod(directory, 0o777)  # More permissive for debugging
                    # Also try shell chmod for maximum compatibility
                    subprocess.run(["chmod", "-R", "777", directory], check=False)
                    
                    # Verify directory exists and is writable
                    if not os.path.exists(directory):
                        print(f"WARNING: Directory {directory} does not exist after creation!")
                    elif not os.access(directory, os.W_OK):
                        print(f"WARNING: Directory {directory} is not writable!")
                    else:
                        print(f"Successfully created and set permissions for {directory}")
                except Exception as e:
                    print(f"Warning: Permission setting failed for {directory}: {str(e)}")
            except Exception as e:
                print(f"ERROR: Failed to create directory {directory}: {str(e)}")
                # Try the shell command as a fallback
                try:
                    subprocess.run(["mkdir", "-p", directory], check=True)
                    subprocess.run(["chmod", "777", directory], check=False)
                    print(f"Created directory {directory} using shell fallback")
                except Exception as e2:
                    print(f"CRITICAL: Both methods failed for {directory}: {str(e2)}")
                    # Continue attempting with other directories
        
        # Write template files quickly - use try/except for each operation
        user_bin_dir = os.path.join(home_dir, '.local', 'bin')
        bashrc_path = os.path.join(home_dir, '.bashrc')
        help_path = os.path.join(home_dir, 'help.txt')
        profile_path = os.path.join(home_dir, '.profile')
        
        # Parallel writing of files with comprehensive error handling
        file_writing_tasks = [
            (bashrc_path, BASHRC_TEMPLATE),
            (help_path, HELP_TEMPLATE)
        ]
        
        # Write files if they don't exist
        for file_path, content in file_writing_tasks:
            try:
                if not os.path.exists(file_path):
                    with open(file_path, 'w') as f:
                        f.write(content)
            except Exception as e:
                print(f"Warning: Could not write to {file_path}: {str(e)}")
        
        # Setup enhanced profile file for better environment with locale fixes
        try:
            with open(profile_path, 'w') as f:
                f.write("""
# Add local bin directory to PATH
export PATH="$HOME/.local/bin:$PATH"

# Set environment variables for better compatibility with fallbacks for locale
export LANG=C.UTF-8 2>/dev/null || export LANG=C
# Don't set LC_ALL directly as it may cause warnings
# export LC_ALL=en_US.UTF-8
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export TERM=xterm-256color

# Setup for interactive commands
export INTERACTIVE_COMMAND_SUPPORT=1

# Setup for OpenSSL
export OPENSSL_PASSPHRASE="termux_secure_passphrase"

# Source .bashrc if it exists
if [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi
""")
            print(f"Created profile with C.UTF-8 locale to avoid warnings")
        except Exception as e:
            print(f"Warning: Could not write profile file: {str(e)}")
        
        # Copy all user scripts for better functionality with robust error handling
        scripts_dir = 'user_scripts'
        abs_scripts_dir = os.path.abspath(scripts_dir)
        print(f"Copying scripts from {abs_scripts_dir} to {user_bin_dir}")
        
        # First ensure the user_bin_dir exists (extra check)
        if not os.path.exists(user_bin_dir):
            try:
                print(f"Re-creating user bin dir: {user_bin_dir}")
                os.makedirs(user_bin_dir, exist_ok=True)
                os.chmod(user_bin_dir, 0o777)
            except Exception as e:
                print(f"CRITICAL: Could not create bin directory: {str(e)}")
                # Try shell commands as fallback
                try:
                    subprocess.run(["mkdir", "-p", user_bin_dir], check=True)
                    subprocess.run(["chmod", "777", user_bin_dir], check=False)
                except Exception as e2:
                    print(f"FATAL: Bin directory creation completely failed: {str(e2)}")
                    return False
        
        # Verify the scripts source directory exists - try multiple locations
        if not os.path.exists(scripts_dir):
            print(f"Scripts directory not found at {scripts_dir}, trying alternatives")
            
            # Try multiple possible locations for user_scripts
            potential_paths = [
                abs_scripts_dir,
                '/app/user_scripts',
                os.path.join(os.getcwd(), 'user_scripts'),
                os.path.join(os.path.dirname(os.getcwd()), 'user_scripts'),
                '/user_scripts',
                os.path.join(os.path.dirname(os.path.dirname(home_dir)), 'user_scripts')
            ]
            
            scripts_dir_found = False
            for path in potential_paths:
                if os.path.exists(path) and os.path.isdir(path):
                    scripts_dir = path
                    print(f"Found scripts at alternative location: {scripts_dir}")
                    scripts_dir_found = True
                    break
            
            if not scripts_dir_found:
                print(f"ERROR: Could not find scripts directory in any location")
                # Try listing directories in current path for debugging
                try:
                    print(f"Searched paths: {potential_paths}")
                    print(f"Current directory: {os.getcwd()}")
                    print(f"Contents: {os.listdir('.')}")
                except Exception as e:
                    print(f"Error listing directory: {str(e)}")
                return False
        
        # Now copy all scripts with extensive error handling
        script_files = []
        try:
            script_files = os.listdir(scripts_dir)
            print(f"Found {len(script_files)} script files in {scripts_dir}")
        except Exception as e:
            print(f"ERROR: Could not list scripts directory: {str(e)}")
            return False
            
        # If no scripts found, try additional error handling
        if not script_files:
            print(f"Warning: No script files found in {scripts_dir}")
            # Try listing with subprocess as a fallback
            try:
                output = subprocess.check_output(["ls", "-l", scripts_dir], text=True)
                print(f"Shell ls output: {output}")
            except Exception as e:
                print(f"Shell listing failed: {str(e)}")
            return False
        
        # Copy each script file with multiple fallback methods
        successful_copies = 0
        failed_copies = 0
        
        for script_file in script_files:
            try:
                script_path = os.path.join(scripts_dir, script_file)
                if os.path.isfile(script_path):
                    dest_path = os.path.join(user_bin_dir, script_file)
                    print(f"Copying script: {script_path} -> {dest_path}")
                    
                    # Try multiple copy methods
                    copy_success = False
                    
                    # Method 1: Try direct file read/write
                    try:
                        with open(script_path, 'rb') as src:
                            script_content = src.read()
                            # Create parent directories if needed
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            with open(dest_path, 'wb') as dst:
                                dst.write(script_content)
                            os.chmod(dest_path, 0o777)  # Make it fully executable
                            copy_success = True
                            print(f"✓ Successfully copied {script_file} (Method 1)")
                    except Exception as copy_error:
                        print(f"Method 1 failed: {str(copy_error)}")
                    
                    # Method 2: Try shutil if method 1 failed
                    if not copy_success:
                        try:
                            # Create parent directories if needed
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            shutil.copy2(script_path, dest_path)
                            os.chmod(dest_path, 0o777)  # Make it fully executable
                            copy_success = True
                            print(f"✓ Successfully copied {script_file} (Method 2)")
                        except Exception as copy_error:
                            print(f"Method 2 failed: {str(copy_error)}")
                    
                    # Method 3: Shell cp command as last resort
                    if not copy_success:
                        try:
                            # Create parent directory if needed
                            os.makedirs(os.path.dirname(dest_path), exist_ok=True)
                            # Try using cp with subprocess
                            cp_result = subprocess.run(["cp", script_path, dest_path], 
                                                     stderr=subprocess.PIPE, 
                                                     text=True, 
                                                     check=False)
                            if cp_result.returncode != 0:
                                print(f"cp error: {cp_result.stderr}")
                                # Try one more approach using cat
                                subprocess.run(f"cat '{script_path}' > '{dest_path}'", shell=True, check=True)
                            subprocess.run(["chmod", "777", dest_path], check=False)
                            copy_success = True
                            print(f"✓ Successfully copied {script_file} (Method 3)")
                        except Exception as copy_error:
                            print(f"Method 3 failed: {str(copy_error)}")
                    
                    # Check if any method succeeded
                    if not copy_success:
                        print(f"CRITICAL: All methods failed to copy {script_file}")
                        failed_copies += 1
                    else:
                        successful_copies += 1
                        # Verify the file exists and is executable
                        if not os.path.exists(dest_path):
                            print(f"ERROR: File does not exist after copy: {dest_path}")
                        elif not os.access(dest_path, os.X_OK):
                            print(f"ERROR: File is not executable after copy: {dest_path}")
                            try:
                                # Try again to make it executable with multiple methods
                                os.chmod(dest_path, 0o777)
                                subprocess.run(["chmod", "777", dest_path], check=False)
                                print(f"Fixed permissions for {script_file}")
                            except Exception as perm_error:
                                print(f"Failed to fix permissions: {str(perm_error)}")
            except Exception as e:
                print(f"Warning: Failed to process script {script_file}: {str(e)}")
                failed_copies += 1
                
        print(f"Script copying summary: {successful_copies} successful, {failed_copies} failed")
        
        # Set up enhanced environment using our new script if available
        setup_script = os.path.join(user_bin_dir, 'setup-enhanced-environment')
        source_script_path = os.path.join(os.getcwd(), scripts_dir, 'setup-enhanced-environment')
        
        # Use absolute paths to avoid relative path issues
        if os.path.isfile(source_script_path):
            # First, ensure the source script has execute permissions
            try:
                os.chmod(source_script_path, 0o755)
            except Exception as e:
                print(f"Warning: Could not set execute permission on source script: {str(e)}")
                
            # Now handle the target script setup
            try:
                # Make a copy instead of a symlink to avoid path issues
                with open(source_script_path, 'rb') as src_file:
                    script_content = src_file.read()
                
                # Write directly to the destination
                with open(setup_script, 'wb') as dest_file:
                    dest_file.write(script_content)
                
                # Ensure permissions are correct
                os.chmod(setup_script, 0o755)
                
                # Log the successful setup
                print(f"Setup script created at {setup_script}")
                
                # Run the setup script in the background for this user
                # Use a safer approach that doesn't rely on the symlink
                try:
                    subprocess.Popen(
                        f"cd {home_dir} && bash {setup_script} > {home_dir}/.setup.log 2>&1 &",
                        shell=True,
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                        start_new_session=True
                    )
                    print(f"Setup script executed for {home_dir}")
                except Exception as e:
                    print(f"Warning: Failed to execute setup script: {str(e)}")
            except Exception as e:
                print(f"Warning: Failed to setup enhanced environment: {str(e)}")
        else:
            print(f"Warning: Enhanced environment setup script not found at {source_script_path}")
        
        # Set up the pkg command if not already present
        pkg_dest = os.path.join(user_bin_dir, 'pkg')
        if not os.path.exists(pkg_dest) and os.path.exists(os.path.join(scripts_dir, 'termux-environment')):
            # Extract the pkg command from termux-environment
            try:
                with open(os.path.join(scripts_dir, 'termux-environment'), 'r') as f:
                    termux_env_content = f.read()
                    
                # Find the pkg command definition
                if 'pkg command for Termux' in termux_env_content:
                    pkg_start = termux_env_content.find('pkg command for Termux')
                    if pkg_start > 0:
                        # Extract the command definition
                        pkg_content = termux_env_content[pkg_start:pkg_start+5000]  # Assume it's less than 5000 chars
                        # Find the end of the function
                        pkg_end = pkg_content.find('\nEOF\n')
                        if pkg_end > 0:
                            pkg_script = pkg_content[:pkg_end+5]  # Include the EOF
                            
                            # Write to the pkg command file
                            with open(pkg_dest, 'w') as f:
                                f.write('#!/bin/bash\n# Extracted from termux-environment\n\n')
                                f.write(pkg_script)
                            
                            # Make executable
                            os.chmod(pkg_dest, 0o755)
            except Exception as e:
                print(f"Warning: Failed to extract pkg command: {str(e)}")
        
        # Setup links for OpenSSL wrapper if available
        openssl_wrapper_src = os.path.join(scripts_dir, 'openssl-wrapper')
        openssl_wrapper_dest = os.path.join(user_bin_dir, 'openssl-wrapper')
        
        if os.path.exists(openssl_wrapper_src):
            try:
                # Copy OpenSSL wrapper or create a symlink
                if os.path.exists(openssl_wrapper_dest):
                    # Check if content is different before overwriting
                    if os.path.getsize(openssl_wrapper_src) != os.path.getsize(openssl_wrapper_dest):
                        shutil.copy2(openssl_wrapper_src, openssl_wrapper_dest)
                else:
                    shutil.copy2(openssl_wrapper_src, openssl_wrapper_dest)
                
                os.chmod(openssl_wrapper_dest, 0o755)
                
                # Create an alias in bashrc (check first if it already exists)
                openssl_alias = '\n# Use enhanced OpenSSL wrapper\nalias openssl="openssl-wrapper"\n'
                try:
                    if os.path.exists(bashrc_path):
                        with open(bashrc_path, 'r') as f:
                            bashrc_content = f.read()
                        
                        if "alias openssl=" not in bashrc_content:
                            with open(bashrc_path, 'a') as f:
                                f.write(openssl_alias)
                    else:
                        with open(bashrc_path, 'w') as f:
                            f.write(BASHRC_TEMPLATE + openssl_alias)
                except Exception as e:
                    print(f"Warning: Failed to update bashrc: {str(e)}")
            except Exception as e:
                print(f"Warning: Failed to setup OpenSSL wrapper: {str(e)}")

        # Create a simple session keep-alive script
        keep_alive_path = os.path.join(user_bin_dir, 'session-keep-alive')
        try:
            with open(keep_alive_path, 'w') as f:
                f.write("""#!/bin/bash
# Simple script to keep session alive by running light commands periodically

echo "Starting session keep-alive service..."
echo "This will prevent your session from timing out due to inactivity."
echo "Press Ctrl+C to stop."

while true; do
    # Run a light command to keep session active
    echo -n "."
    sleep 300  # 5 minutes
done
""")
            os.chmod(keep_alive_path, 0o755)
        except Exception as e:
            print(f"Warning: Failed to create keep-alive script: {str(e)}")
        
        # Create a memory-monitoring script to help prevent OOM conditions
        memory_monitor_path = os.path.join(user_bin_dir, 'monitor-memory')
        try:
            with open(memory_monitor_path, 'w') as f:
                f.write("""#!/bin/bash
# Memory monitoring and management script

echo "Starting memory monitor..."
echo "This script helps prevent out-of-memory crashes."
echo "Press Ctrl+C to stop."

THRESHOLD=90  # Memory usage percentage threshold

while true; do
    # Get current memory usage percentage
    if command -v free &> /dev/null; then
        # Linux with free command
        MEM_USAGE=$(free | grep Mem | awk '{print int($3/$2 * 100)}')
    elif command -v vm_stat &> /dev/null; then
        # macOS with vm_stat
        MEM_USAGE=$(vm_stat | grep "Page free" | awk '{print int((1-$3) * 100)}')
    else
        # Fallback - just use a safe value
        MEM_USAGE=70
    fi
    
    if [ "$MEM_USAGE" -gt "$THRESHOLD" ]; then
        echo "WARNING: High memory usage detected: ${MEM_USAGE}%"
        echo "Clearing cached data to free memory..."
        
        # Clear Python cache
        python3 -c "import gc; gc.collect()" 2>/dev/null || true
        
        # Clear any large temporary files
        find /tmp -type f -size +10M -delete 2>/dev/null || true
        
        # Reduce memory usage by restarting services (not in this user space)
        echo "Memory cleanup completed."
    fi
    
    sleep 60  # Check every minute
done
""")
            os.chmod(memory_monitor_path, 0o755)
        except Exception as e:
            print(f"Warning: Failed to create memory monitor script: {str(e)}")
        
        # Log the setup time for performance monitoring
        setup_time = time.time() - start_time
        print(f"User environment setup completed in {setup_time:.2f} seconds")
        
        return True
    except Exception as e:
        print(f"Error setting up user environment for {home_dir}: {str(e)}")
        return False


def terminate_process(session_id):
    """Terminate any running process for a session"""
    if session_id in running_processes:
        process_info = running_processes[session_id]
        try:
            # Try to terminate the process group
            os.killpg(os.getpgid(process_info['process'].pid), signal.SIGTERM)
        except (ProcessLookupError, OSError):
            pass  # Process already terminated
        finally:
            if session_id in running_processes:
                del running_processes[session_id]


def cleanup_sessions():
    """Cleanup expired sessions"""
    with session_lock:
        current_time = time.time()
        expired_sessions = []
        
        # Find expired sessions
        for session_id, session in sessions.items():
            if current_time - session['last_accessed'] > SESSION_TIMEOUT:
                expired_sessions.append(session_id)
        
        # Remove expired sessions
        for session_id in expired_sessions:
            # Terminate any running processes
            terminate_process(session_id)
            
            log_activity('session', {
                'action': 'expired',
                'session_id': session_id,
                'user_id': sessions[session_id]['user_id']
            })
            del sessions[session_id]
            
    # Schedule next cleanup
    threading.Timer(60.0, cleanup_sessions).start()  # Run every minute


# Handle process cleanup on shutdown
def cleanup_on_exit():
    """Clean up all running processes when the server shuts down"""
    for session_id in list(running_processes.keys()):
        terminate_process(session_id)

atexit.register(cleanup_on_exit)

# Start session cleanup thread
cleanup_sessions()


def authenticate():
    """Authenticate the request if authentication is enabled"""
    if not USE_AUTH:
        return True
        
    api_key = request.headers.get('X-API-Key')
    if not api_key or api_key != API_KEY:
        return False
    
    return True


# Map of user IDs to their active sessions for cross-endpoint session tracking
user_sessions = {}

# Track file operations by session for improved security and debugging
file_access_log = {}

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

def get_session(session_id):
    """Get and validate a session"""
    with session_lock:
        if session_id not in sessions:
            
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
                
            return None
            
        session = sessions[session_id]
        current_time = time.time()
        
        # Check if session has expired
        if current_time - session['last_accessed'] > SESSION_TIMEOUT:
            del sessions[session_id]
            return None
            
        # Update last accessed time
        session['last_accessed'] = current_time
        
        # Track active sessions by user ID for cross-endpoint persistence
        if 'user_id' in session and session['user_id']:
            user_sessions[session['user_id']] = session_id
            
        return session


# Web Terminal Interface Routes
@app.route('/')
@cached_response(timeout=3600)  # Cache for 1 hour
def index():
    """Serve web terminal interface"""
    return send_file('static/simple-terminal.html')

@app.route('/container-terminal')
@cached_response(timeout=3600)  # Cache for 1 hour
def container_terminal():
    """Serve container-based terminal interface"""
    return send_file('static/container-terminal.html')

@app.route('/status')
@cached_response(timeout=60)  # Cache for 1 minute only to keep data fresh
def status_dashboard():
    """Serve server status dashboard for monitoring"""
    return send_file('static/status.html')


@app.route('/static/<path:path>')
@cached_response(timeout=86400)  # Cache for 1 day
def serve_static(path):
    """Serve static files"""
    # Use cached file content for common static files
    if path.endswith(('.js', '.css', '.html')):
        try:
            file_path = os.path.join('static', path)
            if os.path.exists(file_path) and os.path.isfile(file_path):
                content = get_cached_file_content(file_path)
                
                # Set content type based on file extension
                content_type = 'text/plain'
                if path.endswith('.js'):
                    content_type = 'application/javascript'
                elif path.endswith('.css'):
                    content_type = 'text/css'
                elif path.endswith('.html'):
                    content_type = 'text/html'
                
                response = make_response(content)
                response.headers['Content-Type'] = content_type
                response.headers['Cache-Control'] = 'public, max-age=86400'
                return response
        except Exception:
            # Fall back to standard method if caching fails
            pass
            
    return send_from_directory('static', path)


# API Endpoints
# Session pool - pre-created sessions for faster allocation
session_pool = []
SESSION_POOL_SIZE = 10  # Increased pool size for better concurrency
MAX_POOL_AGE = 1800  # Maximum age of a pooled session (30 minutes)
session_pool_lock = threading.Lock()
pool_initialization_in_progress = False  # Flag to prevent multiple initializations

def initialize_session_pool():
    """Pre-create sessions for the pool to speed up session allocation"""
    global pool_initialization_in_progress
    
    # Use a flag to prevent multiple threads from initializing at once
    if pool_initialization_in_progress:
        return
        
    # Set flag before acquiring lock to prevent race conditions
    pool_initialization_in_progress = True
    
    try:
        with session_pool_lock:
            current_time = time.time()
            
            # Remove any old sessions from the pool
            expired_sessions = [s for s in session_pool if current_time - s['created'] > MAX_POOL_AGE]
            for expired in expired_sessions:
                session_pool.remove(expired)
                
            # Only fill the pool if it's below threshold
            needed_sessions = SESSION_POOL_SIZE - len(session_pool)
            new_sessions = []
            
            for _ in range(needed_sessions):
                session_id = str(uuid.uuid4())
                home_dir = os.path.join('user_data', session_id)
                
                # Create the session in a controlled process
                try:
                    # Set up environment with basic structure only
                    os.makedirs(home_dir, exist_ok=True)
                    
                    # Create basic required directories immediately
                    dirs_to_create = [
                        os.path.join(home_dir, '.local', 'bin'),
                        os.path.join(home_dir, '.config'),
                    ]
                    
                    for directory in dirs_to_create:
                        os.makedirs(directory, exist_ok=True)
                    
                    # Add to new sessions list
                    new_sessions.append({
                        'session_id': session_id,
                        'home_dir': home_dir,
                        'created': time.time()
                    })
                except Exception as e:
                    print(f"Error pre-creating session: {str(e)}")
                    continue
            
            # Add all successfully created sessions to the pool
            session_pool.extend(new_sessions)
            
            # Now process the environment setup for each new session in background
            for session in new_sessions:
                # Set up the complete environment in a separate thread
                threading.Thread(
                    target=setup_user_environment,
                    args=(session['home_dir'],),
                    daemon=True
                ).start()
                
            print(f"Session pool initialized with {len(session_pool)} sessions (added {len(new_sessions)} new)")
    except Exception as e:
        print(f"Error during session pool initialization: {str(e)}")
    finally:
        # Reset flag when done
        pool_initialization_in_progress = False
    
    # Schedule next pool refill
    threading.Timer(30.0, initialize_session_pool).start()  # Run more frequently for better availability

# Start session pool initialization
initialize_session_pool()

@app.route('/create-session', methods=['POST'])
def create_session():
    """Create a new session for a user - optimized with session pooling"""
    start_time = time.time()
    
    # Ensure the user_data directory exists with proper permissions
    try:
        parent_dir = 'user_data'
        os.makedirs(parent_dir, exist_ok=True)
        os.chmod(parent_dir, 0o777)  # Make it fully writable
        print(f"Ensured user_data directory exists with proper permissions")
    except Exception as e:
        print(f"Warning: Could not set up user_data directory: {str(e)}")
    
    if USE_AUTH and not authenticate():
        return jsonify({'error': 'Authentication failed'}), 401
        
    data = request.json or {}
    user_id = data.get('userId', str(uuid.uuid4()))
    client_ip = request.remote_addr
    
    # Include device identifier in session handling for better isolation
    device_id = request.headers.get('X-Device-ID', '')
    if not device_id:
        # Use User-Agent + IP as a fallback device identifier
        user_agent = request.headers.get('User-Agent', '')
        device_id = hashlib.md5(f"{user_agent}-{client_ip}".encode()).hexdigest()
    
    # Try to get a pre-created session from the pool
    pooled_session = None
    with session_pool_lock:
        if session_pool:
            pooled_session = session_pool.pop(0)
    
    if pooled_session:
        # Use a pre-created session from the pool (fast path)
        session_id = pooled_session['session_id']
        home_dir = pooled_session['home_dir']
        
        # Schedule pool refill in background
        threading.Thread(target=initialize_session_pool).start()
    else:
        # No pooled sessions available, create new one (slow path)
        
        # For better user isolation, create a deterministic but unique ID
        # This ensures the same user+device gets the same session directory
        if device_id:
            # Create a namespace UUID for consistent hashing
            namespace = uuid.UUID('6ba7b810-9dad-11d1-80b4-00c04fd430c8')  # DNS namespace
            # Create a deterministic UUID based on user+device
            session_id = str(uuid.uuid5(namespace, f"{user_id}-{device_id}-{client_ip}"))
            print(f"Created deterministic session ID for device isolation: {session_id}")
        else:
            # Fallback to random UUID if no device ID
            session_id = str(uuid.uuid4())
            print(f"Created random session ID: {session_id}")
            
        home_dir = os.path.join('user_data', session_id)
        
        # Check if this directory already exists from a previous session
        if os.path.exists(home_dir):
            print(f"Found existing user directory: {home_dir}")
            # Verify it has the right permissions
            try:
                os.chmod(home_dir, 0o777)  # Ensure it's writable
                print(f"Updated permissions on existing directory")
            except Exception as e:
                print(f"Warning: Could not update permissions: {str(e)}")
        else:
            print(f"Creating new user directory: {home_dir}")
        
        # Set up the user environment with necessary files and directories
        setup_result = setup_user_environment(home_dir)
        if not setup_result:
            print(f"WARNING: User environment setup failed or incomplete")
    
    # Register the session
    with session_lock:
        sessions[session_id] = {
            'user_id': user_id,
            'client_ip': client_ip,
            'created': time.time(),
            'last_accessed': time.time(),
            'home_dir': home_dir
        }
    
    # Initialize environment in a background thread to avoid blocking response
    def background_init(session_home_dir):
        try:
            # Run initial setup commands (source .bashrc, etc.) without blocking
            process = subprocess.Popen(
                "source .bashrc 2>/dev/null || true",
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                cwd=session_home_dir
            )
            process.communicate(timeout=2)  # Shorter timeout
        except Exception:
            pass  # Ignore errors
    
    # Start initialization in background
    threading.Thread(target=background_init, args=(home_dir,)).start()
    
    # Log activity
    log_activity('session', {
        'action': 'created',
        'session_id': session_id,
        'user_id': user_id,
        'client_ip': client_ip,
        'from_pool': pooled_session is not None,
        'response_time': time.time() - start_time
    })
    
    # Return response immediately
    response = jsonify({
        'sessionId': session_id,
        'userId': user_id,
        'message': 'Session created successfully',
        'expiresIn': SESSION_TIMEOUT * 1000  # Convert to milliseconds for client
    })
    
    # Add performance headers
    response.headers['X-Session-From-Pool'] = str(pooled_session is not None)
    response.headers['X-Response-Time'] = f"{(time.time() - start_time):.4f}s"
    
    return response


@app.route('/execute-command', methods=['POST'])
def execute_command():
    """Execute a command in the user's session"""
    cmd_start_time = time.time()
    
    if USE_AUTH and not authenticate():
        return jsonify({'error': 'Authentication failed'}), 401
        
    session_id = request.headers.get('X-Session-Id')
    
    # For compatibility with legacy clients
    if not session_id and not USE_AUTH:
        # Use IP address or a device identifier as a simple session identifier
        device_id = request.headers.get('X-Device-Id', request.remote_addr)
        
        # Find or create a session for this device
        with session_lock:
            for sid, session in sessions.items():
                if session['user_id'] == device_id:
                    session_id = sid
                    break
                    
            if not session_id:
                # Create a new session
                data = request.json or {}
                data['userId'] = device_id
                # We need to manually create a session since we can't return through the normal endpoint
                user_id = data.get('userId', str(uuid.uuid4()))
                client_ip = request.remote_addr
                
                # Create a new session
                session_id = str(uuid.uuid4())
                home_dir = os.path.join('user_data', session_id)
                
                # Set up the user environment with necessary files
                setup_user_environment(home_dir)
                
                with session_lock:
                    sessions[session_id] = {
                        'user_id': user_id,
                        'client_ip': client_ip,
                        'created': time.time(),
                        'last_accessed': time.time(),
                        'home_dir': home_dir
                    }
                
                log_activity('session', {
                    'action': 'created',
                    'session_id': session_id,
                    'user_id': user_id,
                    'client_ip': client_ip
                })
    
    session = get_session(session_id)
    
    # If the session is invalid or expired, create a new one instead of returning an error
    if not session:
        # Create a new session for this user/device
        logger.info(f"Session {session_id} invalid or expired, creating a new session")
        
        # Use client IP or device ID as a fallback user ID
        user_id = request.headers.get('X-Device-Id', request.remote_addr)
        client_ip = request.remote_addr
        
        # Create a new session
        new_session_id = str(uuid.uuid4())
        home_dir = os.path.join('user_data', new_session_id)
        
        # Set up the user environment with necessary files
        setup_user_environment(home_dir)
        
        with session_lock:
            sessions[new_session_id] = {
                'user_id': user_id,
                'client_ip': client_ip,
                'created': time.time(),
                'last_accessed': time.time(),
                'home_dir': home_dir
            }
        
        log_activity('session', {
            'action': 'auto_renewed',
            'old_session_id': session_id,
            'new_session_id': new_session_id,
            'user_id': user_id,
            'client_ip': client_ip
        })
        
        # Use the new session
        session_id = new_session_id
        session = sessions[session_id]
        
        # Return both the command result and the new session info
        auto_renewed = True
    else:
        auto_renewed = False
        
    data = request.json or {}
    command = data.get('command')
    
    if not command:
        return jsonify({'error': 'Command is required'}), 400
    
    # Reset the last_accessed time to prevent timeout during command execution
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['last_accessed'] = time.time()
            
    # Execute command using container pool if available
    if USE_CONTAINERS and container_pool is not None:
        try:
            logger.debug(f"Executing command via container pool: {command}")
            result = container_pool.execute_command(session['user_id'], command)
            
            if 'error' in result:
                logger.warning(f"Command execution error: {result['error']}")
                return jsonify({
                    'error': result['error'],
                    'exitCode': result.get('exit_code', 1),
                    'sessionRenewed': auto_renewed,
                    'newSessionId': session_id if auto_renewed else None
                }), 500
            
            # Return successful result
            return jsonify({
                'output': result.get('output', ''),
                'exitCode': result.get('exit_code', 0),
                'sessionRenewed': auto_renewed,
                'newSessionId': session_id if auto_renewed else None
            })
            
        except Exception as e:
            logger.error(f"Container execution error: {str(e)}")
            # Fall back to directory-based execution
            logger.info("Falling back to directory-based execution")
            # Continue with normal execution flow below
    
    # Handle special commands
    if command.strip() == 'help':
        help_path = os.path.join(session['home_dir'], 'help.txt')
        try:
            with open(help_path, 'r') as f:
                help_text = f.read()
            return jsonify({'output': help_text})
        except Exception:
            pass  # Fall through to regular command execution
    
    elif command.strip() == 'termux-help':
        # Special case for Termux help command
        termux_prefix = os.path.join(session['home_dir'], 'termux', 'data', 'data', 'com.termux', 'files', 'usr')
        help_path = os.path.join(termux_prefix, 'bin', 'termux-help')
        if os.path.exists(help_path):
            command = f"bash {help_path}"
        else:
            return jsonify({'output': 'Termux environment not set up yet. Run setup-termux first.'})
    
    elif command.strip() == 'install-python':
        # Run the Python setup script
        script_path = os.path.join(session['home_dir'], '.local', 'bin', 'install-python-pip')
        if os.path.exists(script_path):
            command = f"bash {script_path}"
        else:
            return jsonify({
                'error': 'Python installation helper script not found. Please contact the administrator.'
            }), 500
    
    elif command.strip() == 'install-node':
        # Run the Node.js setup script
        script_path = os.path.join(session['home_dir'], '.local', 'bin', 'install-node-npm')
        if os.path.exists(script_path):
            command = f"bash {script_path}"
        else:
            return jsonify({
                'error': 'Node.js installation helper script not found. Please contact the administrator.'
            }), 500
            
    elif command.strip() == 'setup-termux':
        # Run the Termux environment setup script
        script_path = os.path.join(session['home_dir'], '.local', 'bin', 'setup-termux-env')
        if os.path.exists(script_path):
            command = f"bash {script_path}"
        else:
            return jsonify({
                'error': 'Termux environment setup script not found. Please contact the administrator.'
            }), 500
    
    elif command.strip() == 'setup-enhanced-environment':
        # Run the enhanced environment setup script
        script_path = os.path.join(session['home_dir'], '.local', 'bin', 'setup-enhanced-environment')
        if os.path.exists(script_path):
            command = f"bash {script_path}"
        else:
            return jsonify({
                'error': 'Enhanced environment setup script not found. Please contact the administrator.'
            }), 500
    
    # Check for the session keep-alive command
    elif command.strip() == 'session-keep-alive':
        # Run the session-keep-alive script
        script_path = os.path.join(session['home_dir'], '.local', 'bin', 'session-keep-alive')
        if os.path.exists(script_path):
            command = f"bash {script_path}"
            # Return a special message since this is going to run in the background
            return jsonify({
                'output': 'Session keep-alive service started. This will prevent your session from timing out.\n' +
                          'It will continue running in the background, checking in every 5 minutes.\n' +
                          'You can safely run other commands now.'
            })
        else:
            return jsonify({
                'output': 'Session keep-alive script not found. Your session may time out after inactivity.'
            })
    
    # Verify the user directory exists for all commands - create it if it doesn't
    if not os.path.isdir(session['home_dir']):
        try:
            os.makedirs(session['home_dir'], exist_ok=True)
            print(f"Created missing user directory: {session['home_dir']}")
            # Since we had to create the directory, we should set up the environment
            setup_user_environment(session['home_dir'])
        except Exception as e:
            print(f"Error creating user directory: {str(e)}")
            return jsonify({'error': f"Could not access user directory: {str(e)}"}), 500

    # Handle terminal-based editors (nano, vim, emacs, etc.)
    terminal_editors = ['nano', 'vim', 'vi', 'emacs', 'pico', 'joe', 'ed']
    for editor in terminal_editors:
        if command.strip().startswith(f"{editor} "):
            # Extract filename from command
            parts = command.strip().split()
            if len(parts) > 1:
                filename = parts[1]
                # Check if file exists, create it if it doesn't
                filepath = os.path.join(session['home_dir'], filename)
                try:
                    # Create parent directories if they don't exist
                    os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                    
                    # Create the file if it doesn't exist
                    if not os.path.exists(filepath):
                        with open(filepath, 'w') as f:
                            f.write('')
                            
                    # Return a message explaining that web-based editors aren't supported
                    return jsonify({
                        'output': f"Terminal-based editors like {editor} aren't fully supported in the web terminal.\n\n"
                                 f"The file '{filename}' has been created. You can use these alternatives:\n"
                                 f"1. Use 'cat > {filename}' to create/edit the file (Ctrl+D to save)\n"
                                 f"2. Use 'echo \"content\" > {filename}' to write to the file\n"
                                 f"3. Use 'cat {filename}' to view the file contents"
                    })
                except Exception as e:
                    return jsonify({'error': f"Failed to create file: {str(e)}"}), 500
            else:
                return jsonify({
                    'output': f"Terminal-based editors like {editor} aren't fully supported in the web terminal.\n"
                             f"Please specify a filename, e.g., {editor} filename.txt"
                })

    # First, clean the command - remove any accidental leading $ characters from copy/paste
    cleaned_command = command.strip()
    if cleaned_command.startswith('$'):
        cleaned_command = cleaned_command[1:].strip()
        print(f"Removed leading $ from command: {cleaned_command}")
        command = cleaned_command  # Update the command for further processing
        
    # Handle Python code execution (if it looks like Python code)
    python_patterns = ['print(', 'def ', 'import ', 'for ', 'while ', 'if ', 'class ', 'from ', 
                     'with ', 'try:', 'except:', 'finally:', 'else:', 'elif ', 'lambda ',
                     'async ', 'await ', 'yield ', '"""', "'''"]
    python_functions = ['len(', 'range(', 'list(', 'dict(', 'set(', 'int(', 'str(', 'float(', 'bool(', 'tuple(']
    
    # Add more patterns to detect Python code
    is_python_code = False
    
    # Check if command starts with any Python patterns
    for pattern in python_patterns:
        if command.strip().startswith(pattern):
            is_python_code = True
            print(f"Detected Python code by pattern: {pattern}")
            break
            
    # Check for common Python functions
    if not is_python_code:
        for func in python_functions:
            if func in command:
                is_python_code = True
                print(f"Detected Python code by function: {func}")
                break
    
    # Look for Python syntax patterns if not yet detected
    if not is_python_code:
        # Check for variable assignment pattern (x = y)
        if re.search(r'^[a-zA-Z_][a-zA-Z0-9_]*\s*=\s*.+$', command.strip()):
            is_python_code = True
            print("Detected Python code by assignment pattern")
            
        # Check for list/dict literals
        elif '[' in command and ']' in command:
            is_python_code = True
            print("Detected Python code by list/dict pattern")
            
        # Check for parentheses which might indicate function calls
        elif '(' in command and ')' in command:
            is_python_code = True
            print("Detected Python code by parentheses pattern")
    
    if is_python_code:
        # Wrap the command in python -c
        python_cmd = command.replace('"', '\\"')  # Escape double quotes
        command = f'python3 -c "{python_cmd}"'
        print(f"Executing as Python: {command}")
    
    # Special handling for OpenSSL commands - use our wrapper if available
    if command.strip().startswith('openssl '):
        # Check local user openssl-wrapper
        openssl_wrapper = os.path.join(session['home_dir'], '.local', 'bin', 'openssl-wrapper')
        
        # If wrapper doesn't exist, copy it from source script dir with robust handling
        if not os.path.exists(openssl_wrapper) or not os.access(openssl_wrapper, os.X_OK):
            try:
                # Ensure the .local/bin directory exists and is writable
                local_bin_dir = os.path.join(session['home_dir'], '.local', 'bin')
                os.makedirs(local_bin_dir, exist_ok=True)
                os.chmod(local_bin_dir, 0o777)  # Make it fully writable
                print(f"OpenSSL command detected - preparing environment at {local_bin_dir}")
                
                # Try multiple possible locations for the source wrapper
                source_paths = [
                    os.path.join('user_scripts', 'openssl-wrapper'),
                    os.path.abspath(os.path.join('user_scripts', 'openssl-wrapper')),
                    '/app/user_scripts/openssl-wrapper',
                    os.path.join(os.getcwd(), 'user_scripts', 'openssl-wrapper'),
                    '/user_scripts/openssl-wrapper'
                ]
                
                wrapper_found = False
                for source_wrapper in source_paths:
                    if os.path.exists(source_wrapper):
                        print(f"Found openssl-wrapper at: {source_wrapper}")
                        
                        # Try multiple copy methods
                        # Method 1: Direct file read/write
                        try:
                            with open(source_wrapper, 'rb') as src:
                                wrapper_content = src.read()
                                with open(openssl_wrapper, 'wb') as dst:
                                    dst.write(wrapper_content)
                            os.chmod(openssl_wrapper, 0o777)  # Make fully executable
                            wrapper_found = True
                            print(f"✓ Successfully copied openssl-wrapper (direct file copy)")
                            break
                        except Exception as copy_error:
                            print(f"Direct copy failed: {str(copy_error)}")
                            
                            # Method 2: Try shutil
                            try:
                                shutil.copy2(source_wrapper, openssl_wrapper)
                                os.chmod(openssl_wrapper, 0o777)
                                wrapper_found = True
                                print(f"✓ Successfully copied openssl-wrapper (shutil)")
                                break
                            except Exception as copy_error:
                                print(f"Shutil copy failed: {str(copy_error)}")
                                
                                # Method 3: Shell command
                                try:
                                    subprocess.run(f"cat '{source_wrapper}' > '{openssl_wrapper}'", shell=True, check=True)
                                    subprocess.run(["chmod", "777", openssl_wrapper], check=True)
                                    wrapper_found = True
                                    print(f"✓ Successfully copied openssl-wrapper (shell)")
                                    break
                                except Exception as copy_error:
                                    print(f"Shell copy failed: {str(copy_error)}")
                
                if not wrapper_found:
                    print(f"ERROR: Could not find or copy openssl-wrapper from any location")
                    print(f"Searched in: {source_paths}")
            except Exception as e:
                print(f"Failed to set up openssl-wrapper: {str(e)}")

        # Now check if the wrapper exists and use it if possible
        if os.path.exists(openssl_wrapper) and os.access(openssl_wrapper, os.X_OK):
            print(f"Using openssl-wrapper at {openssl_wrapper}")
            # Extract the openssl subcommand and arguments
            openssl_parts = command.strip().split(' ')
            if len(openssl_parts) > 1:
                openssl_cmd = ' '.join(openssl_parts[1:])
                command = f"bash {openssl_wrapper} {openssl_cmd}"
                print(f"Using wrapper with command: {command}")
        else:
            # Fallback to direct execution with preset passphrase for OpenSSL
            print(f"Warning: Using direct openssl command (wrapper not available at {openssl_wrapper})")
            # Check wrapper permissions and existence for debugging
            if os.path.exists(openssl_wrapper):
                print(f"Wrapper exists but is not executable. Permissions: {oct(os.stat(openssl_wrapper).st_mode)}")
                # Try one more time to fix permissions
                try:
                    os.chmod(openssl_wrapper, 0o777)
                    subprocess.run(["chmod", "777", openssl_wrapper], check=False)
                    print(f"Attempted to fix permissions")
                except Exception as e:
                    print(f"Failed to fix permissions: {str(e)}")
            else:
                print(f"Wrapper does not exist at path: {openssl_wrapper}")
    
    # Prevent potentially dangerous or resource-intensive commands
    disallowed_commands = [
        'sudo ', 'su ', 'chmod 777 ', 'chmod -R 777 ', 'rm -rf /', 'dd if=/dev/zero',
        '> /dev/sda', ':(){ :|:& };:'  # Fork bomb
    ]
    
    if not ENABLE_SYSTEM_COMMANDS:
        dangerous_prefixes = ['apt', 'apt-get', 'yum', 'dnf', 'pacman', 'systemctl', 'service']
        for prefix in dangerous_prefixes:
            if command.strip().startswith(prefix):
                return jsonify({
                    'error': f"System command '{prefix}' is disabled. Please use user-level installations instead."
                }), 403
    
    for bad_cmd in disallowed_commands:
        if bad_cmd in command:
            return jsonify({
                'error': f"Command contains disallowed operation: {bad_cmd}"
            }), 403
        
    # Log command for audit
    log_activity('command', {
        'session_id': session_id,
        'user_id': session['user_id'],
        'client_ip': session['client_ip'],
        'command': command
    })
    
    # Intercept apt/apt-get commands and redirect to pkg
    if command.strip().startswith('apt ') or command.strip().startswith('apt-get '):
        command = command.replace('apt ', 'pkg ').replace('apt-get ', 'pkg ')
    
    # Improve Python script execution
    if command.strip().startswith('python ') or command.strip().startswith('python3 '):
        parts = command.strip().split()
        if len(parts) >= 2 and (parts[1].endswith('.py') or '-m' in command):
            # Running a script or module - use python-import instead
            command = command.replace('python ', 'python-import ').replace('python3 ', 'python-import ')
            
            # Also automatically fix the shebang if it's a file
            if len(parts) >= 2 and parts[1].endswith('.py') and os.path.exists(os.path.join(session['home_dir'], parts[1])):
                script_path = parts[1]
                fix_cmd = f"if [ -x '$HOME/.local/bin/termux-fix-shebang' ]; then $HOME/.local/bin/termux-fix-shebang {script_path} > /dev/null 2>&1; fi; "
                command = fix_cmd + command
    
    # Terminate any existing process for this session
    terminate_process(session_id)
    
    try:
        # Create a working directory for this session if it doesn't exist
        os.makedirs(session['home_dir'], exist_ok=True)
        
        # Check if this command needs interactive handling
        is_interactive = False
        interactive_cmds = ['openssl', 'ssh-keygen', 'ssh', 'pg_dump', 'mysql', 'passwd', 'gpg']
        for interactive_cmd in interactive_cmds:
            if command.strip().startswith(interactive_cmd):
                is_interactive = True
                break
        
        # Also check for OpenSSL wrapper which is already interactive-aware
        if command.strip().startswith('openssl-wrapper'):
            is_interactive = False
        
        # Handle special command: pip install (use pip-termux when available)
        if command.strip().startswith('pip install '):
            # Check if we have pip-termux available
            pip_termux_path = os.path.join(session['home_dir'], '.local', 'bin', 'pip-termux')
            if os.path.exists(pip_termux_path) and not command.strip().startswith('pip-termux'):
                if '--user' in command:
                    command = command.replace('pip install ', 'pip-termux install ')
                else:
                    command = command.replace('pip install ', 'pip-termux install --user ')
            elif '--user' not in command:
                command = command.replace('pip install ', 'pip install --user ')
        
        # Add environment variables to help user-level installations
        env = os.environ.copy()
        env['HOME'] = session['home_dir']  
        env['PYTHONUSERBASE'] = os.path.join(session['home_dir'], '.local')
        env['PATH'] = os.path.join(session['home_dir'], '.local', 'bin') + ':' + env.get('PATH', '')
        env['USER'] = 'terminal-user'  # Provide a username for commands that need it
        env['OPENSSL_PASSPHRASE'] = 'termux_secure_passphrase'  # Default passphrase for OpenSSL operations
        
        # Source .profile instead of just .bashrc to get all environment variables
        profile_path = os.path.join(session['home_dir'], '.profile')
        if os.path.exists(profile_path):
            source_cmd = f"source {profile_path}"
        else:
            source_cmd = "source .bashrc 2>/dev/null || true"
        
        # Execute command with bash to ensure profile or bashrc is sourced
        full_command = f'cd {session["home_dir"]} && {source_cmd}; {command}'
        
        # For interactive commands, use our special handler
        if is_interactive:
            interactive_handler = os.path.join(session['home_dir'], '.local', 'bin', 'interactive-command-handler')
            
            # If the interactive handler doesn't exist, copy it from source
            if not os.path.exists(interactive_handler):
                try:
                    # Ensure the .local/bin directory exists
                    os.makedirs(os.path.join(session['home_dir'], '.local', 'bin'), exist_ok=True)
                    
                    # Copy the script from the source location
                    source_handler = os.path.join('user_scripts', 'interactive-command-handler')
                    if os.path.exists(source_handler):
                        shutil.copy2(source_handler, interactive_handler)
                        os.chmod(interactive_handler, 0o755)
                        print(f"Copied interactive-command-handler to {interactive_handler}")
                    else:
                        print(f"Source interactive-command-handler not found at {source_handler}")
                except Exception as e:
                    print(f"Failed to copy interactive-command-handler: {str(e)}")
            
            if os.path.exists(interactive_handler) and os.access(interactive_handler, os.X_OK):
                # Use the interactive command handler with bash explicitly
                handler_cmd = f"cd {session['home_dir']} && {source_cmd}; bash {interactive_handler} '{command}' '{session_id}'"
                
                # Run the handler and get FIFO paths
                try:
                    handler_process = subprocess.Popen(
                        handler_cmd,
                        shell=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        cwd=session['home_dir'],
                        env=env
                    )
                    
                    handler_out, handler_err = handler_process.communicate(timeout=10)
                    
                    if handler_process.returncode == 0 and "FIFOs:" in handler_out:
                        # Extract FIFO paths from handler output
                        fifo_info = handler_out.strip().split("FIFOs: ")[1]
                        cmd_fifo, resp_fifo = fifo_info.split(":")
                        
                        # Return special response for interactive commands
                        return jsonify({
                            'interactive': True,
                            'message': 'Interactive command started. Use the provided FIFOs to communicate.',
                            'cmd_fifo': cmd_fifo,
                            'resp_fifo': resp_fifo
                        })
                    else:
                        # Fall back to regular execution if the handler failed
                        print(f"Interactive handler failed: {handler_err}")
                        print(f"Handler output: {handler_out}")
                        is_interactive = False
                except Exception as e:
                    print(f"Error running interactive handler: {str(e)}")
                    is_interactive = False
            else:
                print(f"Interactive handler not found or not executable at {interactive_handler}")
                is_interactive = False
        
        # Start process in its own process group
        process = subprocess.Popen(
            full_command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=session['home_dir'],
            env=env,
            preexec_fn=os.setsid  # Create new process group
        )
        
        # Store process information
        running_processes[session_id] = {
            'process': process,
            'start_time': time.time()
        }
        
        try:
            stdout, stderr = process.communicate(timeout=COMMAND_TIMEOUT)
            # Remove from running processes if completed
            if session_id in running_processes:
                del running_processes[session_id]
                
            if process.returncode != 0:
                # Return both stdout and stderr for better debugging
                error_message = stderr or 'Command failed with no error output'
                output = stdout or ''
                if output and error_message:
                    combined = f"STDOUT:\n{output}\n\nERROR:\n{error_message}"
                else:
                    combined = error_message
                    
                # Prepare error response data
                error_response = {
                    'error': combined,
                    'exitCode': process.returncode
                }
                
                # If session was auto-renewed, include the new session ID in the error response
                if auto_renewed:
                    error_response['sessionRenewed'] = True
                    error_response['newSessionId'] = session_id
                    error_response['error'] = f"[Session renewed with ID: {session_id[:8]}...]\n{combined}"
                
                return jsonify(error_response), 400
            
            # Add response time for performance monitoring
            cmd_time = time.time() - cmd_start_time
            
            # Prepare response data
            response_data = {'output': stdout}
            
            # If session was auto-renewed, include the new session ID in the response
            if auto_renewed:
                response_data['sessionRenewed'] = True
                response_data['newSessionId'] = session_id
                response_data['output'] = f"[Session renewed with ID: {session_id[:8]}...]\n{stdout}"
            
            response = jsonify(response_data)
            response.headers['X-Command-Time'] = f"{cmd_time:.4f}s"
            return response
            
        except subprocess.TimeoutExpired:
            # Keep process running but return timeout message
            timeout_response = {
                'error': f'Command exceeded {COMMAND_TIMEOUT} second timeout limit. ' + 
                         'It continues running in the background. ' +
                         'Check results later or start a new command.'
            }
            
            # If session was auto-renewed, include the new session ID in the timeout response
            if auto_renewed:
                timeout_response['sessionRenewed'] = True
                timeout_response['newSessionId'] = session_id
                timeout_response['error'] = f"[Session renewed with ID: {session_id[:8]}...]\n{timeout_response['error']}"
            
            return jsonify(timeout_response), 408
        
    except Exception as e:
        # Cleanup any processes on error
        terminate_process(session_id)
        
        # Prepare the error response
        error_response = {'error': f'Failed to execute command: {str(e)}'}
        
        # If session was auto-renewed, include the new session ID in the error response
        if auto_renewed:
            error_response['sessionRenewed'] = True
            error_response['newSessionId'] = session_id
            error_response['error'] = f"[Session renewed with ID: {session_id[:8]}...]\n{error_response['error']}"
        
        return jsonify(error_response), 500


@app.route('/session', methods=['GET'])
def session_info():
    """Get information about the current session"""
    if USE_AUTH and not authenticate():
        return jsonify({'error': 'Authentication failed'}), 401
        
    session_id = request.headers.get('X-Session-Id')
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
        
    session = get_session(session_id)
    if not session:
        return jsonify({'error': 'Invalid or expired session'}), 401
        
    return jsonify({
        'userId': session['user_id'],
        'created': datetime.fromtimestamp(session['created']).isoformat(),
        'lastAccessed': datetime.fromtimestamp(session['last_accessed']).isoformat(),
        'expiresIn': int(SESSION_TIMEOUT - (time.time() - session['last_accessed'])) * 1000  # ms
    })


@app.route('/session', methods=['DELETE'])
def delete_session():
    """Delete a session"""
    if USE_AUTH and not authenticate():
        return jsonify({'error': 'Authentication failed'}), 401
        
    session_id = request.headers.get('X-Session-Id')
    if not session_id:
        return jsonify({'error': 'Session ID is required'}), 400
        
    with session_lock:
        if session_id in sessions:
            log_activity('session', {
                'action': 'deleted',
                'session_id': session_id,
                'user_id': sessions[session_id]['user_id']
            })
            
            # Cleanup session data
            home_dir = sessions[session_id]['home_dir']
            del sessions[session_id]
            
            # Could delete user data here, but we'll leave it for now
            # import shutil
            # shutil.rmtree(home_dir, ignore_errors=True)
    
    return jsonify({'message': 'Session terminated successfully'})


@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint with enhanced diagnostics"""
    import psutil
    
    # Gather system stats
    process = psutil.Process(os.getpid())
    mem_info = process.memory_info()
    mem_percent = process.memory_percent()
    
    # Gather session information
    with session_lock:
        active_sessions = len(sessions)
        
    with session_pool_lock:
        available_pool_sessions = len(session_pool)
    
    # Get system load average (Unix-only)
    try:
        load_avg = os.getloadavg()
    except (AttributeError, OSError):
        load_avg = (0, 0, 0)
        
    # Check if memory usage is in warning territory
    memory_status = "ok"
    if mem_percent > 85:
        memory_status = "critical"
    elif mem_percent > 70:
        memory_status = "warning"
    
    # Return comprehensive health information
    return jsonify({
        'status': 'ok',
        'activeSessions': active_sessions,
        'version': app.config['SERVER_VERSION'],
        'uptime': time.time() - app.config.get('START_TIME', time.time()),
        'memory': {
            'percent': f"{mem_percent:.1f}%",
            'used_mb': mem_info.rss / (1024 * 1024),
            'status': memory_status
        },
        'pooledSessions': available_pool_sessions,
        'systemLoad': {
            '1min': load_avg[0],
            '5min': load_avg[1],
            '15min': load_avg[2]
        },
        'cacheStats': {
            'responseCache': {
                'size': len(response_cache),
                'hits': response_cache_hits,
                'misses': response_cache_misses
            },
            'fileCache': getattr(file_content_cache, 'currsize', 0)
        }
    })


# Register file management endpoints with Flask app
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
    session = get_session(session_id)
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

# Moved here after get_session is defined to avoid NameError
register_file_management_endpoints(app, get_session)

# Serve the file browser interface
@app.route('/files-browser')
def file_browser():
    """Serve the file browser interface"""
    return send_file('static/file-browser.html')

if __name__ == '__main__':
    print(f"Flask Terminal Server running on port {PORT}")
    print(f"Debug mode: {DEBUG}")
    print(f"Authentication enabled: {USE_AUTH}")
    print(f"Web terminal available at http://localhost:{PORT}")
    print(f"File browser available at http://localhost:{PORT}/files-browser")
    
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
