#!/usr/bin/env python3
"""
Main entry point for the Enhanced iOS Terminal Server
Uses the redesigned terminal emulation with integrated file operations
"""

import os
import sys
import signal
import logging
import eventlet
import threading
import time
import gc

# Create logs directory if it doesn't exist
os.makedirs("logs", exist_ok=True)

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - run_enhanced_server.py - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/run_enhanced.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("run_enhanced")

# Set eventlet as the async mode before importing Flask-SocketIO components
os.environ['EVENTLET_NO_GREENDNS'] = '1'  # Avoid DNS resolution issues
eventlet.monkey_patch()

# Define signal handlers for graceful shutdown
def handle_sigterm(signum, frame):
    """Handle SIGTERM signal for graceful shutdown"""
    logger.info("Received SIGTERM, shutting down gracefully")
    sys.exit(0)

def handle_sigint(signum, frame):
    """Handle SIGINT signal for graceful shutdown"""
    logger.info("Received SIGINT, shutting down gracefully")
    sys.exit(0)

def handle_sigusr1(signum, frame):
    """Handle SIGUSR1 signal for memory optimization"""
    logger.warning("Received SIGUSR1 - performing memory optimization")
    gc.collect()  # Force garbage collection
    
    # Log memory stats
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        logger.info(f"Memory usage after collection: {memory_info.rss / (1024*1024):.2f} MB")
    except (ImportError, Exception) as e:
        logger.error(f"Error getting memory stats: {e}")

# Register signal handlers
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGUSR1, handle_sigusr1)

# Periodic memory monitor function
def monitor_memory():
    """Monitor memory usage and take action if needed"""
    try:
        import psutil
        MEMORY_WARNING_THRESHOLD = 75  # percent
        MEMORY_CRITICAL_THRESHOLD = 90  # percent
        MEMORY_CHECK_INTERVAL = 60  # seconds
        
        while True:
            try:
                # Check system memory
                memory = psutil.virtual_memory()
                process = psutil.Process(os.getpid())
                
                # Log memory usage
                logger.info(f"Memory usage: {memory.percent:.1f}% (Process: {process.memory_info().rss / (1024*1024):.2f} MB)")
                
                if memory.percent > MEMORY_CRITICAL_THRESHOLD:
                    logger.critical(f"CRITICAL MEMORY ALERT: {memory.percent:.1f}% used!")
                    logger.info("Running aggressive garbage collection")
                    gc.collect()
                    
                elif memory.percent > MEMORY_WARNING_THRESHOLD:
                    logger.warning(f"Memory usage high: {memory.percent:.1f}% used")
                    gc.collect()
                
                # Sleep interval
                time.sleep(MEMORY_CHECK_INTERVAL)
                    
            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
                time.sleep(MEMORY_CHECK_INTERVAL)
                
    except ImportError:
        logger.warning("psutil not installed - memory monitoring disabled")

def run_server():
    """Run the Flask app with Socket.IO support"""
    # Start memory monitoring in a separate thread
    try:
        memory_thread = threading.Thread(target=monitor_memory, daemon=True)
        memory_thread.start()
        logger.info("Started memory monitoring thread")
    except Exception as e:
        logger.error(f"Error starting memory monitoring: {e}")
    
    # Log system information
    logger.info(f"Starting server with PID {os.getpid()}")
    logger.info(f"Python version: {sys.version}")
    
    try:
        # Import the enhanced server module
        from enhanced_flask_server import app, socketio
        
        # Get port from environment or use default
        port = int(os.environ.get('PORT', 3000))
        
        # Enable debug mode if requested
        debug = os.environ.get('DEBUG', 'False').lower() == 'true'
        
        logger.info(f"Starting Enhanced iOS Terminal Server")
        logger.info(f"Port: {port}")
        logger.info(f"Debug mode: {debug}")
        logger.info(f"WebSocket mode: {socketio.async_mode}")
        
        # Start the socketio server
        socketio.run(
            app,
            host="0.0.0.0",
            port=port,
            debug=debug,
            use_reloader=debug,
            log_output=True,
            allow_unsafe_werkzeug=True  # Allow running in production
        )
    except Exception as e:
        logger.critical(f"Failed to start server: {str(e)}")
        # Print the error to stderr as well for immediate visibility
        print(f"ERROR: Failed to start server: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    # Set up thread debugging for eventlet if in debug mode
    if os.environ.get('DEBUG', 'False').lower() == 'true':
        eventlet.debug.hub_prevent_multiple_readers(False)
        eventlet.debug.hub_exceptions(True)
    
    run_server()
