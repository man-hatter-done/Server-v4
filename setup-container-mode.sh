#!/bin/bash
# Setup script for container-based user isolation mode

echo "Setting up container-based isolation mode..."

# Create necessary directories
mkdir -p container-scripts
mkdir -p logs

# Create user creation script
cat > container-scripts/create-user.sh << 'EOF'
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
cat > "/home/$USERNAME/.bashrc" << 'BASHRC'
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
BASHRC

chown "$USERNAME:$USERNAME" "/home/$USERNAME/.bashrc"

# Create user's workspace symlink
ln -sf "$USER_WORKSPACE" "/home/$USERNAME/workspace"
chown -h "$USERNAME:$USERNAME" "/home/$USERNAME/workspace"

# Create a profile file to avoid locale warnings
cat > "/home/$USERNAME/.profile" << 'PROFILE'
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
PROFILE

chown "$USERNAME:$USERNAME" "/home/$USERNAME/.profile"

echo "User $USERNAME created successfully with user ID $USERID"
EOF

# Create container initialization script
cat > container-scripts/init-container.sh << 'EOF'
#!/bin/bash
# Container initialization script
# This runs when the container starts and keeps it alive

echo "Initializing multi-user terminal container"

# Create the workspace directory if it doesn't exist
if [ ! -d "/workspace" ]; then
    mkdir -p /workspace
    chmod 711 /workspace
    echo "Created workspace directory"
fi

# Ensure shared_scripts directory has the right permissions
if [ -d "/shared_scripts" ]; then
    chmod -R +x /shared_scripts
    echo "Set executable permissions on shared scripts"
fi

# Configure SSH for management (optional)
if [ -f "/etc/ssh/sshd_config" ]; then
    # Set up SSH config for better security
    sed -i 's/#PasswordAuthentication yes/PasswordAuthentication no/' /etc/ssh/sshd_config
    sed -i 's/#PermitRootLogin prohibit-password/PermitRootLogin no/' /etc/ssh/sshd_config
    
    # Create SSH host keys if they don't exist
    if [ ! -f "/etc/ssh/ssh_host_rsa_key" ]; then
        ssh-keygen -A
    fi
    
    # Start SSH service
    service ssh start
    echo "SSH service started"
fi

# Display system information
echo "Container information:"
echo "----------------------"
echo "Hostname: $(hostname)"
echo "CPU: $(grep "model name" /proc/cpuinfo | head -n1 | cut -d: -f2 | sed 's/^[ \t]*//')"
echo "Memory: $(free -h | grep Mem | awk '{print $2}')"
echo "Disk space: $(df -h / | grep / | awk '{print $4}') available"
echo "----------------------"

echo "Container is ready for users"

# Keep container running indefinitely
while true; do
    sleep 3600 &
    wait $!
done
EOF

# Make scripts executable
chmod +x container-scripts/create-user.sh
chmod +x container-scripts/init-container.sh

echo "Container scripts created successfully."
echo "To start in container mode, run: docker-compose -f docker-compose-multi-user.yml up -d"
