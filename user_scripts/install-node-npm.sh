#!/bin/bash
# Script to install Node.js and npm in user space

echo "Installing Node.js and npm for user..."

# Set up nvm (Node Version Manager) for user-level installation
export NVM_DIR="$HOME/.nvm"
mkdir -p "$NVM_DIR"

# Install nvm
curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.3/install.sh | bash

# Load nvm
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"

# Install latest LTS version of Node.js
echo "Installing Node.js LTS version..."
nvm install --lts

# Set default Node.js version
nvm alias default node

# Verify installation
echo "Node.js $(node -v) installed"
echo "npm $(npm -v) installed"

# Add nvm initialization to .bashrc if not already there
if ! grep -q "NVM_DIR" "$HOME/.bashrc"; then
    echo 'export NVM_DIR="$HOME/.nvm"' >> "$HOME/.bashrc"
    echo '[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"  # This loads nvm' >> "$HOME/.bashrc"
    echo '[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # This loads nvm bash_completion' >> "$HOME/.bashrc"
fi

echo "Node.js and npm are ready to use!"
echo "To install global packages, use: npm install -g PACKAGE_NAME"
echo "The installation is confined to your user space."
