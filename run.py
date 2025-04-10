#!/usr/bin/env python3
"""
Main entry point for the iOS Terminal Server
Supports both traditional HTTP and WebSocket functionality
Enhanced with memory monitoring, error handling, and improved stability
"""

import os
import sys
import signal
import logging
import eventlet
import gc
import threading
import time
from threading import Thread
from flask_socketio import SocketIO

# Create logs directory if it doesn't exist
try:
    os.makedirs("logs", exist_ok=True)
    # Ensure directory has proper permissions
    os.chmod("logs", 0o777)
except Exception as e:
    print(f"WARNING: Could not create or set permissions on logs directory: {e}")
    print("The entrypoint.sh script should have already created this directory.")

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - run.py - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("logs/run.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("run")

# Memory monitoring constants
MEMORY_CHECK_INTERVAL = 60  # seconds
MEMORY_WARNING_THRESHOLD = 75  # percent
MEMORY_CRITICAL_THRESHOLD = 90  # percent

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

def handle_sigusr2(signum, frame):
    """Handle SIGUSR2 signal for stats reporting"""
    logger.info("Received SIGUSR2 - producing stats report")
    
    # Report on cache if available
    try:
        from flask_server import response_cache, response_cache_hits, response_cache_misses
        total_requests = response_cache_hits + response_cache_misses
        hit_rate = response_cache_hits / total_requests if total_requests > 0 else 0
        logger.info(f"Cache stats: {len(response_cache)} entries, {hit_rate:.2%} hit rate")
    except (ImportError, Exception) as e:
        logger.warning(f"Could not get cache stats: {e}")
    
    # Report on memory
    try:
        import psutil
        process = psutil.Process(os.getpid())
        memory_info = process.memory_info()
        logger.info(f"Memory usage: {memory_info.rss / (1024*1024):.2f} MB")
        logger.info(f"Open files: {len(process.open_files())}")
        logger.info(f"Threads: {process.num_threads()}")
        logger.info(f"CPU usage: {process.cpu_percent(interval=1.0):.2f}%")
    except (ImportError, Exception) as e:
        logger.warning(f"Could not get process stats: {e}")

# Register signal handlers
signal.signal(signal.SIGTERM, handle_sigterm)
signal.signal(signal.SIGINT, handle_sigint)
signal.signal(signal.SIGUSR1, handle_sigusr1)
signal.signal(signal.SIGUSR2, handle_sigusr2)

# Periodic memory monitor function
def monitor_memory():
    """Monitor memory usage and take action if needed"""
    try:
        import psutil
        while True:
            try:
                # Check system memory
                memory = psutil.virtual_memory()
                process = psutil.Process(os.getpid())
                
                # Log memory usage
                if memory.percent > MEMORY_CRITICAL_THRESHOLD:
                    logger.critical(f"CRITICAL MEMORY ALERT: {memory.percent:.1f}% used!")
                    logger.critical(f"Process using {process.memory_info().rss / (1024*1024):.2f} MB")
                    
                    # Run aggressive garbage collection
                    logger.info("Running aggressive garbage collection")
                    gc.collect()
                    
                    # Clear caches to free memory
                    try:
                        from flask_server import response_cache
                        cache_size = len(response_cache)
                        response_cache.clear()
                        logger.info(f"Cleared {cache_size} cache entries")
                    except (ImportError, Exception):
                        pass
                    
                elif memory.percent > MEMORY_WARNING_THRESHOLD:
                    logger.warning(f"Memory usage high: {memory.percent:.1f}% used")
                    logger.warning(f"Process using {process.memory_info().rss / (1024*1024):.2f} MB")
                    
                    # Run normal garbage collection
                    gc.collect()
                
                # Sleep interval (check more frequently if memory pressure is high)
                if memory.percent > MEMORY_WARNING_THRESHOLD:
                    time.sleep(MEMORY_CHECK_INTERVAL / 2)
                else:
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
        memory_thread = Thread(target=monitor_memory, daemon=True)
        memory_thread.start()
        logger.info("Started memory monitoring thread")
    except Exception as e:
        logger.error(f"Error starting memory monitoring: {e}")
    
    # Log system information
    logger.info(f"Starting server with PID {os.getpid()}")
    logger.info(f"Python version: {sys.version}")
    
    # Import the app and socketio instance here after monkey patching
    try:
        # Use a more robust import approach that handles common errors
        try:
            # First attempt to import the modules
            import flask_server
            # If successful, get the required objects
            app = flask_server.app
            socketio = flask_server.socketio
            print("Successfully imported flask_server module")
        except NameError as ne:
            logger.critical(f"Name error importing flask_server: {str(ne)}")
            print(f"ERROR: {str(ne)}")
            # Try to determine which name is undefined
            if "logger" in str(ne):
                print("It appears the logger is being used before it's defined in flask_server.py")
                print("Please ensure logger is defined at the top of flask_server.py")
            sys.exit(1)
        except ImportError as ie:
            logger.critical(f"Import error: {str(ie)}")
            print(f"ERROR: Could not import required modules: {str(ie)}")
            sys.exit(1)
        except AttributeError as ae:
            logger.critical(f"Attribute error in flask_server: {str(ae)}")
            print(f"ERROR: Flask server module is missing an attribute: {str(ae)}")
            sys.exit(1)
        
        # Get port from environment or use default
        port = int(os.environ.get('PORT', 3000))
        
        # Enable debug mode if requested
        debug = os.environ.get('DEBUG', 'False').lower() == 'true'
        
        logger.info(f"Starting iOS Terminal Server with WebSocket support")
        logger.info(f"Port: {port}")
        logger.info(f"Debug mode: {debug}")
        logger.info(f"WebSocket mode: {socketio.async_mode}")
        
        # Start the socketio server with allow_unsafe_werkzeug=True for production
        # This ensures that the server starts even in production environments
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
