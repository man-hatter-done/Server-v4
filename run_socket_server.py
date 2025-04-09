#!/usr/bin/env python3
import os
import eventlet
import sys

# Set eventlet as the async mode before importing Flask-SocketIO components
os.environ['EVENTLET_NO_GREENDNS'] = '1'  # Avoid DNS resolution issues
eventlet.monkey_patch()

# Import the Flask app and socketio instance
from flask_server import app, socketio

if __name__ == "__main__":
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 3000))
    
    # Enable debug mode if requested
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print(f"Starting WebSocket server on port {port} with debug={debug}")
    
    # Start the socketio server
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=debug,
        log_output=True
    )
