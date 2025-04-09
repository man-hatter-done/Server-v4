import os
import shutil
import subprocess
from flask_socketio import SocketIO

def ensure_user_environment(session, session_id, auto_renewed, socketio, request_sid, setup_user_environment):
    """Make sure the user environment exists and is properly set up"""
    if not os.path.exists(session['home_dir']):
        try:
            print(f"Creating missing user directory: {session['home_dir']}")
            os.makedirs(session['home_dir'], exist_ok=True)
            os.chmod(session['home_dir'], 0o755)  # Ensure directory is accessible
            # Since we had to create the directory, set up the environment
            setup_user_environment(session['home_dir'])
            return True
        except Exception as e:
            print(f"Error creating user directory: {str(e)}")
            socketio.emit('command_error', {
                'error': f"Could not access or create user directory: {str(e)}",
                'sessionRenewed': auto_renewed,
                'newSessionId': session_id if auto_renewed else None
            }, to=request_sid)
            return False
    return True

def setup_openssl_wrapper(session, session_id, auto_renewed, socketio, request_sid):
    """Set up the OpenSSL wrapper for the user"""
    # Ensure user .local/bin directory exists
    local_bin_dir = os.path.join(session['home_dir'], '.local', 'bin')
    try:
        os.makedirs(local_bin_dir, exist_ok=True)
        os.chmod(local_bin_dir, 0o755)  # Make sure directory is accessible
    except Exception as e:
        print(f"Error creating .local/bin directory: {str(e)}")
        return None
    
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
                    'output': "Warning: OpenSSL wrapper script not found. Using direct OpenSSL command.\n"
                }, to=request_sid)
                return None
        except Exception as e:
            print(f"Failed to copy openssl-wrapper: {str(e)}")
            socketio.emit('command_output', {
                'output': f"Warning: Could not set up OpenSSL wrapper: {str(e)}\n"
            }, to=request_sid)
            return None
    
    # Now verify the wrapper exists and is executable
    if os.path.exists(openssl_wrapper) and os.access(openssl_wrapper, os.X_OK):
        return openssl_wrapper
    
    return None

def handle_openssl_command(command, session, session_id, auto_renewed, socketio, request_sid, setup_user_environment):
    """Special handling for OpenSSL commands"""
    # First ensure the user environment exists
    if not ensure_user_environment(session, session_id, auto_renewed, socketio, request_sid, setup_user_environment):
        return None
    
    # Set up the OpenSSL wrapper
    openssl_wrapper = setup_openssl_wrapper(session, session_id, auto_renewed, socketio, request_sid)
    
    if openssl_wrapper:
        # Extract the openssl subcommand and arguments
        openssl_parts = command.strip().split(' ')
        if len(openssl_parts) > 1:
            openssl_cmd = ' '.join(openssl_parts[1:])
            # Use full path to wrapper to avoid any PATH issues
            command = f"/bin/bash {openssl_wrapper} {openssl_cmd}"
            print(f"Using OpenSSL wrapper: {command}")
            return command
    else:
        # Fallback to direct execution with preset passphrase for OpenSSL
        print(f"Using direct openssl command (wrapper not available)")
        socketio.emit('command_output', {
            'output': "Warning: Using direct OpenSSL command without wrapper.\n"
        }, to=request_sid)
    
    # Return the original command if wrapper setup failed
    return command
