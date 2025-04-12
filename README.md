# Enhanced iOS Terminal Server

A redesigned, high-performance backend for iOS Terminal that provides a robust Linux terminal emulation experience through WebSockets and HTTP APIs. This server delivers a true Linux terminal experience with integrated file management, without redundant HTTP endpoints.

## Features

- **Full Linux Terminal Emulation**: Complete Linux command environment with proper shell setup
- **Integrated File Operations**: File operations handled directly through terminal commands
- **Real-time WebSocket Interaction**: Streaming command output in real-time
- **Enhanced Session Management**: Improved session persistence and isolation
- **Streamlined API**: Reduced endpoints with focus on terminal experience
- **Python Support**: Run Python scripts and other interpreted languages
- **Simple Integration**: Easy to integrate with iOS apps
- **Memory Management**: Intelligent memory monitoring to prevent OOM issues
- **Enhanced Environment**: Automatically sets up a rich command environment for each user

## Architectural Improvements

This redesign offers significant architectural improvements over the previous version:

### Enhanced Terminal Emulation

- Complete Linux terminal experience with proper environment variables
- Commands executed in isolated user environments
- Shell configuration files (.bashrc, .profile) and utility scripts
- Support for long-running and interactive commands

### Integrated File Operations

- File operations handled directly through terminal commands
- No separate HTTP endpoints for file operations
- Files properly tied to user sessions and isolated
- Full support for standard file commands (ls, cat, mkdir, rm, etc.)

### Real-time WebSocket Communication

- Real-time command output streaming
- Better interactive experience for terminal operations
- Support for terminal resize and control signals
- Low-latency command execution

### Improved Session Management

- Robust session tracking with proper cleanup
- Session persistence across server restarts
- Clear session lifecycle with transparent error handling
- Automatic session renewal with state preservation

### Memory Management

Intelligent memory monitoring prevents out-of-memory crashes:
- Automatic garbage collection when memory usage is high
- Resource monitoring and cleanup
- Dynamic session management based on system resources
- Background monitoring thread

## Core Components

The redesigned server consists of these main components:

### 1. Terminal Command Handler

The `TerminalCommandHandler` class:
- Executes terminal commands in isolated environments
- Integrates file operations directly into command execution
- Streams command output in real-time
- Handles command errors gracefully

### 2. Session Manager

The `SessionManager` class:
- Creates and validates user sessions
- Maps users to sessions for continuity
- Provides session persistence
- Handles expired session cleanup
- Manages session directories and data

### 3. Environment Setup

The `EnvironmentSetup` class:
- Creates isolated user environments
- Sets up configuration files (.bashrc, .profile)
- Copies utility scripts to user environments
- Configures environment variables

## Configuration

The server can be configured using environment variables:

```bash
# Basic Configuration
DEBUG=false                  # Set to true for development logging
PORT=3000                    # HTTP port to listen on
SESSION_TIMEOUT=3600         # Session timeout in seconds
USER_DATA_DIR=user_data      # Directory for user session data
SCRIPT_DIR=user_scripts      # Directory for user scripts
```

These can be set in the docker-compose.yaml file or in your deployment environment.

## API Reference

The redesigned API focuses on WebSocket communication for real-time terminal interaction, with HTTP endpoints for compatibility.

### WebSocket API (Recommended)

Connect to `/socket.io/` for WebSocket communication.

#### Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `create_session` | Client → Server | Create a new terminal session |
| `session_created` | Server → Client | Confirm session creation with details |
| `join_session` | Client → Server | Join an existing session |
| `execute_command` | Client → Server | Execute a command in the terminal |
| `command_output` | Server → Client | Real-time command output |
| `command_complete` | Server → Client | Command execution completed |
| `end_session` | Client → Server | End a terminal session |

#### Example WebSocket Usage

```javascript
// Connect to the WebSocket server
const socket = io('http://your-server:3000');

// Create a new session
socket.emit('create_session', { userId: 'user-123' });

// Handle session creation response
socket.on('session_created', (data) => {
  const sessionId = data.sessionId;
  console.log(`Session created: ${sessionId}`);
  
  // Execute a command
  socket.emit('execute_command', {
    command: 'ls -la',
    session_id: sessionId
  });
});

// Handle command output
socket.on('command_output', (data) => {
  console.log(data.output); // Real-time output streaming
});

// Handle command completion
socket.on('command_complete', (data) => {
  console.log(`Command completed with exit code: ${data.exitCode}`);
});
```

### HTTP API (For Compatibility)

#### Create Session

```
POST /create-session
```

**Request:**
```json
{
  "userId": "optional-user-identifier"
}
```

**Response:**
```json
{
  "sessionId": "unique-session-id",
  "created": "2023-05-01T12:34:56.789Z",
  "expiresIn": 3600,
  "workingDirectory": "~"
}
```

#### Execute Command

```
POST /execute-command
```

**Headers:**
```
X-Session-Id: your-session-id
```

**Request:**
```json
{
  "command": "ls -la"
}
```

**Response:**
```json
{
  "output": "total 8\ndrwxr-xr-x 2 user user 4096 May 1 12:34 .\ndrwxr-xr-x 6 user user 4096 May 1 12:34 ..\n",
  "exitCode": 0
}
```

#### End Session

```
DELETE /session
```

**Headers:**
```
X-Session-Id: your-session-id
```

**Response:**
```json
{
  "message": "Session ended successfully"
}
```

## Running the Server

### Prerequisites

- Python 3.8+
- Flask, Flask-SocketIO, Eventlet
- Other dependencies listed in requirements.txt

### Installation

1. Clone the repository:
   ```bash
   git clone https://github.com/your-username/ios-terminal-server.git
   cd ios-terminal-server
   ```

2. Install the required dependencies:
   ```bash
   pip install -r requirements.txt
   ```

3. Run the enhanced server:
   ```bash
   python run_enhanced_server.py
   ```

4. Access the documentation at:
   ```
   http://localhost:3000/
   ```

### Deployment to Render.com

This server can be easily deployed to Render.com:

1. Fork this repository to your GitHub account
2. Create a new Web Service on Render.com
3. Connect to your forked GitHub repository
4. Select "Docker" as the environment
5. Click "Create Web Service"

## Swift Client Integration

Here are integration examples for the redesigned backend:

### WebSocket Client (Recommended)

```swift
import SocketIO

class TerminalService {
    static let shared = TerminalService()
    
    private let manager: SocketManager
    private let socket: SocketIOClient
    private var sessionId: String?
    
    private init() {
        // Change this URL to your deployed server
        let serverURL = URL(string: "https://your-terminal-server.onrender.com")!
        manager = SocketManager(socketURL: serverURL, config: [.log(true), .compress])
        socket = manager.defaultSocket
        
        setupSocketEvents()
        socket.connect()
    }
    
    private func setupSocketEvents() {
        socket.on(clientEvent: .connect) { [weak self] data, ack in
            print("Socket connected")
            self?.createSession()
        }
        
        socket.on("session_created") { [weak self] data, ack in
            guard let data = data[0] as? [String: Any],
                  let sessionId = data["sessionId"] as? String else { return }
            
            self?.sessionId = sessionId
            print("Session created: \(sessionId)")
            
            // Notify session created if needed
            NotificationCenter.default.post(name: .terminalSessionCreated, object: nil)
        }
        
        socket.on("command_output") { data, ack in
            guard let data = data[0] as? [String: Any],
                  let output = data["output"] as? String else { return }
            
            // Handle streaming output - this will be called multiple times
            NotificationCenter.default.post(name: .terminalOutputReceived, object: nil, userInfo: ["output": output])
        }
        
        socket.on("command_complete") { data, ack in
            guard let data = data[0] as? [String: Any],
                  let exitCode = data["exitCode"] as? Int else { return }
            
            // Command completed
            NotificationCenter.default.post(name: .terminalCommandCompleted, object: nil, userInfo: ["exitCode": exitCode])
        }
        
        socket.on("command_error") { data, ack in
            guard let data = data[0] as? [String: Any],
                  let error = data["error"] as? String else { return }
            
            // Handle command error
            NotificationCenter.default.post(name: .terminalCommandError, object: nil, userInfo: ["error": error])
        }
    }
    
    func createSession() {
        // Include device identifier for uniqueness
        let deviceId = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
        socket.emit("create_session", ["userId": deviceId])
    }
    
    func executeCommand(_ command: String) {
        guard let sessionId = sessionId else {
            print("No active session")
            // Create session first and then execute
            createSession()
            // Wait for session created and retry
            return
        }
        
        socket.emit("execute_command", [
            "command": command,
            "session_id": sessionId
        ])
    }
    
    func endSession() {
        guard let sessionId = sessionId else { return }
        
        socket.emit("end_session", ["session_id": sessionId])
        self.sessionId = nil
    }
}

// Notification names for terminal events
extension Notification.Name {
    static let terminalSessionCreated = Notification.Name("terminalSessionCreated")
    static let terminalOutputReceived = Notification.Name("terminalOutputReceived")
    static let terminalCommandCompleted = Notification.Name("terminalCommandCompleted")
    static let terminalCommandError = Notification.Name("terminalCommandError")
}
```

### HTTP Client (Alternative)

```swift
import Foundation

class TerminalHTTPService {
    static let shared = TerminalHTTPService()
    
    private let baseURL: String
    private var sessionId: String?
    
    private init() {
        // Change this URL to your deployed server
        self.baseURL = "https://your-terminal-server.onrender.com"
    }
    
    /// Creates a new terminal session
    func createSession(completion: @escaping (Result<String, Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/create-session") else {
            completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        
        // Include device identifier for uniqueness
        let deviceId = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
        let body: [String: Any] = ["userId": deviceId]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "No data received"])))
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let errorMessage = json["error"] as? String {
                        completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: errorMessage])))
                        return
                    }
                    
                    if let newSessionId = json["sessionId"] as? String {
                        self.sessionId = newSessionId
                        completion(.success(newSessionId))
                    } else {
                        completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Invalid response format"])))
                    }
                } else {
                    completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Could not parse response"])))
                }
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    /// Executes a command in the terminal session
    func executeCommand(_ command: String, completion: @escaping (Result<String, Error>) -> Void) {
        // First ensure we have a valid session
        if sessionId == nil {
            createSession { result in
                switch result {
                case .success(let sessionId):
                    self.executeCommandWithSession(command, sessionId: sessionId, completion: completion)
                case .failure(let error):
                    completion(.failure(error))
                }
            }
            return
        }
        
        executeCommandWithSession(command, sessionId: sessionId!, completion: completion)
    }
    
    private func executeCommandWithSession(_ command: String, sessionId: String, completion: @escaping (Result<String, Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/execute-command") else {
            completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        let body = ["command": command]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "No data received"])))
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let errorMessage = json["error"] as? String {
                        completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: errorMessage])))
                        return
                    }
                    
                    if let output = json["output"] as? String {
                        completion(.success(output))
                    } else {
                        completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Invalid response format"])))
                    }
                } else {
                    completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Could not parse response"])))
                }
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    /// Terminates the current session
    func endSession(completion: @escaping (Result<Void, Error>) -> Void) {
        guard let sessionId = sessionId else {
            completion(.success(()))
            return
        }
        
        guard let url = URL(string: "\(baseURL)/session") else {
            completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.addValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            self.sessionId = nil
            completion(.success(()))
        }.resume()
    }
}
```

## Example Usage in Swift Projects

Here's how to use the WebSocket terminal service in your Swift project:

```swift
import UIKit

class TerminalViewController: UIViewController {
    @IBOutlet weak var commandTextField: UITextField!
    @IBOutlet weak var outputTextView: UITextView!
    
    override func viewDidLoad() {
        super.viewDidLoad()
        
        // Set up notification observers for real-time updates
        NotificationCenter.default.addObserver(self, selector: #selector(handleOutputReceived(_:)), 
                                              name: .terminalOutputReceived, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(handleCommandCompleted(_:)), 
                                              name: .terminalCommandCompleted, object: nil)
        NotificationCenter.default.addObserver(self, selector: #selector(handleCommandError(_:)), 
                                              name: .terminalCommandError, object: nil)
    }
    
    @IBAction func executeButtonTapped(_ sender: Any) {
        guard let command = commandTextField.text, !command.isEmpty else {
            return
        }
        
        // Clear previous output
        outputTextView.text = ""
        
        // Execute the command via WebSocket
        TerminalService.shared.executeCommand(command)
        
        // Clear the input field
        commandTextField.text = ""
    }
    
    @objc func handleOutputReceived(_ notification: Notification) {
        guard let output = notification.userInfo?["output"] as? String else { return }
        
        // Append the output to the text view
        DispatchQueue.main.async { [weak self] in
            self?.outputTextView.text.append(output)
            // Scroll to bottom
            let range = NSRange(location: (self?.outputTextView.text.count ?? 0) - 1, length: 1)
            self?.outputTextView.scrollRangeToVisible(range)
        }
    }
    
    @objc func handleCommandCompleted(_ notification: Notification) {
        guard let exitCode = notification.userInfo?["exitCode"] as? Int else { return }
        
        DispatchQueue.main.async { [weak self] in
            // Optionally show command completion status
            if exitCode != 0 {
                self?.outputTextView.text.append("\n(Command completed with exit code \(exitCode))")
            }
        }
    }
    
    @objc func handleCommandError(_ notification: Notification) {
        guard let error = notification.userInfo?["error"] as? String else { return }
        
        DispatchQueue.main.async { [weak self] in
            self?.outputTextView.text.append("\nError: \(error)")
        }
    }
    
    @IBAction func clearButtonTapped(_ sender: Any) {
        outputTextView.text = ""
    }
}
```

## Terminal Command Examples

The redesigned server supports all standard Linux commands, with properly integrated file operations:

### File Operations

```swift
// List files in the current directory
TerminalService.shared.executeCommand("ls -la")

// Create a new directory
TerminalService.shared.executeCommand("mkdir myproject")

// Change to that directory
TerminalService.shared.executeCommand("cd myproject")

// Create a new file with content
TerminalService.shared.executeCommand("echo 'Hello, world!' > hello.txt")

// View file content
TerminalService.shared.executeCommand("cat hello.txt")

// Append to a file
TerminalService.shared.executeCommand("echo 'This is a new line' >> hello.txt")

// Remove a file
TerminalService.shared.executeCommand("rm hello.txt")
```

### Python Development

```swift
// Install a Python package
TerminalService.shared.executeCommand("pip install requests")

// Create a Python script
let pythonCode = """
import requests

response = requests.get('https://api.github.com')
print(f"GitHub API Status Code: {response.status_code}")
"""

TerminalService.shared.executeCommand("echo '\(pythonCode)' > github_api.py")

// Run the script
TerminalService.shared.executeCommand("python3 github_api.py")
```

### Advanced Usage: Multi-step Operations

Using WebSockets allows for cleaner code with real-time updates:

```swift
// Set up a simple web server
func setupWebServer() {
    // 1. Create project directory
    TerminalService.shared.executeCommand("mkdir -p webserver")
    
    // 2. Change to that directory
    TerminalService.shared.executeCommand("cd webserver")
    
    // 3. Install Flask
    TerminalService.shared.executeCommand("pip install flask")
    
    // 4. Create the server file
    let serverCode = """
    from flask import Flask
    app = Flask(__name__)

    @app.route('/')
    def hello():
        return 'Hello from iOS Terminal!'

    if __name__ == '__main__':
        app.run(host='0.0.0.0', port=8000)
    """
    
    TerminalService.shared.executeCommand("echo '\(serverCode)' > server.py")
    
    // 5. Run the server in the background
    TerminalService.shared.executeCommand("python3 server.py &")
}
```

## Additional Resources

For more detailed information about the redesign and API changes, see:

- [REDESIGN.md](./REDESIGN.md) - Details about the architectural changes
- [API_CHANGES.md](./API_CHANGES.md) - Specific API changes and migration guide

## License

MIT
