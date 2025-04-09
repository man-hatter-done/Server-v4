#!/bin/bash
# Setup script for iOS Terminal server

# Ensure we're running with appropriate permissions
if [ "$EUID" -ne 0 ]; then
  echo "Please run this script with sudo or as root"
  exit 1
fi

echo "===== iOS Terminal Server Setup ====="
echo "This script will prepare your system to run the iOS Terminal server"

# Create a user for running the terminal service
if ! id -u terminal-service >/dev/null 2>&1; then
  echo "Creating terminal-service user..."
  useradd -m -s /bin/bash terminal-service
else
  echo "terminal-service user already exists"
fi

# Install required system packages
echo "Installing required system packages..."
apt-get update
apt-get install -y \
  docker.io \
  docker-compose \
  python3 \
  python3-pip \
  python3-venv \
  build-essential \
  curl \
  wget \
  git \
  sudo

# Install Python requirements
echo "Installing Python requirements..."
pip3 install -r requirements.txt

# Set up terminal-service user with Docker permissions
echo "Setting up Docker permissions..."
usermod -aG docker terminal-service

# Create data directories
echo "Creating data directories..."
mkdir -p user_data logs
chown -R terminal-service:terminal-service user_data logs

# Set up systemd service for auto-starting
echo "Setting up systemd service..."
cat > /etc/systemd/system/ios-terminal.service << EOF
[Unit]
Description=iOS Terminal Server
After=network.target docker.service
Requires=docker.service

[Service]
User=terminal-service
Group=terminal-service
WorkingDirectory=$(pwd)
ExecStart=/usr/bin/docker-compose up
ExecStop=/usr/bin/docker-compose down
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and enable service
systemctl daemon-reload
systemctl enable ios-terminal.service

echo ""
echo "===== Setup Complete ====="
echo "To start the service, run: systemctl start ios-terminal"
echo "To check status, run: systemctl status ios-terminal"
echo ""
echo "The terminal server will be available at: http://YOUR_IP:3000"
