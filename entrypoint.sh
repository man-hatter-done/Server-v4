#!/bin/bash
# Entrypoint script for Render deployment
set -e

echo "Initializing container-based terminal server..."

# Check if Docker socket is accessible
if [ ! -S /var/run/docker.sock ]; then
    echo "WARNING: Docker socket not found. Container mode will be disabled."
    export USE_CONTAINERS=false
else
    # Test Docker connection
    if ! docker info > /dev/null 2>&1; then
        echo "WARNING: Cannot connect to Docker. Container mode will be disabled."
        export USE_CONTAINERS=false
    else
        echo "Docker connection successful!"
        export USE_CONTAINERS=true
        
        # Build the multi-user container image
        echo "Building multi-user container image..."
        docker build -t terminal-multi-user:latest -f Dockerfile.multi-user .
        
        # Create docker volume for user data if it doesn't exist
        if ! docker volume inspect terminal-workspace > /dev/null 2>&1; then
            echo "Creating terminal-workspace volume..."
            docker volume create terminal-workspace
        fi
        
        echo "Container setup complete!"
    fi
fi

# Ensure all scripts are executable
chmod +x user_scripts/*
chmod +x container-scripts/*

# Create necessary directories
mkdir -p logs user_data
chmod 777 logs user_data

# Print configuration
echo "Server Configuration:"
echo "---------------------"
echo "USE_CONTAINERS: $USE_CONTAINERS"
echo "MAX_CONTAINERS: $MAX_CONTAINERS"
echo "USERS_PER_CONTAINER: $USERS_PER_CONTAINER"
echo "---------------------"

# Set startup message
cat > user_data/welcome.txt << 'EOL'
Welcome to the Terminal Server with Container Isolation!

This server provides a Linux command environment with:
- User isolation via containers
- Persistent file storage
- Python, Node.js, and other development tools

Try these commands:
- container-info   - Show your container and user info
- help             - Display available commands
- python3          - Run Python interpreter
- ls, cd, mkdir    - File management commands

Happy coding!
EOL

# Start the server
echo "Starting server..."

# Use Gunicorn for production
exec gunicorn --bind 0.0.0.0:3000 \
    --workers 4 \
    --threads 2 \
    --worker-class eventlet \
    --worker-connections 1000 \
    --timeout 120 \
    --keepalive 5 \
    --max-requests 1000 \
    --max-requests-jitter 50 \
    --log-level info \
    --access-logfile - \
    --error-logfile - \
    flask_server:app
