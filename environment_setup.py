"""
User Environment Setup Module

Handles the creation and setup of user environments including:
- Directory structure
- Configuration files
- Environment variables
- Shell utilities and scripts
"""

import os
import shutil
import subprocess
import logging
import threading
from openssl_improved import setup_openssl_environment

logger = logging.getLogger("environment_setup")

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

# Display welcome message on login
echo "iOS Terminal - Type 'help' for available commands"
"""

PROFILE_TEMPLATE = """
# Add local bin directory to PATH
export PATH="$HOME/.local/bin:$PATH"

# Set environment variables for better compatibility with fallbacks for locale
export LANG=C.UTF-8 2>/dev/null || export LANG=C
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
export TERM=xterm-256color

# Setup for interactive commands
export INTERACTIVE_COMMAND_SUPPORT=1

# Setup for OpenSSL
export OPENSSL_PASSPHRASE="termux_secure_passphrase"
export SSL_DIR="$HOME/.ssl"

# Source .bashrc if it exists
if [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi
"""

HELP_TEMPLATE = """iOS Terminal Help
===============

Command Examples
---------------
- File management:         ls, cp, mv, rm, mkdir, cat, touch
- Network tools:           curl, wget, ping
- Process management:      ps, kill
- Python development:      python, pip
- Text editing:            echo, cat, grep

File Operations
--------------
- List files:              ls -la
- Create directory:        mkdir dirname
- Create empty file:       touch filename
- Write to file:           echo "content" > filename
- Append to file:          echo "content" >> filename
- View file content:       cat filename

Tips
----
- Your files are preserved between sessions
- Use up/down arrows to navigate command history
- Tab completion is supported for commands and filenames
- Files can be edited directly with echo and cat commands
"""

class EnvironmentSetup:
    """
    Setup and maintain user environments for terminal sessions.
    
    This class handles:
    - Creating and initializing user home directories
    - Setting up configuration files
    - Copying utility scripts
    """
    
    def __init__(self, script_dir="user_scripts"):
        """
        Initialize the environment setup.
        
        Args:
            script_dir: Directory containing user scripts to be copied
        """
        self.script_dir = script_dir
        self.setup_lock = threading.Lock()
        
        # Verify script directory exists
        if not os.path.isdir(script_dir):
            logger.warning(f"Script directory {script_dir} not found")
        
        logger.info("Environment setup initialized")
    
    def setup_user_environment(self, home_dir):
        """
        Set up a user environment with necessary files and directories.
        
        Args:
            home_dir: The user's home directory path
            
        Returns:
            Boolean indicating success
        """
        with self.setup_lock:
            try:
                logger.info(f"Setting up user environment in {home_dir}")
                
                # Create the directory if it doesn't exist
                if not os.path.exists(home_dir):
                    os.makedirs(home_dir, exist_ok=True)
                
                # Create all required directories
                dirs_to_create = [
                    os.path.join(home_dir, 'projects'),
                    os.path.join(home_dir, 'downloads'),
                    os.path.join(home_dir, '.local', 'bin'),
                    os.path.join(home_dir, '.config'),
                    os.path.join(home_dir, '.cache'),
                    os.path.join(home_dir, '.ssl')  # For OpenSSL operations
                ]
                
                for directory in dirs_to_create:
                    os.makedirs(directory, exist_ok=True)
                
                # Create configuration files
                self._create_config_files(home_dir)
                
                # Copy utility scripts
                self._copy_utility_scripts(home_dir)
                
                # Set up OpenSSL environment
                setup_openssl_environment(home_dir)
                
                logger.info(f"User environment setup complete for {home_dir}")
                return True
                
            except Exception as e:
                logger.error(f"Error setting up user environment: {str(e)}")
                return False
    
    def _create_config_files(self, home_dir):
        """Create configuration files for the user environment"""
        try:
            # Create .bashrc
            bashrc_path = os.path.join(home_dir, '.bashrc')
            if not os.path.exists(bashrc_path):
                with open(bashrc_path, 'w') as f:
                    f.write(BASHRC_TEMPLATE)
            
            # Create .profile
            profile_path = os.path.join(home_dir, '.profile')
            if not os.path.exists(profile_path):
                with open(profile_path, 'w') as f:
                    f.write(PROFILE_TEMPLATE)
            
            # Create help.txt
            help_path = os.path.join(home_dir, 'help.txt')
            if not os.path.exists(help_path):
                with open(help_path, 'w') as f:
                    f.write(HELP_TEMPLATE)
            
            logger.debug(f"Created configuration files in {home_dir}")
            
        except Exception as e:
            logger.error(f"Error creating configuration files: {str(e)}")
            raise
    
    def _copy_utility_scripts(self, home_dir):
        """Copy utility scripts to the user's .local/bin directory"""
        try:
            bin_dir = os.path.join(home_dir, '.local', 'bin')
            os.makedirs(bin_dir, exist_ok=True)
            
            # Only try to copy scripts if the script directory exists
            if not os.path.isdir(self.script_dir):
                logger.warning(f"Script directory {self.script_dir} not found, skipping script copy")
                return
            
            # Find all executable scripts in the script directory
            for script_file in os.listdir(self.script_dir):
                script_path = os.path.join(self.script_dir, script_file)
                if os.path.isfile(script_path):
                    dest_path = os.path.join(bin_dir, script_file)
                    
                    # Copy the script
                    shutil.copy2(script_path, dest_path)
                    
                    # Make it executable
                    os.chmod(dest_path, 0o755)
            
            logger.debug(f"Copied utility scripts to {bin_dir}")
            
        except Exception as e:
            logger.error(f"Error copying utility scripts: {str(e)}")
            raise
