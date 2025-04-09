#!/usr/bin/env python3

# This script contains the improved OpenSSL handling code
# We'll use this as a reference to update flask_server.py

def get_openssl_handler_code():
    return """
    # Special handling for OpenSSL commands - use our wrapper if available
    if command.strip().startswith('openssl '):
        socketio.emit('command_output', {
            'output': "Setting up OpenSSL environment...\\n"
        }, to=request.sid)
        
        # Force a complete environment setup instead of just checking for existence
        try:
            # Get absolute path for home_dir
            abs_home_dir = os.path.abspath(session['home_dir'])
            print(f"OpenSSL command - ensuring environment in: {abs_home_dir}")
            
            # Let the user know we're working on it
            socketio.emit('command_output', {
                'output': f"Preparing environment for OpenSSL...\\n"
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
                    'output': "Warning: OpenSSL wrapper script not found. Using direct OpenSSL command.\\n"
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
                        'output': "Using enhanced OpenSSL wrapper script...\\n"
                    }, to=request.sid)
            else:
                # Fallback to direct execution with preset passphrase for OpenSSL
                print(f"Using direct openssl command (wrapper not available at {openssl_wrapper})")
                socketio.emit('command_output', {
                    'output': "Notice: Using direct OpenSSL command without wrapper.\\n"
                }, to=request.sid)
                
        except Exception as e:
            print(f"Critical error in OpenSSL setup: {str(e)}")
            socketio.emit('command_error', {
                'error': f"Error setting up OpenSSL environment: {str(e)}",
                'sessionRenewed': auto_renewed,
                'newSessionId': session_id if auto_renewed else None
            }, to=request.sid)
            return
"""

if __name__ == "__main__":
    print(get_openssl_handler_code())
