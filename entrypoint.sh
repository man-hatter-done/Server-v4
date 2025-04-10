#!/bin/bash
# Entrypoint script for Render deployment
set -e

echo "Initializing container-based terminal server..."

# Start a simple server immediately on the required port 
# This ensures Render detects an open port during initial health checks
echo "Starting temporary server on port 3000..."
python3 -c "
import socket, threading, time, os
def handle_conn(conn):
    conn.send(b'HTTP/1.1 200 OK\\r\\nContent-Type: text/plain\\r\\nContent-Length: 19\\r\\n\\r\\nServer initializing.')
    conn.close()
s = socket.socket()
s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
try:
    s.bind(('0.0.0.0', int(os.environ.get('PORT', 3000))))
    s.listen(5)
    print('Temporary server listening on port ' + str(os.environ.get('PORT', 3000)))
    threading.Thread(target=lambda: [
        handle_conn(conn) for conn, _ in iter(lambda: s.accept(), None)
    ], daemon=True).start()
except Exception as e:
    print('Failed to start temporary server:', e)
" &
TEMP_SERVER_PID=$!
# Give temporary server time to start
sleep 2

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
echo "PORT: $PORT" 
echo "USE_CONTAINERS: $USE_CONTAINERS"
echo "MULTI_CONTAINER_MODE: $MULTI_CONTAINER_MODE"
echo "MAX_CONTAINERS: $MAX_CONTAINERS"
echo "USERS_PER_CONTAINER: $USERS_PER_CONTAINER"
echo "---------------------"
echo "Network information:"
echo "--------------------"
ip addr || echo "ip command not available"
netstat -tulpn || echo "netstat command not available"
echo "--------------------"

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

# Stop the temporary server
if [ -n "$TEMP_SERVER_PID" ]; then
    echo "Stopping temporary server..."
    kill $TEMP_SERVER_PID || true
fi

# Start the server
echo "Starting server on 0.0.0.0:${PORT:-3000}..."

# Use Gunicorn for production with socket optimization
exec gunicorn --bind "0.0.0.0:${PORT:-3000}" \
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
