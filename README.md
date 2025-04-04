# Terminal Server

A secure, multi-user terminal server that provides isolated Linux environments for each user, accessible via a REST API.

## Features

- **User Isolation**: Each user gets their own Docker container
- **Session Management**: API key and session-based authentication
- **Resource Limits**: Prevent abuse with memory and CPU limits
- **Comprehensive Tools**: Full Linux environment with development tools
- **Secure**: Multiple security measures to prevent abuse

## API Reference

### Authentication

All endpoints require an API key sent in the `X-API-Key` header.

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
X-API-Key: your-api-key
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
  "output": "total 8\ndrwxr-xr-x 2 terminal-user terminal-user 4096 May 1 12:34 .\ndrwxr-xr-x 6 terminal-user terminal-user 4096 May 1 12:34 ..\n"
}
```

### Get Session Info

```
GET /session
```

**Headers:**
```
X-API-Key: your-api-key
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
X-API-Key: your-api-key
X-Session-Id: your-session-id
```

**Response:**
```json
{
  "message": "Session terminated successfully"
}
```

## Swift Client

Here's the Swift client code for accessing the terminal server:

```swift
import Foundation

enum TerminalError: Error {
    case invalidURL
    case networkError(String)
    case responseError(String)
    case sessionError(String)
    case parseError(String)
}

class TerminalService {
    static let shared = TerminalService()
    
    private let baseURL: String
    private let apiKey: String
    private var sessionId: String?
    private var userId: String?
    
    private init() {
        // Change these values for your production environment
        self.baseURL = "https://backdoor-backend.onrender.com"
        self.apiKey = "your-api-key-here"
    }
    
    /// Creates a new terminal session for the user
    /// - Parameter completion: Called with the session ID or an error
    func createSession(completion: @escaping (Result<String, Error>) -> Void) {
        // Check if we already have a valid session
        if let existingSession = sessionId {
            // Validate existing session
            validateSession { result in
                switch result {
                case .success(_):
                    // Session is still valid
                    completion(.success(existingSession))
                case .failure(_):
                    // Session is invalid, create a new one
                    self.createNewSession(completion: completion)
                }
            }
        } else {
            // No existing session, create a new one
            createNewSession(completion: completion)
        }
    }
    
    private func createNewSession(completion: @escaping (Result<String, Error>) -> Void) {
        guard let url = URL(string: "\(baseURL)/create-session") else {
            completion(.failure(TerminalError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue(apiKey, forHTTPHeaderField: "X-API-Key")
        
        // Include device identifier to ensure uniqueness
        let deviceId = UIDevice.current.identifierForVendor?.uuidString ?? UUID().uuidString
        let body: [String: Any] = ["userId": deviceId]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(TerminalError.networkError(error.localizedDescription)))
                return
            }
            
            guard let data = data else {
                completion(.failure(TerminalError.responseError("No data received")))
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let errorMessage = json["error"] as? String {
                        completion(.failure(TerminalError.responseError(errorMessage)))
                        return
                    }
                    
                    if let newSessionId = json["sessionId"] as? String {
                        self.sessionId = newSessionId
                        self.userId = json["userId"] as? String
                        completion(.success(newSessionId))
                    } else {
                        completion(.failure(TerminalError.responseError("Invalid response format")))
                    }
                } else {
                    completion(.failure(TerminalError.responseError("Could not parse response")))
                }
            } catch {
                completion(.failure(error))
            }
        }.resume()
    }
    
    private func validateSession(completion: @escaping (Result<Bool, Error>) -> Void) {
        guard let sessionId = sessionId else {
            completion(.failure(TerminalError.sessionError("No active session")))
            return
        }
        
        guard let url = URL(string: "\(baseURL)/session") else {
            completion(.failure(TerminalError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "GET"
        request.addValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.addValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(TerminalError.networkError(error.localizedDescription)))
                return
            }
            
            if let httpResponse = response as? HTTPURLResponse, httpResponse.statusCode != 200 {
                // Session is invalid
                self.sessionId = nil
                completion(.failure(TerminalError.sessionError("Session expired")))
                return
            }
            
            completion(.success(true))
        }.resume()
    }
    
    /// Executes a command in the user's terminal session
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
            completion(.failure(TerminalError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.addValue("application/json", forHTTPHeaderField: "Content-Type")
        request.addValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.addValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        let body = ["command": command]
        request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(TerminalError.networkError(error.localizedDescription)))
                return
            }
            
            guard let data = data else {
                completion(.failure(TerminalError.responseError("No data received")))
                return
            }
            
            do {
                if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                    if let errorMessage = json["error"] as? String {
                        completion(.failure(TerminalError.responseError(errorMessage)))
                        return
                    }
                    
                    if let output = json["output"] as? String {
                        completion(.success(output))
                    } else {
                        completion(.failure(TerminalError.responseError("Invalid response format")))
                    }
                } else {
                    completion(.failure(TerminalError.parseError("Could not parse response")))
                }
            } catch {
                completion(.failure(TerminalError.parseError("JSON parsing error: \(error.localizedDescription)")))
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
            completion(.failure(TerminalError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.addValue(apiKey, forHTTPHeaderField: "X-API-Key")
        request.addValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(TerminalError.networkError(error.localizedDescription)))
                return
            }
            
            self.sessionId = nil
            completion(.success(()))
        }.resume()
    }
}
```

## Using in Swift Projects

Add the TerminalService class to your project and use it like this:

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
        outputTextView.text = ""
    }
}
```

## Swift Usage Examples

### Basic Command Execution

```swift
// Execute a simple command
TerminalService.shared.executeCommand("ls -la") { result in
    switch result {
    case .success(let output):
        print("Command output: \(output)")
    case .failure(let error):
        print("Error: \(error.localizedDescription)")
    }
}
```

### File Operations

```swift
// Create a directory
TerminalService.shared.executeCommand("mkdir -p myproject") { _ in
    // Create a file in the directory
    let fileContent = "Hello, World!"
    let command = "echo '\(fileContent)' > myproject/hello.txt"
    
    TerminalService.shared.executeCommand(command) { _ in
        // Read the file
        TerminalService.shared.executeCommand("cat myproject/hello.txt") { result in
            if case .success(let output) = result {
                print("File content: \(output)")
            }
        }
    }
}
```

### Running a Python Script

```swift
// Create a Python script
let pythonCode = """
print("Hello from Python!")
for i in range(5):
    print(f"Number: {i}")
"""

let createScriptCommand = "echo '\(pythonCode)' > script.py"
TerminalService.shared.executeCommand(createScriptCommand) { _ in
    // Execute the Python script
    TerminalService.shared.executeCommand("python3 script.py") { result in
        if case .success(let output) = result {
            print("Python output: \(output)")
        }
    }
}
```

## License

MIT
