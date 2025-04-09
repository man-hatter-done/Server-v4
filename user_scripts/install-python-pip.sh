#!/bin/bash
# Script to install and set up Python and pip in Termux-like environment

echo "Setting up Python environment for Termux-like experience..."

# Ensure basic directories exist
mkdir -p "$HOME/.local/bin"
mkdir -p "$HOME/.local/lib/python$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)/site-packages"

# Add to PATH
export PATH="$HOME/.local/bin:$PATH"
export PYTHONUSERBASE="$HOME/.local"

# Create Termux-style directory structure for Python
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
TERMUX_PREFIX="$HOME/termux/data/data/com.termux/files/usr"
TERMUX_HOME="$HOME/termux/data/data/com.termux/files/home"

mkdir -p "$TERMUX_PREFIX/lib/python${PYTHON_VERSION}/site-packages"
mkdir -p "$TERMUX_PREFIX/bin"
mkdir -p "$TERMUX_HOME"

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

# Install basic packages that are commonly used in Termux
echo "Installing common Python packages..."
pip install --user requests numpy pandas matplotlib ipython pillow \
    beautifulsoup4 lxml cryptography flask django pytest \
    rich urllib3 pygments

# Create a pip wrapper with Termux-like behavior
cat > "$HOME/.local/bin/pip-termux" << 'EOF'
#!/bin/bash
# Wrapper for pip with Termux paths

# Set up environment variables
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
TERMUX_PREFIX="$HOME/termux/data/data/com.termux/files/usr"
export PYTHONPATH="$TERMUX_PREFIX/lib/python${PYTHON_VERSION}/site-packages:$PYTHONPATH"
export PYTHONUSERBASE="$HOME/.local"

# Execute pip command
pip3 "$@"

# Copy the installed packages to the Termux lib path if it's an installation
if [[ "$*" == *"install"* ]]; then
    # Wait a moment for files to be fully written
    sleep 1
    
    # Determine site-packages location
    if [ -d "$HOME/venv/lib/python${PYTHON_VERSION}/site-packages" ]; then
        SITE_PACKAGES="$HOME/venv/lib/python${PYTHON_VERSION}/site-packages"
    else
        SITE_PACKAGES="$HOME/.local/lib/python${PYTHON_VERSION}/site-packages"
    fi
    
    # Create Termux lib directory if it doesn't exist
    TERMUX_SITE_PACKAGES="$TERMUX_PREFIX/lib/python${PYTHON_VERSION}/site-packages"
    mkdir -p "$TERMUX_SITE_PACKAGES"
    
    # Create symbolic links from all packages to Termux directory
    ln -sf "$SITE_PACKAGES"/* "$TERMUX_SITE_PACKAGES/" 2>/dev/null || true
    
    echo "Python modules are also available in the Termux environment."
fi
EOF

chmod +x "$HOME/.local/bin/pip-termux"

# Create a Python launcher with Termux paths
cat > "$HOME/.local/bin/python-import" << 'EOF'
#!/bin/bash
# Run Python with correct import paths for Termux-like environment

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
TERMUX_PREFIX="$HOME/termux/data/data/com.termux/files/usr"

# Add all possible Python module locations to path
export PYTHONPATH="$TERMUX_PREFIX/lib/python${PYTHON_VERSION}/site-packages:$HOME/.local/lib/python${PYTHON_VERSION}/site-packages:$PYTHONPATH"

# Set user base to ensure pip installs packages in user space
export PYTHONUSERBASE="$HOME/.local"

if [ $# -eq 0 ]; then
    # Interactive mode
    echo "Python with Termux-like import paths (${PYTHON_VERSION})"
    python3
else
    # Run script with arguments
    python3 "$@"
fi
EOF

chmod +x "$HOME/.local/bin/python-import"

# Create a fix-python-shebang script to adjust Python scripts
cat > "$HOME/.local/bin/fix-python-shebang" << 'EOF'
#!/bin/bash
# Fix Python script shebangs to use python-import

if [ $# -ne 1 ]; then
    echo "Usage: $0 <python-script>"
    echo "Changes the shebang line to use python-import for proper module imports"
    exit 1
fi

SCRIPT="$1"

if [ ! -f "$SCRIPT" ]; then
    echo "Error: File not found: $SCRIPT"
    exit 1
fi

# Check if file has a Python shebang
if grep -q "^#!.*python" "$SCRIPT"; then
    # Replace the shebang with python-import
    sed -i "1s|^#!.*python.*|#!/usr/bin/env python-import|" "$SCRIPT"
    chmod +x "$SCRIPT"
    echo "Shebang updated in $SCRIPT to use python-import"
else
    # Add a shebang if none exists
    if ! grep -q "^#!" "$SCRIPT"; then
        sed -i "1i#!/usr/bin/env python-import" "$SCRIPT"
        chmod +x "$SCRIPT"
        echo "Shebang added to $SCRIPT to use python-import"
    else
        echo "File doesn't have a Python shebang: $SCRIPT"
    fi
fi
EOF

chmod +x "$HOME/.local/bin/fix-python-shebang"

# Set up the Termux environment
if [ -f "$HOME/.local/bin/setup-termux-env" ]; then
    echo "Setting up Termux-like environment..."
    bash "$HOME/.local/bin/setup-termux-env"
fi

echo "==============================================================="
echo "Python environment with Termux compatibility is ready!"
echo "==============================================================="
echo ""
echo "How to use Python with proper imports:"
echo "  python-import script.py      Run a Python script"
echo "  fix-python-shebang script.py Fix script shebang for imports"
echo ""
echo "How to install packages:"
echo "  pip-termux install PACKAGE   Install Python packages"
echo "  pkg install python-PACKAGE   Termux-style installation"
echo ""
echo "Your packages are available in both environments!"
echo "==============================================================="
