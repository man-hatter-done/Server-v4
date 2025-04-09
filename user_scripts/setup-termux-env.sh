#!/bin/bash
# Script to set up a Termux-like environment in the user's home directory

echo "Setting up Termux-like environment structure..."

# Create Termux-style directory structure
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/bin"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/lib"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/include"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/share"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/etc"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/tmp"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/var"
mkdir -p "$HOME/termux/data/data/com.termux/files/home"

# Create symlinks to the actual home directory
ln -sf "$HOME" "$HOME/termux/data/data/com.termux/files/home/storage"

# Create symlinks for Python to find modules properly
PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/lib/python${PYTHON_VERSION}"
mkdir -p "$HOME/termux/data/data/com.termux/files/usr/lib/python${PYTHON_VERSION}/site-packages"

# If we have a virtual environment, link its site-packages
if [ -d "$HOME/venv" ]; then
    # Link site-packages
    if [ -d "$HOME/venv/lib/python${PYTHON_VERSION}/site-packages" ]; then
        ln -sf "$HOME/venv/lib/python${PYTHON_VERSION}/site-packages/"* \
               "$HOME/termux/data/data/com.termux/files/usr/lib/python${PYTHON_VERSION}/site-packages/" 2>/dev/null || true
    fi
    
    # Link Python binary
    ln -sf "$HOME/venv/bin/python" \
           "$HOME/termux/data/data/com.termux/files/usr/bin/python" 2>/dev/null || true
    ln -sf "$HOME/venv/bin/python3" \
           "$HOME/termux/data/data/com.termux/files/usr/bin/python3" 2>/dev/null || true
fi

# Link local bin to usr/bin for commands
mkdir -p "$HOME/.local/bin"
ln -sf "$HOME/.local/bin/"* "$HOME/termux/data/data/com.termux/files/usr/bin/" 2>/dev/null || true

# Create the pkg command
cat > "$HOME/.local/bin/pkg" << 'EOF'
#!/bin/bash
# Simulated Termux pkg command

PKG_DB_DIR="$HOME/.pkg"
PKG_INSTALLED_FILE="$PKG_DB_DIR/installed.txt"

# Create pkg database directory if it doesn't exist
mkdir -p "$PKG_DB_DIR"
touch "$PKG_INSTALLED_FILE"

print_help() {
    echo "Usage: pkg command [arguments]"
    echo ""
    echo "Commands:"
    echo "  install [packages]    Install specified packages"
    echo "  uninstall [packages]  Uninstall specified packages"
    echo "  reinstall [packages]  Reinstall specified packages"
    echo "  update                Update package lists"
    echo "  upgrade               Upgrade installed packages"
    echo "  list-installed        List installed packages"
    echo "  list-all              List all available packages"
    echo "  search [query]        Search for packages"
    echo "  help                  Show this help"
    echo ""
    echo "This is a simulated 'pkg' command to provide a Termux-like experience."
}

pkg_install() {
    if [ -z "$1" ]; then
        echo "Error: No package specified for installation"
        return 1
    fi
    
    echo "Installing package: $1"
    
    case "$1" in
        python | python3)
            echo "Python is already installed by default."
            ;;
        python-numpy | python-pandas | python-matplotlib | python-scipy | python-sklearn)
            # Extract the package name after python-
            PKG=${1#python-}
            echo "Installing Python package $PKG via pip..."
            pip install --user "$PKG"
            ;;
        nodejs | node)
            echo "Installing Node.js..."
            if [ -f "$HOME/.local/bin/install-node-npm" ]; then
                bash "$HOME/.local/bin/install-node-npm"
            else
                echo "Node.js installer not found. Please use the 'install-node' command."
            fi
            ;;
        git)
            echo "Git is already installed by default."
            ;;
        vim | nano | emacs)
            echo "$1 is already installed by default."
            ;;
        gcc | clang)
            echo "Note: $1 is simulated and runs in a container environment."
            echo "For full compilation support, please use the native app."
            ;;
        *)
            echo "Note: This is a simulated environment. Package '$1' is marked as installed,"
            echo "but it may not actually function as in a real Termux environment."
            ;;
    esac
    
    # Mark as installed in our database
    if ! grep -q "^$1$" "$PKG_INSTALLED_FILE"; then
        echo "$1" >> "$PKG_INSTALLED_FILE"
    fi
    
    echo "Package $1 installed successfully."
}

pkg_uninstall() {
    if [ -z "$1" ]; then
        echo "Error: No package specified for uninstallation"
        return 1
    fi
    
    echo "Removing package: $1"
    
    # Remove from installed list
    if grep -q "^$1$" "$PKG_INSTALLED_FILE"; then
        grep -v "^$1$" "$PKG_INSTALLED_FILE" > "$PKG_INSTALLED_FILE.tmp"
        mv "$PKG_INSTALLED_FILE.tmp" "$PKG_INSTALLED_FILE"
        echo "Package $1 uninstalled successfully."
    else
        echo "Package $1 is not installed."
    fi
}

pkg_list_installed() {
    echo "Installed packages:"
    if [ -s "$PKG_INSTALLED_FILE" ]; then
        cat "$PKG_INSTALLED_FILE"
    else
        echo "No packages installed yet."
    fi
}

pkg_update() {
    echo "Updating package lists..."
    echo "Package lists updated. Simulated operation in web terminal environment."
}

pkg_upgrade() {
    echo "Upgrading installed packages..."
    echo "All packages upgraded. Simulated operation in web terminal environment."
}

pkg_list_all() {
    echo "Available packages (common packages):"
    echo "python python3 python-numpy python-pandas python-matplotlib"
    echo "nodejs git ruby vim nano wget curl gcc clang"
    echo "openssh tmux zsh sqlite3 libsqlite perl"
    echo ""
    echo "Note: This is a simplified list for simulation purposes."
}

pkg_search() {
    if [ -z "$1" ]; then
        echo "Error: No search query provided"
        return 1
    fi
    
    echo "Searching for packages matching '$1':"
    pkg_list_all | grep -i "$1"
}

# Main command processing
CMD="$1"
shift

case "$CMD" in
    install)
        for pkg in "$@"; do
            pkg_install "$pkg"
        done
        ;;
    uninstall)
        for pkg in "$@"; do
            pkg_uninstall "$pkg"
        done
        ;;
    reinstall)
        for pkg in "$@"; do
            pkg_uninstall "$pkg"
            pkg_install "$pkg"
        done
        ;;
    update)
        pkg_update
        ;;
    upgrade)
        pkg_upgrade
        ;;
    list-installed)
        pkg_list_installed
        ;;
    list-all)
        pkg_list_all
        ;;
    search)
        pkg_search "$1"
        ;;
    help|--help|-h)
        print_help
        ;;
    *)
        echo "Unknown command: $CMD"
        print_help
        exit 1
        ;;
esac
EOF

# Make the pkg command executable
chmod +x "$HOME/.local/bin/pkg"

# Create the termux-setup-storage command simulation
cat > "$HOME/.local/bin/termux-setup-storage" << 'EOF'
#!/bin/bash
# Simulated termux-setup-storage command

echo "Simulating storage access setup for Termux..."
mkdir -p "$HOME/storage/shared"
mkdir -p "$HOME/storage/dcim"
mkdir -p "$HOME/storage/downloads"
mkdir -p "$HOME/storage/music"
mkdir -p "$HOME/storage/pictures"
mkdir -p "$HOME/storage/videos"

echo "Storage access has been set up. You can access your files at:"
echo "~/storage/*"
echo ""
echo "Note: This is a simulated environment. Actual file access depends on server configuration."
EOF

chmod +x "$HOME/.local/bin/termux-setup-storage"

# Create a simulated .termux directory with common configuration
mkdir -p "$HOME/.termux"
touch "$HOME/.termux/termux.properties"

# Create a wrapper script to use the Termux environment
cat > "$HOME/.local/bin/termux" << 'EOF'
#!/bin/bash
# Wrapper to run commands in the Termux-like environment

export PREFIX="$HOME/termux/data/data/com.termux/files/usr"
export HOME_TERMUX="$HOME/termux/data/data/com.termux/files/home"
export PATH="$PREFIX/bin:$PATH"
export LD_LIBRARY_PATH="$PREFIX/lib"
export PYTHONPATH="$PREFIX/lib/python$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)/site-packages"

if [ $# -eq 0 ]; then
    # Interactive mode - start a shell in the Termux environment
    echo "Entering Termux-like environment. Type 'exit' to return to normal shell."
    cd "$HOME_TERMUX"
    PS1="Termux ~ $ " bash
else
    # Execute the specified command in the Termux environment
    cd "$HOME_TERMUX"
    "$@"
fi
EOF

chmod +x "$HOME/.local/bin/termux"

# Create a Python wrapper to ensure proper paths
cat > "$HOME/.local/bin/python-termux" << 'EOF'
#!/bin/bash
# Wrapper to run Python with Termux-like paths

export PREFIX="$HOME/termux/data/data/com.termux/files/usr"
export PYTHONPATH="$PREFIX/lib/python$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1-2)/site-packages:$PYTHONPATH"

if [ $# -eq 0 ]; then
    # Interactive mode
    python3
else
    # Run with arguments
    python3 "$@"
fi
EOF

chmod +x "$HOME/.local/bin/python-termux"

echo "Termux-like environment has been set up successfully!"
echo ""
echo "Available commands:"
echo "  pkg               - Package management like in Termux"
echo "  termux            - Enter Termux-like environment"
echo "  python-termux     - Run Python with Termux-like paths"
echo "  termux-setup-storage - Simulate setting up storage access"
echo ""
echo "To start using the Termux-like environment, type: termux"
echo "To run Python with proper imports, use: python-termux script.py"
echo ""
echo "You can install packages with: pkg install <package>"
