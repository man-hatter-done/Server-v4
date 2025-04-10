#!/bin/bash
# Entrypoint script for Render deployment with Socket.IO support
set -e

echo "Initializing terminal server with WebSocket support..."

# Set PORT environment variable if not set
export PORT=${PORT:-3000}

# Check if port is available before starting
echo "Checking if port $PORT is available..."
if command -v netstat > /dev/null; then
    netstat -tuln | grep ":$PORT " && echo "WARNING: Port $PORT may be in use. Will try to use it anyway." || echo "Port $PORT appears to be available"
elif command -v ss > /dev/null; then
    ss -tuln | grep ":$PORT " && echo "WARNING: Port $PORT may be in use. Will try to use it anyway." || echo "Port $PORT appears to be available"
else
    echo "Unable to check port availability - missing netstat/ss tools"
fi

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
        
        # Build the multi-user container image
        if [ "$USE_CONTAINERS" = "true" ]; then
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
fi

# Ensure all scripts are executable
chmod +x user_scripts/* 2>/dev/null || true
chmod +x container-scripts/* 2>/dev/null || true

# Create necessary directories
mkdir -p logs user_data
chmod 777 logs user_data

# Print configuration
echo "Server Configuration:"
echo "---------------------"
echo "PORT: $PORT" 
echo "USE_CONTAINERS: $USE_CONTAINERS"
echo "MULTI_CONTAINER_MODE: $MULTI_CONTAINER_MODE"
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

# Start the server using Flask-SocketIO's built-in server
echo "Starting Socket.IO server on port $PORT..."

# Run with additional diagnostic output
python3 -u run.py
