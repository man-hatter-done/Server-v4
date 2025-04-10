#!/bin/bash
# Setup script for installing required dependencies

echo "Installing dependencies for container-based terminal server..."

# Check if pip is installed
if ! command -v pip &> /dev/null; then
    echo "pip is not installed. Installing pip..."
    if command -v apt-get &> /dev/null; then
        sudo apt-get update
        sudo apt-get install -y python3-pip
    elif command -v yum &> /dev/null; then
        sudo yum install -y python3-pip
    else
        echo "Could not install pip. Please install manually."
        exit 1
    fi
fi

# Install Docker Python library
echo "Installing Docker Python library..."
pip install docker

# Check if docker is installed
if ! command -v docker &> /dev/null; then
    echo "Docker is not installed. Please install Docker to use container mode."
    echo "Visit https://docs.docker.com/get-docker/ for installation instructions."
    exit 1
fi

# Make container scripts directory
mkdir -p container-scripts

echo "Dependencies installed successfully."
echo "To set up container mode, run: ./setup-container-mode.sh"
