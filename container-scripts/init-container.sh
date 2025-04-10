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
