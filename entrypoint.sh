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

# Add memory monitoring
echo "Setting up memory monitoring..."
if command -v python3 >/dev/null 2>&1; then
    # Create a simple memory monitor script
    cat > memory_monitor.py << 'EOL'
#!/usr/bin/env python3
import time
import os
import psutil
import logging
import gc
import signal
import sys

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - MemoryMonitor - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/memory_monitor.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("memory_monitor")

# Memory thresholds (percentages)
WARNING_THRESHOLD = 80
CRITICAL_THRESHOLD = 90
EMERGENCY_THRESHOLD = 95

def format_bytes(bytes):
    """Format bytes to human-readable size"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes < 1024 or unit == 'GB':
            return f"{bytes:.2f} {unit}"
        bytes /= 1024

def monitor_memory():
    """Monitor memory usage and take actions if thresholds are reached"""
    try:
        process = psutil.Process(os.getpid())
        parent_process = psutil.Process(os.getppid())
        
        while True:
            # Get memory info
            system_memory = psutil.virtual_memory()
            process_memory = process.memory_info()
            
            memory_percent = system_memory.percent
            available_mb = system_memory.available / (1024 * 1024)
            process_mb = process_memory.rss / (1024 * 1024)
            
            logger.info(f"Memory: {memory_percent:.1f}% used, {format_bytes(system_memory.available)} available, Process using {format_bytes(process_memory.rss)}")
            
            # Take action based on memory usage
            if memory_percent > EMERGENCY_THRESHOLD:
                logger.critical(f"EMERGENCY: Memory usage at {memory_percent:.1f}%! Taking emergency actions...")
                # Force garbage collection
                gc.collect()
                # Notify the parent process to restart
                os.kill(parent_process.pid, signal.SIGUSR1)
                
            elif memory_percent > CRITICAL_THRESHOLD:
                logger.warning(f"CRITICAL: Memory usage at {memory_percent:.1f}%! Running aggressive garbage collection...")
                # Force garbage collection
                gc.collect()
                # Signal the main app to clear caches
                os.kill(parent_process.pid, signal.SIGUSR2)
                
            elif memory_percent > WARNING_THRESHOLD:
                logger.warning(f"WARNING: Memory usage at {memory_percent:.1f}%! Running garbage collection...")
                # Regular garbage collection
                gc.collect()
            
            # Adjust monitoring interval based on memory pressure
            if memory_percent > CRITICAL_THRESHOLD:
                time.sleep(10)  # Check more frequently under high memory
            else:
                time.sleep(60)  # Normal monitoring interval
                
    except Exception as e:
        logger.error(f"Memory monitoring error: {str(e)}")
        time.sleep(60)  # Wait before trying again
        monitor_memory()  # Restart monitoring

if __name__ == "__main__":
    logger.info("Memory monitor started")
    monitor_memory()
EOL

    # Make it executable
    chmod +x memory_monitor.py

    # Start memory monitor in the background
    echo "Starting memory monitor..."
    python3 memory_monitor.py &
fi

# Run with additional diagnostic output
echo "Starting main server application..."
python3 -u run.py
