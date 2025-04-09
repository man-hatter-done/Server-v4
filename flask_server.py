import os
import uuid
import time
import json
import shutil
import signal
import subprocess
import threading
import atexit
from datetime import datetime
from flask import Flask, request, jsonify, send_from_directory, send_file, render_template
from flask_cors import CORS
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__, static_folder='static')
CORS(app)  # Enable CORS for all routes

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


def setup_user_environment(home_dir):
    """Set up a user environment with necessary files and directories"""
    os.makedirs(home_dir, exist_ok=True)
    
    # Create Python virtual environment if it doesn't exist
    venv_dir = os.path.join(home_dir, 'venv')
    if not os.path.exists(venv_dir):
        try:
            subprocess.run(['python3', '-m', 'venv', venv_dir], check=True)
        except subprocess.CalledProcessError:
            # Fallback if venv creation fails
            pass
    
    # Set up a .bashrc file with helpful configurations
    bashrc_path = os.path.join(home_dir, '.bashrc')
    if not os.path.exists(bashrc_path):
        with open(bashrc_path, 'w') as f:
            f.write("""
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
""")
    
    # Create additional useful directories
    os.makedirs(os.path.join(home_dir, 'projects'), exist_ok=True)
    os.makedirs(os.path.join(home_dir, 'downloads'), exist_ok=True)
    os.makedirs(os.path.join(home_dir, '.local', 'bin'), exist_ok=True)
    
    # Create a custom help file
    help_path = os.path.join(home_dir, 'help.txt')
    if not os.path.exists(help_path):
        with open(help_path, 'w') as f:
            f.write("""iOS Terminal Help
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
""")
    
    # Copy helper scripts to user's bin directory
    user_bin_dir = os.path.join(home_dir, '.local', 'bin')
    scripts_dir = 'user_scripts'
    
    if os.path.exists(scripts_dir):
        for script in ['install-python-pip.sh', 'install-node-npm.sh']:
            script_path = os.path.join(scripts_dir, script)
            if os.path.exists(script_path):
                # Copy and make executable
                dest_path = os.path.join(user_bin_dir, script.replace('.sh', ''))
                shutil.copy2(script_path, dest_path)
                os.chmod(dest_path, 0o755)


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
def index():
    """Serve web terminal interface"""
    return send_file('static/simple-terminal.html')


@app.route('/static/<path:path>')
def serve_static(path):
    """Serve static files"""
    return send_from_directory('static', path)


# API Endpoints
@app.route('/create-session', methods=['POST'])
def create_session():
    """Create a new session for a user"""
    if USE_AUTH and not authenticate():
        return jsonify({'error': 'Authentication failed'}), 401
        
    data = request.json or {}
    user_id = data.get('userId', str(uuid.uuid4()))
    client_ip = request.remote_addr
    
    # Create a new session
    session_id = str(uuid.uuid4())
    home_dir = os.path.join('user_data', session_id)
    
    # Set up the user environment with necessary files and directories
    setup_user_environment(home_dir)
    
    with session_lock:
        sessions[session_id] = {
            'user_id': user_id,
            'client_ip': client_ip,
            'created': time.time(),
            'last_accessed': time.time(),
            'home_dir': home_dir
        }
    
    # Initialize session with customized environment
    try:
        # Run initial setup commands (source .bashrc, etc.)
        process = subprocess.Popen(
            "source .bashrc 2>/dev/null || true",
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=home_dir
        )
        process.communicate(timeout=5)  # Short timeout for initialization
    except (subprocess.TimeoutExpired, Exception):
        pass  # Ignore errors during initialization
    
    log_activity('session', {
        'action': 'created',
        'session_id': session_id,
        'user_id': user_id,
        'client_ip': client_ip
    })
    
    return jsonify({
        'sessionId': session_id,
        'userId': user_id,
        'message': 'Session created successfully',
        'expiresIn': SESSION_TIMEOUT * 1000  # Convert to milliseconds for client
    })


@app.route('/execute-command', methods=['POST'])
def execute_command():
    """Execute a command in the user's session"""
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
    
    # Terminate any existing process for this session
    terminate_process(session_id)
    
    try:
        # Create a working directory for this session if it doesn't exist
        os.makedirs(session['home_dir'], exist_ok=True)
        
        # Handle special command: pip install (convert to user installation)
        if command.strip().startswith('pip install ') and '--user' not in command:
            # Modify to use --user flag for installing in user directory
            command = command.replace('pip install ', 'pip install --user ')
        
        # Add environment variables to help user-level installations
        env = os.environ.copy()
        env['HOME'] = session['home_dir']  
        env['PYTHONUSERBASE'] = os.path.join(session['home_dir'], '.local')
        env['PATH'] = os.path.join(session['home_dir'], '.local', 'bin') + ':' + env.get('PATH', '')
        env['USER'] = 'terminal-user'  # Provide a username for commands that need it
        
        # Execute command with bash to ensure .bashrc is sourced
        full_command = f'cd {session["home_dir"]} && source .bashrc 2>/dev/null || true; {command}'
        
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
                
            return jsonify({'output': stdout})
            
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


if __name__ == '__main__':
    print(f"Flask Terminal Server running on port {PORT}")
    print(f"Debug mode: {DEBUG}")
    print(f"Authentication enabled: {USE_AUTH}")
    print(f"Web terminal available at http://localhost:{PORT}")
    
    app.run(host='0.0.0.0', port=PORT, debug=DEBUG)
