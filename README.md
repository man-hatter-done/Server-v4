# iOS Terminal

A high-performance, Python-based terminal server that provides a Linux command environment for iOS apps, similar to Termux for Android. This server is designed to be easily accessible from Swift applications and offers enhanced stability and performance optimizations.

## Features

- **Full Linux Command Access**: Execute any command you'd run in a terminal
- **Session Persistence**: Your files and state are preserved between commands
- **Python Support**: Run Python scripts and other interpreted languages
- **Simple API**: Easy to integrate with iOS apps
- **Web Terminal Interface**: Test commands directly in your browser
- **No Docker Required**: Run directly on the server without containerization
- **Fast Deployment**: Quick to deploy to Render.com or other platforms
- **High Performance**: Optimized for concurrent users with advanced session pooling
- **Memory Management**: Intelligent memory monitoring to prevent OOM issues
- **Enhanced Environment**: Automatically sets up a rich command environment
- **Health Monitoring**: Built-in healthchecks and resource management

## Performance Optimizations

This server includes several performance optimizations to handle high traffic and ensure stability:

### Session Pooling

Pre-creates session environments for faster user allocation:
- Configurable pool size (default: 10)
- Automatic pool refilling
- Thread-safe pool management
- Expired session cleanup

### Memory Management

Intelligent memory monitoring prevents out-of-memory crashes:
- Automatic garbage collection when memory usage is high
- Cache clearing under memory pressure
- Dynamic session cleanup when resources are low
- Background monitoring thread

### Worker Optimization

Gunicorn worker configuration is optimized for concurrent users:
- Multiple workers (12 by default)
- Thread-based request handling
- Graceful timeouts and restarts
- Preloading for faster startup

### Resource Management

Docker container resource limits prevent host resource starvation:
- Memory limits and reservations
- CPU allocation
- File descriptor limits
- Process limits

## Configuration

The server can be configured using environment variables:

```bash
# Basic Configuration
DEBUG=false                  # Set to true for development logging
PORT=3000                    # HTTP port to listen on
SESSION_TIMEOUT=3600         # Session timeout in seconds
USE_AUTH=false               # Enable authentication
COMMAND_TIMEOUT=300          # Command execution timeout

# Performance Configuration
SESSION_POOL_SIZE=10         # Number of pre-created sessions
MAX_POOL_AGE=1800            # Maximum age of pooled sessions
```

These can be set in the docker-compose.yaml file or in your deployment environment.

## API Reference

The API is designed to be simple and compatible with the original Docker-based implementation, but without requiring API keys by default.

### Create Session

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
  "userId": "user-identifier",
  "message": "Session created successfully",
  "expiresIn": 3600000
}
```

### Execute Command

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
  "output": "total 8\ndrwxr-xr-x 2 user user 4096 May 1 12:34 .\ndrwxr-xr-x 6 user user 4096 May 1 12:34 ..\n"
}
```

### Get Session Info

```
GET /session
```

**Headers:**
```
X-Session-Id: your-session-id
```

**Response:**
```json
{
  "userId": "user-identifier",
  "created": "2023-05-01T12:34:56.789Z",
  "lastAccessed": "2023-05-01T12:45:00.000Z",
  "expiresIn": 3000000
}
```

### Delete Session

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
  "message": "Session terminated successfully"
}
```

## Deployment to Render.com

This server can be easily deployed to Render.com:

1. Fork this repository to your GitHub account
2. Create a new Web Service on Render.com
3. Connect to your forked GitHub repository
4. Select "Docker" as the environment
5. Choose the `Dockerfile.flask` file
6. Click "Create Web Service"

## Swift Client

Here's the Swift client code for accessing the iOS Terminal server:

```swift
import Foundation

class TerminalService {
    static let shared = TerminalService()
    
    private let baseURL: String
    private var sessionId: String?
    private var userId: String?
    
    private init() {
        // Change this URL to your deployed server
        self.baseURL = "https://your-terminal-server.onrender.com"
    }
    
    /// Creates a new terminal session
    /// - Parameter completion: Called with session ID or an error
    func createSession(completion: @escaping (Result<String, Error>) -> Void) {
        // Check for existing valid session
        if let existingSession = sessionId {
            validateSession { result in
                switch result {
                case .success:
                    completion(.success(existingSession))
                case .failure:
                    self.createNewSession(completion: completion)
                }
            }
        } else {
            createNewSession(completion: completion)
        }
    }
    
    private func createNewSession(completion: @escaping (Result<String, Error>) -> Void) {
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
                        self.userId = json["userId"] as? String
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
    
    private func validateSession(completion: @escaping (Result<Bool, Error>) -> Void) {
        guard let sessionId = sessionId else {
            completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "No active session"])))
            return
        }
        
        guard let url = URL(string: "\(baseURL)/session") else {
            completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Invalid URL"])))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.addValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                // Session is invalid
                self.sessionId = nil
                completion(.failure(NSError(domain: "TerminalService", code: 0, userInfo: [NSLocalizedDescriptionKey: "Session expired"])))
                return
            }
            
            completion(.success(true))
        }.resume()
    }
    
    /// Executes a command in the terminal session
    /// - Parameters:
    ///   - command: The command to execute
    ///   - completion: Called with the command output or an error
    func executeCommand(_ command: String, completion: @escaping (Result<String, Error>) -> Void) {
        // First ensure we have a valid session
        createSession { result in
            switch result {
            case .success(let sessionId):
                self.executeCommandWithSession(command, sessionId: sessionId, completion: completion)
            case .failure(let error):
                completion(.failure(error))
            }
        }
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

## Usage in Swift Projects

Here's how to use the TerminalService in your Swift project:

```swift
import UIKit

class TerminalViewController: UIViewController {
    @IBOutlet weak var commandTextField: UITextField!
    @IBOutlet weak var outputTextView: UITextView!
    
    override func viewDidLoad() {
        super.viewDidLoad()
    }
    
    @IBAction func executeButtonTapped(_ sender: Any) {
        guard let command = commandTextField.text, !command.isEmpty else {
            return
        }
        
        outputTextView.text = "Executing command..."
        
        TerminalService.shared.executeCommand(command) { [weak self] result in
            DispatchQueue.main.async {
                switch result {
                case .success(let output):
                    self?.outputTextView.text = output
                case .failure(let error):
                    self?.outputTextView.text = "Error: \(error.localizedDescription)"
                }
            }
        }
    }
    
    @IBAction func clearButtonTapped(_ sender: Any) {
        commandTextField.text = ""
        outputTextView.text = ""
    }
}
```

## Example Use Cases

### Installing and Using Python Packages

```swift
// Install a Python package
TerminalService.shared.executeCommand("pip install requests") { result in
    switch result {
    case .success(let output):
        print("Installation output: \(output)")
        
        // Create a Python script that uses the package
        let pythonCode = """
        import requests
        
        response = requests.get('https://api.github.com')
        print(f"GitHub API Status Code: {response.status_code}")
        print(f"GitHub API Headers: {response.headers}")
        """
        
        let createScriptCommand = "echo '\(pythonCode)' > github_api.py"
        TerminalService.shared.executeCommand(createScriptCommand) { _ in
            // Run the script
            TerminalService.shared.executeCommand("python3 github_api.py") { result in
                if case .success(let output) = result {
                    print("Script output: \(output)")
                }
            }
        }
        
    case .failure(let error):
        print("Error: \(error.localizedDescription)")
    }
}
```

### File Management and Text Processing

```swift
// Create some text files
TerminalService.shared.executeCommand("echo 'This is file 1' > file1.txt") { _ in
    TerminalService.shared.executeCommand("echo 'This is file 2' > file2.txt") { _ in
        // Concatenate files and use grep
        TerminalService.shared.executeCommand("cat file1.txt file2.txt | grep 'file'") { result in
            if case .success(let output) = result {
                print("Grep results: \(output)")
            }
        }
    }
}
```

### Creating and Running a Web Server

```swift
// Create a simple Flask web server
let flaskCode = """
from flask import Flask
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello from your iOS terminal!'

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8000)
"""

TerminalService.shared.executeCommand("pip install flask") { _ in
    TerminalService.shared.executeCommand("echo '\(flaskCode)' > server.py") { _ in
        // Run the server in the background
        TerminalService.shared.executeCommand("python3 server.py &") { result in
            if case .success(let output) = result {
                print("Server started: \(output)")
                
                // We could now access this server via HTTP at the server's address:8000
            }
        }
    }
}
```

## License

MIT
