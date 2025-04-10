#!/bin/bash
# Script to create a new user with proper isolation in a shared container

# Usage: create-user.sh <username> <userid>
USERNAME=$1
USERID=$2

# Exit if parameters missing
if [ -z "$USERNAME" ] || [ -z "$USERID" ]; then
    echo "Error: Missing parameters"
    echo "Usage: create-user.sh <username> <userid>"
    exit 1
fi

# Check if user exists
if id "$USERNAME" &>/dev/null; then
    echo "User $USERNAME already exists"
    exit 0
fi

# Create user with specific UID for consistency
useradd -m -s /bin/bash -u $USERID $USERNAME

# Set a random password
PASSWORD=$(openssl rand -base64 12)
echo "$USERNAME:$PASSWORD" | chpasswd

# Create user workspace in isolated directory
USER_WORKSPACE="/workspace/$USERNAME"
mkdir -p "$USER_WORKSPACE"
chown "$USERNAME:$USERNAME" "$USER_WORKSPACE"
chmod 700 "$USER_WORKSPACE"

# Create .ssh directory
mkdir -p "/home/$USERNAME/.ssh"
chmod 700 "/home/$USERNAME/.ssh"
chown "$USERNAME:$USERNAME" "/home/$USERNAME/.ssh"

# Create .local/bin directory for user scripts
mkdir -p "/home/$USERNAME/.local/bin"
chown -R "$USERNAME:$USERNAME" "/home/$USERNAME/.local"
chmod 755 "/home/$USERNAME/.local/bin"

# Copy shared scripts to user's bin directory
cp /shared_scripts/* "/home/$USERNAME/.local/bin/" 2>/dev/null || true
chmod +x "/home/$USERNAME/.local/bin/"* 2>/dev/null || true
chown "$USERNAME:$USERNAME" "/home/$USERNAME/.local/bin/"* 2>/dev/null || true

# Create bashrc with proper environment
cat > "/home/$USERNAME/.bashrc" << 'EOF'
# User .bashrc
export PATH="$HOME/.local/bin:$PATH"
export LANG=C.UTF-8
export PYTHONUSERBASE="$HOME/.local"

# Set a colorful prompt with current directory
PS1='\[\033[01;32m\]\u@terminal\[\033[00m\]:\[\033[01;34m\]\w\[\033[00m\]\$ '

# Useful aliases
alias ls='ls --color=auto'
alias ll='ls -la'
alias grep='grep --color=auto'

# Start in user workspace
cd $HOME/workspace
EOF

chown "$USERNAME:$USERNAME" "/home/$USERNAME/.bashrc"

# Create user's workspace symlink
ln -sf "$USER_WORKSPACE" "/home/$USERNAME/workspace"
chown -h "$USERNAME:$USERNAME" "/home/$USERNAME/workspace"

# Create a profile file to avoid locale warnings
cat > "/home/$USERNAME/.profile" << 'EOF'
# ~/.profile: executed by the command interpreter for login shells.

# Set locale with fallback
export LANG=C.UTF-8 2>/dev/null || export LANG=C
export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

# Source bashrc if it exists
if [ -n "$BASH_VERSION" ]; then
    if [ -f "$HOME/.bashrc" ]; then
        . "$HOME/.bashrc"
    fi
fi

# Set PATH for local binaries
if [ -d "$HOME/.local/bin" ] ; then
    PATH="$HOME/.local/bin:$PATH"
fi
EOF

chown "$USERNAME:$USERNAME" "/home/$USERNAME/.profile"

echo "User $USERNAME created successfully with user ID $USERID"
