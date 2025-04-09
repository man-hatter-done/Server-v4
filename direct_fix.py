#!/usr/bin/env python3

# Script to directly apply the necessary fix to flask_server.py
import re

# Read the original file
with open('flask_server.py', 'r') as file:
    content = file.read()

# Find the OpenSSL section using regex to be precise
openssl_pattern = r'# Special handling for OpenSSL commands - use our wrapper if available\s+if command\.strip\(\)\.startswith\(\'openssl \'\):.*?print\(f"Using direct openssl command \(wrapper not available at \{openssl_wrapper\}\)"\)'

# Our improved OpenSSL handler code
improved_code = '''    # Special handling for OpenSSL commands - use our wrapper if available
    if command.strip().startswith('openssl '):
        # First, verify the user directory exists and create it if needed
        if not os.path.exists(session['home_dir']):
            try:
                print(f"Creating missing user directory: {session['home_dir']}")
                os.makedirs(session['home_dir'], exist_ok=True)
                os.chmod(session['home_dir'], 0o755)  # Ensure directory is accessible
                # Since we had to create the directory, set up the environment
                setup_user_environment(session['home_dir'])
            except Exception as e:
                print(f"Error creating user directory: {str(e)}")
                socketio.emit('command_error', {
                    'error': f"Could not access or create user directory: {str(e)}",
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
                        'output': "Warning: OpenSSL wrapper script not found. Using direct OpenSSL command.\\n"
                    }, to=request.sid)
            except Exception as e:
                print(f"Failed to copy openssl-wrapper: {str(e)}")
                socketio.emit('command_output', {
                    'output': f"Warning: Could not set up OpenSSL wrapper: {str(e)}\\nWill try to use direct command.\\n"
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
                'output': "Notice: Using direct OpenSSL command without wrapper.\\n"
            }, to=request.sid)'''

# Replace first occurrence of the OpenSSL handling code
# Using re.DOTALL to make . match newlines, and re.sub to do the replacement
new_content = re.sub(openssl_pattern, improved_code, content, count=1, flags=re.DOTALL)

# Write the updated content back to the file
with open('flask_server.py', 'w') as file:
    file.write(new_content)

print("Successfully updated flask_server.py with the OpenSSL directory fix")
