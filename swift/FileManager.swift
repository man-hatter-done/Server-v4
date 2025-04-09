import Foundation

/// FileManager for iOS Termux that allows file operations like listing, downloading, uploading, and deleting files
class TermuxFileManager {
    /// Shared instance for convenience
    static let shared = TermuxFileManager()
    
    /// URL of the Termux server
    private let baseURL: String
    
    /// Current session ID for authentication
    private var sessionId: String?
    
    /// Initialize with the server URL
    init(baseURL: String? = nil) {
        self.baseURL = baseURL ?? "https://your-termux-server.onrender.com"
    }
    
    /// Set session ID manually (usually from TerminalService)
    func setSessionId(_ sessionId: String) {
        self.sessionId = sessionId
    }
    
    /// Get session ID or fetch from TerminalService
    private func getSessionId(completion: @escaping (Result<String, Error>) -> Void) {
        if let sessionId = self.sessionId {
            completion(.success(sessionId))
            return
        }
        
        // Try to get session from TerminalService
        TerminalService.shared.createSession { result in
            switch result {
            case .success(let sessionId):
                self.sessionId = sessionId
                completion(.success(sessionId))
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }
    
    // MARK: - File Operations
    
    /// List files and directories at the specified path
    /// - Parameters:
    ///   - path: Path relative to the user's home directory (empty string for home)
    ///   - completion: Called with array of file items or error
    func listFiles(at path: String = "", completion: @escaping (Result<[FileItem], Error>) -> Void) {
        getSessionId { result in
            switch result {
            case .success(let sessionId):
                self.makeRequest(
                    endpoint: "/files",
                    method: "GET",
                    sessionId: sessionId,
                    queryParams: ["path": path]
                ) { result in
                    switch result {
                    case .success(let data):
                        do {
                            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any],
                               let filesArray = json["files"] as? [[String: Any]] {
                                let fileItems = filesArray.compactMap { FileItem(json: $0) }
                                completion(.success(fileItems))
                            } else {
                                completion(.failure(FileError.invalidResponse))
                            }
                        } catch {
                            completion(.failure(error))
                        }
                    case .failure(let error):
                        completion(.failure(error))
                    }
                }
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }
    
    /// Download a file from the server
    /// - Parameters:
    ///   - path: Path to the file relative to user's home
    ///   - completion: Called with file data or error
    func downloadFile(at path: String, completion: @escaping (Result<Data, Error>) -> Void) {
        getSessionId { result in
            switch result {
            case .success(let sessionId):
                self.makeRequest(
                    endpoint: "/files/download",
                    method: "GET",
                    sessionId: sessionId,
                    queryParams: ["path": path]
                ) { result in
                    switch result {
                    case .success(let data):
                        completion(.success(data))
                    case .failure(let error):
                        completion(.failure(error))
                    }
                }
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }
    
    /// Upload a file to the server
    /// - Parameters:
    ///   - fileData: The binary data of the file
    ///   - filename: Name for the file
    ///   - path: Directory path where to upload (empty for home)
    ///   - completion: Called with success message or error
    func uploadFile(fileData: Data, filename: String, to path: String = "", completion: @escaping (Result<String, Error>) -> Void) {
        getSessionId { result in
            switch result {
            case .success(let sessionId):
                guard let url = URL(string: "\(self.baseURL)/files/upload") else {
                    completion(.failure(FileError.invalidURL))
                    return
                }
                
                // Create multipart form data
                let boundary = "Boundary-\(UUID().uuidString)"
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
                request.setValue(sessionId, forHTTPHeaderField: "X-Session-Id")
                
                var body = Data()
                
                // Add path parameter
                body.append("--\(boundary)\r\n".data(using: .utf8)!)
                body.append("Content-Disposition: form-data; name=\"path\"\r\n\r\n".data(using: .utf8)!)
                body.append("\(path)\r\n".data(using: .utf8)!)
                
                // Add file data
                body.append("--\(boundary)\r\n".data(using: .utf8)!)
                body.append("Content-Disposition: form-data; name=\"file\"; filename=\"\(filename)\"\r\n".data(using: .utf8)!)
                body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
                body.append(fileData)
                body.append("\r\n".data(using: .utf8)!)
                
                // End boundary
                body.append("--\(boundary)--\r\n".data(using: .utf8)!)
                
                request.httpBody = body
                
                URLSession.shared.dataTask(with: request) { data, response, error in
                    if let error = error {
                        completion(.failure(error))
                        return
                    }
                    
                    guard let data = data else {
                        completion(.failure(FileError.noData))
                        return
                    }
                    
                    do {
                        if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                            if let error = json["error"] as? String {
                                completion(.failure(FileError.apiError(error)))
                                return
                            }
                            
                            if let message = json["message"] as? String {
                                completion(.success(message))
                            } else {
                                completion(.success("File uploaded successfully"))
                            }
                        } else {
                            completion(.failure(FileError.invalidResponse))
                        }
                    } catch {
                        completion(.failure(error))
                    }
                }.resume()
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }
    
    /// Create a new directory
    /// - Parameters:
    ///   - path: Path for the new directory relative to user's home
    ///   - completion: Called with success message or error
    func createDirectory(at path: String, completion: @escaping (Result<String, Error>) -> Void) {
        getSessionId { result in
            switch result {
            case .success(let sessionId):
                guard let url = URL(string: "\(self.baseURL)/files/mkdir") else {
                    completion(.failure(FileError.invalidURL))
                    return
                }
                
                var request = URLRequest(url: url)
                request.httpMethod = "POST"
                request.setValue("application/json", forHTTPHeaderField: "Content-Type")
                request.setValue(sessionId, forHTTPHeaderField: "X-Session-Id")
                
                let body: [String: Any] = ["path": path]
                request.httpBody = try? JSONSerialization.data(withJSONObject: body)
                
                URLSession.shared.dataTask(with: request) { data, response, error in
                    if let error = error {
                        completion(.failure(error))
                        return
                    }
                    
                    guard let data = data else {
                        completion(.failure(FileError.noData))
                        return
                    }
                    
                    do {
                        if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                            if let error = json["error"] as? String {
                                completion(.failure(FileError.apiError(error)))
                                return
                            }
                            
                            if let message = json["message"] as? String {
                                completion(.success(message))
                            } else {
                                completion(.success("Directory created successfully"))
                            }
                        } else {
                            completion(.failure(FileError.invalidResponse))
                        }
                    } catch {
                        completion(.failure(error))
                    }
                }.resume()
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }
    
    /// Delete a file or directory
    /// - Parameters:
    ///   - path: Path to delete relative to user's home
    ///   - completion: Called with success message or error
    func deleteItem(at path: String, completion: @escaping (Result<String, Error>) -> Void) {
        getSessionId { result in
            switch result {
            case .success(let sessionId):
                self.makeRequest(
                    endpoint: "/files",
                    method: "DELETE",
                    sessionId: sessionId,
                    queryParams: ["path": path]
                ) { result in
                    switch result {
                    case .success(let data):
                        do {
                            if let json = try JSONSerialization.jsonObject(with: data) as? [String: Any] {
                                if let error = json["error"] as? String {
                                    completion(.failure(FileError.apiError(error)))
                                    return
                                }
                                
                                if let message = json["message"] as? String {
                                    completion(.success(message))
                                } else {
                                    completion(.success("Item deleted successfully"))
                                }
                            } else {
                                completion(.failure(FileError.invalidResponse))
                            }
                        } catch {
                            completion(.failure(error))
                        }
                    case .failure(let error):
                        completion(.failure(error))
                    }
                }
            case .failure(let error):
                completion(.failure(error))
            }
        }
    }
    
    // MARK: - Helper Methods
    
    /// Make a generic API request
    private func makeRequest(
        endpoint: String,
        method: String,
        sessionId: String,
        queryParams: [String: String] = [:],
        body: [String: Any]? = nil,
        completion: @escaping (Result<Data, Error>) -> Void
    ) {
        // Build URL with query parameters
        var urlComponents = URLComponents(string: baseURL + endpoint)
        if !queryParams.isEmpty {
            urlComponents?.queryItems = queryParams.map { URLQueryItem(name: $0.key, value: $0.value) }
        }
        
        guard let url = urlComponents?.url else {
            completion(.failure(FileError.invalidURL))
            return
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = method
        request.setValue(sessionId, forHTTPHeaderField: "X-Session-Id")
        
        if let body = body {
            request.setValue("application/json", forHTTPHeaderField: "Content-Type")
            request.httpBody = try? JSONSerialization.data(withJSONObject: body)
        }
        
        URLSession.shared.dataTask(with: request) { data, response, error in
            if let error = error {
                completion(.failure(error))
                return
            }
            
            guard let data = data else {
                completion(.failure(FileError.noData))
                return
            }
            
            completion(.success(data))
        }.resume()
    }
}

// MARK: - Models and Errors

/// Represents a file or directory in the Termux file system
struct FileItem {
    let name: String
    let path: String
    let isDirectory: Bool
    let size: Int
    let modified: Date
    
    init?(json: [String: Any]) {
        guard let name = json["name"] as? String,
              let path = json["path"] as? String,
              let isDir = json["is_dir"] as? Bool,
              let size = json["size"] as? Int,
              let modifiedStr = json["modified"] as? String else {
            return nil
        }
        
        self.name = name
        self.path = path
        self.isDirectory = isDir
        self.size = size
        
        let dateFormatter = ISO8601DateFormatter()
        self.modified = dateFormatter.date(from: modifiedStr) ?? Date()
    }
}

/// File operation errors
enum FileError: Error {
    case invalidURL
    case noData
    case invalidResponse
    case apiError(String)
    
    var localizedDescription: String {
        switch self {
        case .invalidURL:
            return "Invalid URL"
        case .noData:
            return "No data received"
        case .invalidResponse:
            return "Invalid response format"
        case .apiError(let message):
            return "API Error: \(message)"
        }
    }
}

// MARK: - Data Extensions for Multipart Form

extension Data {
    mutating func append(_ string: String) {
        if let data = string.data(using: .utf8) {
            append(data)
        }
    }
}
