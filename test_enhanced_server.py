#!/usr/bin/env python3
"""
Simple test script for the enhanced terminal server
"""

import requests
import socketio
import time
import threading
import sys

# Configuration
SERVER_URL = "http://localhost:3000"

def test_http_api():
    """Test the HTTP API endpoints"""
    print("\n=== Testing HTTP API ===")
    
    # Create session
    print("Creating session...")
    response = requests.post(f"{SERVER_URL}/create-session", json={"userId": "test-user"})
    if response.status_code != 200:
        print(f"Error creating session: {response.status_code} {response.text}")
        return False
    
    session_data = response.json()
    session_id = session_data.get("sessionId")
    if not session_id:
        print(f"No session ID in response: {session_data}")
        return False
    
    print(f"Session created with ID: {session_id}")
    
    # Execute command
    print("Executing command (ls -la)...")
    response = requests.post(
        f"{SERVER_URL}/execute-command", 
        headers={"X-Session-Id": session_id},
        json={"command": "ls -la"}
    )
    
    if response.status_code != 200:
        print(f"Error executing command: {response.status_code} {response.text}")
        return False
    
    output = response.json().get("output", "")
    print(f"Command output:\n{output}")
    
    # Create a file
    print("Creating a file...")
    response = requests.post(
        f"{SERVER_URL}/execute-command", 
        headers={"X-Session-Id": session_id},
        json={"command": "echo 'Hello, World!' > test.txt"}
    )
    
    if response.status_code != 200:
        print(f"Error creating file: {response.status_code} {response.text}")
        return False
    
    # View file
    print("Viewing file...")
    response = requests.post(
        f"{SERVER_URL}/execute-command", 
        headers={"X-Session-Id": session_id},
        json={"command": "cat test.txt"}
    )
    
    if response.status_code != 200:
        print(f"Error viewing file: {response.status_code} {response.text}")
        return False
    
    output = response.json().get("output", "")
    print(f"File content:\n{output}")
    
    # End session
    print("Ending session...")
    response = requests.delete(
        f"{SERVER_URL}/session", 
        headers={"X-Session-Id": session_id}
    )
    
    if response.status_code != 200:
        print(f"Error ending session: {response.status_code} {response.text}")
        return False
    
    print("HTTP API tests completed successfully.")
    return True

def test_websocket():
    """Test the WebSocket API"""
    print("\n=== Testing WebSocket API ===")
    
    # Create a socket.io client
    sio = socketio.Client()
    results = {"success": False, "session_id": None, "output": ""}
    
    @sio.event
    def connect():
        print("Connected to server")
        # Create a session
        sio.emit("create_session", {"userId": "socket-test-user"})
    
    @sio.event
    def disconnect():
        print("Disconnected from server")
    
    @sio.on("session_created")
    def on_session_created(data):
        print(f"Session created: {data}")
        results["session_id"] = data.get("sessionId")
        
        # Execute a command
        sio.emit("execute_command", {
            "command": "ls -la",
            "session_id": results["session_id"]
        })
    
    @sio.on("command_output")
    def on_command_output(data):
        output = data.get("output", "")
        results["output"] += output
        print(f"Output: {output}", end="")
    
    @sio.on("command_complete")
    def on_command_complete(data):
        print(f"\nCommand completed with exit code: {data.get('exitCode')}")
        
        # Create a file
        sio.emit("execute_command", {
            "command": "echo 'Hello from WebSocket!' > socket_test.txt",
            "session_id": results["session_id"]
        })
        
        # Wait a moment before reading the file
        time.sleep(1)
        
        # Read the file
        sio.emit("execute_command", {
            "command": "cat socket_test.txt",
            "session_id": results["session_id"]
        })
        
        # Wait a moment before ending
        time.sleep(1)
        
        # Test completed successfully
        results["success"] = True
        
        # End the session
        sio.emit("end_session", {"session_id": results["session_id"]})
        
        # Disconnect
        sio.disconnect()
    
    try:
        sio.connect(SERVER_URL)
        # Wait for completion
        timeout = 10
        start_time = time.time()
        while time.time() - start_time < timeout:
            if results["success"]:
                break
            time.sleep(0.5)
        
        if results["success"]:
            print("WebSocket tests completed successfully.")
            return True
        else:
            print(f"WebSocket tests timed out after {timeout} seconds.")
            return False
            
    except Exception as e:
        print(f"Error in WebSocket test: {str(e)}")
        return False

def test_documentation():
    """Test that documentation endpoint is preserved"""
    print("\n=== Testing Documentation Endpoint ===")
    
    response = requests.get(SERVER_URL)
    if response.status_code != 200:
        print(f"Error accessing documentation: {response.status_code}")
        return False
    
    # Check if it looks like the documentation page
    if "iOS Terminal Server" not in response.text:
        print("Response doesn't appear to be the documentation page")
        return False
    
    print("Documentation endpoint test successful.")
    return True

def main():
    """Run all tests"""
    print("Starting tests for Enhanced Terminal Server...")
    
    # Test HTTP API
    http_success = test_http_api()
    
    # Test WebSocket API
    ws_success = test_websocket()
    
    # Test documentation
    doc_success = test_documentation()
    
    # Summary
    print("\n=== Test Summary ===")
    print(f"HTTP API: {'✅ Passed' if http_success else '❌ Failed'}")
    print(f"WebSocket API: {'✅ Passed' if ws_success else '❌ Failed'}")
    print(f"Documentation: {'✅ Passed' if doc_success else '❌ Failed'}")
    
    if http_success and ws_success and doc_success:
        print("\nAll tests passed! The enhanced server is working correctly.")
        return 0
    else:
        print("\nSome tests failed. Please check the output for details.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
