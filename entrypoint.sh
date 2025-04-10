#!/bin/bash
# Entrypoint script for Render deployment
set -e

echo "Initializing container-based terminal server..."

# Start a simple server immediately on the required port 
# This ensures Render detects an open port during initial health checks
PORT=${PORT:-8080}  # Default to 8080 instead of 3000

echo "Starting temporary server on port $PORT..."
python3 -c "
import socket, threading, time, os, sys

def handle_conn(conn, addr):
    print(f'Connection from {addr}')
    try:
        conn.send(b'HTTP/1.1 200 OK\\r\\nContent-Type: text/plain\\r\\nContent-Length: 19\\r\\n\\r\\nServer initializing.')
    except Exception as e:
        print(f'Error handling connection: {e}')
    finally:
        conn.close()

def try_bind_port(port):
    try:
        s = socket.socket()
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('0.0.0.0', port))
        s.listen(5)
        print(f'Temporary server listening on port {port}')
        return s
    except Exception as e:
        print(f'Failed to bind to port {port}: {e}')
        return None

# Try the requested port, then fallbacks if needed
port = int(os.environ.get('PORT', $PORT))
server_socket = try_bind_port(port)

# If main port failed, try fallback ports
if not server_socket and port != 8080:
    print('Trying fallback port 8080')
    server_socket = try_bind_port(8080)
    
if not server_socket and port != 8000:
    print('Trying fallback port 8000')
    server_socket = try_bind_port(8000)

if not server_socket:
    print('Could not bind to any port. Health check will fail.')
    # Keep running so the script doesn't exit
    while True:
        time.sleep(10)
        
# Start serving
def serve():
    while True:
        try:
            conn, addr = server_socket.accept()
            threading.Thread(target=handle_conn, args=(conn, addr), daemon=True).start()
        except Exception as e:
            print(f'Error accepting connection: {e}')
            time.sleep(0.1)

threading.Thread(target=serve, daemon=True).start()
print('Temporary server thread started')
" &
TEMP_SERVER_PID=$!

# Give temporary server time to start
echo "Waiting for temporary server to start (PID: $TEMP_SERVER_PID)..."
sleep 3

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

# Stop the temporary server more forcefully
if [ -n "$TEMP_SERVER_PID" ]; then
    echo "Stopping temporary server (PID: $TEMP_SERVER_PID)..."
    kill -9 $TEMP_SERVER_PID 2>/dev/null || true
    sleep 2  # Give it time to fully release the port
    
    # Verify the process is gone
    if kill -0 $TEMP_SERVER_PID 2>/dev/null; then
        echo "WARNING: Temporary server process still exists after kill attempt"
    else
        echo "Temporary server process successfully stopped"
    fi
fi

# Check if the port is already in use
PORT=${PORT:-3000}
echo "Checking if port $PORT is available..."
if command -v netstat > /dev/null; then
    netstat -tuln | grep ":$PORT " && echo "WARNING: Port $PORT is already in use!" || echo "Port $PORT appears to be available"
elif command -v ss > /dev/null; then
    ss -tuln | grep ":$PORT " && echo "WARNING: Port $PORT is already in use!" || echo "Port $PORT appears to be available"
elif command -v lsof > /dev/null; then
    lsof -i :$PORT && echo "WARNING: Port $PORT is already in use!" || echo "Port $PORT appears to be available"
else
    echo "Unable to check port availability - missing netstat/ss/lsof tools"
fi

# Try to clean up any stale socket files
if [ -S ".gunicorn.sock" ]; then
    echo "Removing stale Gunicorn socket file"
    rm -f .gunicorn.sock
fi

# Start the server
echo "Starting server on 0.0.0.0:$PORT and 127.0.0.1:$PORT..."

# Use Gunicorn with better error handling and try backup ports if needed
start_gunicorn() {
    local bind_port=$1
    echo "Attempting to start Gunicorn on port $bind_port..."
    
    # Try to start Gunicorn
    gunicorn --bind "0.0.0.0:$bind_port" --bind "127.0.0.1:$bind_port" \
        --workers 4 \
        --threads 2 \
        --worker-class eventlet \
        --worker-connections 1000 \
        --timeout 120 \
        --keepalive 5 \
        --max-requests 1000 \
        --max-requests-jitter 50 \
        --log-level debug \
        --access-logfile - \
        --error-logfile - \
        --capture-output \
        flask_server:app
    
    return $?
}

# Try the main port first, then fallback ports if needed
for try_port in $PORT 8080 8000; do
    echo "Trying port $try_port..."
    start_gunicorn $try_port
    
    if [ $? -eq 0 ]; then
        echo "Server started successfully on port $try_port"
        break
    else
        echo "Failed to start on port $try_port, trying next port..."
        sleep 1
    fi
done
