#!/bin/bash
# Script to install and set up Python and pip in user space

echo "Installing Python packages for user..."

# Ensure .local/bin exists and is in PATH
mkdir -p "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$PATH"

# Ensure we're using the user's pip configuration
export PYTHONUSERBASE="$HOME/.local"

# Install or upgrade pip
if ! command -v pip3 &> /dev/null; then
    echo "Installing pip..."
    curl https://bootstrap.pypa.io/get-pip.py -o get-pip.py
    python3 get-pip.py --user
    rm get-pip.py
else
    echo "Upgrading pip..."
    pip3 install --upgrade pip --user
fi

# Create virtual environment if it doesn't exist
if [ ! -d "$HOME/venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$HOME/venv"
fi

# Source virtual environment
source "$HOME/venv/bin/activate"

# Install basic packages that are commonly used
echo "Installing common Python packages..."
pip install --user requests numpy pandas matplotlib

echo "Python and pip are ready to use!"
echo "Your packages will be installed in: $HOME/.local"
echo "To install packages, use: pip install --user PACKAGE_NAME"
echo "Or use the shortcut: pip-user PACKAGE_NAME"
echo ""
echo "The virtual environment has been activated for this session."
