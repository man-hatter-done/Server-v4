"""
OpenSSL command handling for the terminal command handler.

This module provides special handling for OpenSSL commands to ensure
they work correctly, especially for interactive commands and those
requiring password input.
"""

import os
import shutil
import subprocess
import logging

logger = logging.getLogger("openssl_handler")

def setup_openssl_environment(home_dir):
    """
    Set up the OpenSSL environment for a user.
    
    Args:
        home_dir: The user's home directory
        
    Returns:
        Boolean indicating success
    """
    try:
        # Create SSL directory
        ssl_dir = os.path.join(home_dir, '.ssl')
        os.makedirs(ssl_dir, exist_ok=True)
        
        # Create .local/bin directory
        local_bin_dir = os.path.join(home_dir, '.local', 'bin')
        os.makedirs(local_bin_dir, exist_ok=True)
        
        # Copy OpenSSL wrapper script from user_scripts
        openssl_wrapper_source = os.path.join('user_scripts', 'openssl-wrapper')
        openssl_wrapper_dest = os.path.join(local_bin_dir, 'openssl-wrapper')
        
        if os.path.exists(openssl_wrapper_source):
            # Copy the script
            shutil.copy2(openssl_wrapper_source, openssl_wrapper_dest)
            
            # Make it executable
            os.chmod(openssl_wrapper_dest, 0o755)
            
            logger.info(f"OpenSSL wrapper copied to {openssl_wrapper_dest}")
            return True
        else:
            logger.warning(f"OpenSSL wrapper source not found at {openssl_wrapper_source}")
            return False
    except Exception as e:
        logger.error(f"Error setting up OpenSSL environment: {str(e)}")
        return False

def handle_openssl_command(command, home_dir, callback=None):
    """
    Handle OpenSSL commands using the wrapper script.
    
    Args:
        command: The OpenSSL command to execute
        home_dir: The user's home directory
        callback: Function to call with streaming output
        
    Returns:
        Dict containing command result or None if the command is not an OpenSSL command
    """
    if not command.strip().startswith('openssl '):
        return None
    
    try:
        # Check if OpenSSL wrapper exists
        openssl_wrapper = os.path.join(home_dir, '.local', 'bin', 'openssl-wrapper')
        
        # If wrapper doesn't exist, set it up
        if not os.path.exists(openssl_wrapper) or not os.access(openssl_wrapper, os.X_OK):
            setup_success = setup_openssl_environment(home_dir)
            if not setup_success:
                logger.warning("Using direct openssl command (wrapper setup failed)")
                # Let the normal command handler process it
                return None
        
        # Log that we're handling this as a special OpenSSL command
        if callback:
            callback("Using enhanced OpenSSL wrapper...\n")
        
        # Extract the openssl subcommand and arguments
        openssl_parts = command.strip().split(' ')
        if len(openssl_parts) > 1:
            openssl_cmd = ' '.join(openssl_parts[1:])
            
            # Set up environment variables
            env = os.environ.copy()
            env['HOME'] = home_dir
            env['OPENSSL_PASSPHRASE'] = 'termux_secure_passphrase'  # Default passphrase
            
            # Use the wrapper script
            modified_command = f"bash {openssl_wrapper} {openssl_cmd}"
            
            # Let the normal command handler take it from here with the modified command
            return {
                "command": modified_command,
                "env": env
            }
        
    except Exception as e:
        logger.error(f"Error handling OpenSSL command: {str(e)}")
        if callback:
            callback(f"Error setting up OpenSSL environment: {str(e)}\n")
    
    # If anything fails, let the normal command handler process it
    return None
