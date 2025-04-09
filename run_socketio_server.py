#!/usr/bin/env python3
"""
WebSocket-enabled runner for iOS Terminal Server
This script runs the Flask server with Socket.IO support using eventlet
"""

import os
import eventlet
import sys
from flask import Flask
from flask_socketio import SocketIO

# Set eventlet as the async mode before importing Flask-SocketIO components
os.environ['EVENTLET_NO_GREENDNS'] = '1'  # Avoid DNS resolution issues
eventlet.monkey_patch()

def run_socketio_server():
    """Run the Flask app with Socket.IO support"""
    # Import the app here after monkey patching
    from flask_server import app, socketio
    
    # Get port from environment or use default
    port = int(os.environ.get('PORT', 3000))
    
    # Enable debug mode if requested
    debug = os.environ.get('DEBUG', 'False').lower() == 'true'
    
    print(f"Starting iOS Terminal Server with WebSocket support")
    print(f"Port: {port}")
    print(f"Debug mode: {debug}")
    print(f"WebSocket mode: {socketio.async_mode}")
    
    # Start the socketio server
    socketio.run(
        app,
        host="0.0.0.0",
        port=port,
        debug=debug,
        use_reloader=debug,
        log_output=True
    )

if __name__ == "__main__":
    run_socketio_server()
