import os
import uuid
import time
import json
import shutil
import signal
import subprocess
import threading
import atexit
import functools
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template, make_response
from flask_cors import CORS
from flask_compress import Compress
from werkzeug.security import generate_password_hash, check_password_hash
import cachetools.func
from file_management import register_file_management_endpoints

# Create a Flask app with optimized settings
app = Flask(__name__, static_folder='static')
app.config['JSON_SORT_KEYS'] = False  # Faster JSON responses
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 86400  # Cache static files for 1 day
app.config['COMPRESS_ALGORITHM'] = ['gzip', 'deflate']  # Enable response compression
app.config['COMPRESS_LEVEL'] = 6  # Medium compression level - good balance between CPU and size
app.config['COMPRESS_MIN_SIZE'] = 500  # Only compress responses larger than 500 bytes

# Initialize Flask-Compress for response compression
compress = Compress()
compress.init_app(app)

# Enable CORS with optimized settings
CORS(app, resources={r"/*": {"origins": "*"}}, supports_credentials=True, max_age=86400)

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
                
            # Create a cache key from the request
            cache_key = f"{request.path}?{request.query_string.decode('utf-8')}"
            
            # Check if we have the response cached and it's not expired
            current_time = time.time()
            if cache_key in response_cache:
                cached_data, expiry_time = response_cache[cache_key]
                if current_time < expiry_time:
                    response_cache_hits += 1
                    return cached_data
            
            # Cache miss - generate response
            response_cache_misses += 1
            response = f(*args, **kwargs)
            
            # Only cache successful responses that are not too large
            # Don't cache streaming responses or file downloads
            if not isinstance(response, tuple) or (isinstance(response, tuple) and response[1] < 300):
                # Store in cache with expiry time
                response_cache[cache_key] = (response, current_time + timeout)
                
                # Trim cache if it's too large
                if len(response_cache) > response_cache_size:
                    # Remove oldest entries
                    oldest_keys = sorted(
                        response_cache.keys(), 
                        key=lambda k: response_cache[k][1]
                    )[:len(response_cache) - response_cache_size]
                    
                    for key in oldest_keys:
                        del response_cache[key]
                
            return response
        return decorated_function
    return decorator

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

# Create required directories
os.makedirs('logs', exist_ok=True)
os.makedirs('user_data', exist_ok=True)

# Session storage
sessions = {}
running_processes = {}  # Stores active subprocesses by session_id
session_lock = threading.Lock()


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
    
    # Create initial directories in parallel
    os.makedirs(home_dir, exist_ok=True)
    
    # Fix permissions - ensure all users can access the directory
    try:
        # Make directory and all subdirectories accessible
        os.chmod(home_dir, 0o755)
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
    
    # Create directories with a single call
    for directory in dirs_to_create:
        os.makedirs(directory, exist_ok=True)
        # Set proper permissions
        try:
            os.chmod(directory, 0o755)
        except Exception:
            pass  # Ignore permission errors
    
    # Only create venv if explicitly requested later (on-demand instead of at startup)
    # This significantly speeds up initial session creation
    
    # Write template files quickly
    bashrc_path = os.path.join(home_dir, '.bashrc')
    help_path = os.path.join(home_dir, 'help.txt')
    profile_path = os.path.join(home_dir, '.profile')
    
    # Parallel writing of files
    file_writing_tasks = [
        (bashrc_path, BASHRC_TEMPLATE),
        (help_path, HELP_TEMPLATE)
    ]
    
    # Write files if they don't exist
    for file_path, content in file_writing_tasks:
        if not os.path.exists(file_path):
            with open(file_path, 'w') as f:
                f.write(content)
    
    # Setup enhanced profile file for better environment
    with open(profile_path, 'w') as f:
        f.write("""
# Add local bin directory to PATH
export PATH="$HOME/.local/bin:$PATH"

# Set environment variables for better compatibility
export LANG=en_US.UTF-8
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
    
    # Copy all user scripts for better functionality
    user_bin_dir = os.path.join(home_dir, '.local', 'bin')
    scripts_dir = 'user_scripts'
    
    if os.path.exists(scripts_dir):
        # Copy all scripts, not just specific ones
        for script_file in os.listdir(scripts_dir):
            script_path = os.path.join(scripts_dir, script_file)
            if os.path.isfile(script_path):
                # Use cached script content if available for performance
                dest_path = os.path.join(user_bin_dir, script_file)
                
                if script_path not in script_cache:
                    with open(script_path, 'rb') as f:
                        script_cache[script_path] = f.read()
                
                # Write from cache
                with open(dest_path, 'wb') as f:
                    f.write(script_cache[script_path])
                
                # Set executable permissions
                os.chmod(dest_path, 0o755)
    
    # Set up enhanced environment using our new script if available
    setup_script = os.path.join(user_bin_dir, 'setup-enhanced-environment')
    if os.path.exists(os.path.join(scripts_dir, 'setup-enhanced-environment')):
        # Create symbolic link to the setup script
        os.symlink(os.path.join(scripts_dir, 'setup-enhanced-environment'), setup_script)
        os.chmod(setup_script, 0o755)
        
        # Run the setup script in the background for this user
        # Use nohup and background process to avoid blocking
        try:
            subprocess.Popen(
                f"cd {home_dir} && bash {setup_script} > {home_dir}/.setup.log 2>&1 &",
                shell=True,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True
            )
        except Exception as e:
            print(f"Warning: Failed to start enhanced environment setup: {str(e)}")
    
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
            # Copy OpenSSL wrapper
            shutil.copy2(openssl_wrapper_src, openssl_wrapper_dest)
            os.chmod(openssl_wrapper_dest, 0o755)
            
            # Create an alias in bashrc
            with open(bashrc_path, 'a') as f:
                f.write('\n# Use enhanced OpenSSL wrapper\nalias openssl="openssl-wrapper"\n')
        except Exception as e:
            print(f"Warning: Failed to setup OpenSSL wrapper: {str(e)}")

    # Create a simple session keep-alive script
    keep_alive_path = os.path.join(user_bin_dir, 'session-keep-alive')
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
    
    # Log the setup time for performance monitoring
    setup_time = time.time() - start_time
    print(f"User environment setup completed in {setup_time:.2f} seconds")


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


def get_session(session_id):
    """Get and validate a session"""
    with session_lock:
        if session_id not in sessions:
            return None
            
        session = sessions[session_id]
        current_time = time.time()
        
        # Check if session has expired
        if current_time - session['last_accessed'] > SESSION_TIMEOUT:
            del sessions[session_id]
            return None
            
        # Update last accessed time
        session['last_accessed'] = current_time
        return session


# Web Terminal Interface Routes
@app.route('/')
@cached_response(timeout=3600)  # Cache for 1 hour
def index():
    """Serve web terminal interface"""
    return send_file('static/simple-terminal.html')


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
SESSION_POOL_SIZE = 3  # Number of pre-created sessions to maintain
session_pool_lock = threading.Lock()

def initialize_session_pool():
    """Pre-create sessions for the pool to speed up session allocation"""
    with session_pool_lock:
        # Only fill the pool if it's empty or below threshold
        while len(session_pool) < SESSION_POOL_SIZE:
            session_id = str(uuid.uuid4())
            home_dir = os.path.join('user_data', session_id)
            
            # Set up environment in background
            setup_user_environment(home_dir)
            
            # Add to pool
            session_pool.append({
                'session_id': session_id,
                'home_dir': home_dir,
                'created': time.time()
            })
    
    # Schedule next pool refill
    threading.Timer(60.0, initialize_session_pool).start()

# Start session pool initialization
initialize_session_pool()

@app.route('/create-session', methods=['POST'])
def create_session():
    """Create a new session for a user - optimized with session pooling"""
    start_time = time.time()
    
    if USE_AUTH and not authenticate():
        return jsonify({'error': 'Authentication failed'}), 401
        
    data = request.json or {}
    user_id = data.get('userId', str(uuid.uuid4()))
    client_ip = request.remote_addr
    
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
        session_id = str(uuid.uuid4())
        home_dir = os.path.join('user_data', session_id)
        
        # Set up the user environment with necessary files and directories
        setup_user_environment(home_dir)
    
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
    if not session:
        return jsonify({'error': 'Invalid or expired session'}), 401
        
    data = request.json or {}
    command = data.get('command')
    
    if not command:
        return jsonify({'error': 'Command is required'}), 400
    
    # Reset the last_accessed time to prevent timeout during command execution
    with session_lock:
        if session_id in sessions:
            sessions[session_id]['last_accessed'] = time.time()
    
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
    
    # Special handling for OpenSSL commands - use our wrapper if available
    if command.strip().startswith('openssl '):
        openssl_wrapper = os.path.join(session['home_dir'], '.local', 'bin', 'openssl-wrapper')
        if os.path.exists(openssl_wrapper):
            # Extract the openssl subcommand and arguments
            openssl_parts = command.strip().split(' ')
            if len(openssl_parts) > 1:
                openssl_cmd = ' '.join(openssl_parts[1:])
                command = f"{openssl_wrapper} {openssl_cmd}"
    
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
            
            if os.path.exists(interactive_handler):
                # Use the interactive command handler
                handler_cmd = f"cd {session['home_dir']} && {source_cmd}; {interactive_handler} '{command}' '{session_id}'"
                
                # Run the handler and get FIFO paths
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
                    
                return jsonify({
                    'error': combined,
                    'exitCode': process.returncode
                }), 400
            
            # Add response time for performance monitoring
            cmd_time = time.time() - cmd_start_time
            response = jsonify({'output': stdout})
            response.headers['X-Command-Time'] = f"{cmd_time:.4f}s"
            return response
            
        except subprocess.TimeoutExpired:
            # Keep process running but return timeout message
            return jsonify({
                'error': f'Command exceeded {COMMAND_TIMEOUT} second timeout limit. ' + 
                         'It continues running in the background. ' +
                         'Check results later or start a new command.'
            }), 408
        
    except Exception as e:
        # Cleanup any processes on error
        terminate_process(session_id)
        return jsonify({'error': f'Failed to execute command: {str(e)}'}), 500


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
    """Health check endpoint"""
    with session_lock:
        active_sessions = len(sessions)
    
    return jsonify({
        'status': 'ok',
        'activeSessions': active_sessions,
        'version': 'flask-1.0.0'
    })


# Register file management endpoints with Flask app
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
