# iOS Terminal Deployment Guide

This guide provides instructions for deploying and using the iOS Terminal server.

## Option 1: Deploying to Render.com (Recommended)

Render.com offers a simple way to deploy your terminal server for free:

1. **Fork or clone this repository** to your own GitHub account

2. **Sign up for Render.com** if you don't have an account

3. **Create a new Web Service**:
   - Click "New +" and select "Web Service"
   - Connect to your GitHub repository
   - Select the repository where you pushed the code

4. **Configure the service**:
   - Name: `ios-terminal` (or any name you prefer)
   - Environment: `Docker`
   - Docker file path: `Dockerfile.flask`
   - Branch: `main` (or your preferred branch)
   - Plan: `Free` (sufficient for most personal use)

5. **Set environment variables** (optional):
   - `DEBUG`: `false` (set to `true` for debugging)
   - `SESSION_TIMEOUT`: `3600` (session timeout in seconds)
   - `USE_AUTH`: `false` (set to `true` if you want to enable API key authentication)
   - `API_KEY`: Only required if `USE_AUTH` is `true`

6. **Create the service** and wait for deployment to complete

7. **Note your service URL** (e.g., `https://ios-terminal.onrender.com`)

8. **Update your Swift code** with this URL in the `baseURL` property of the `TerminalService` class

## Option 2: Running Locally with Docker

For local development or testing:

1. Make sure **Docker** and **Docker Compose** are installed on your computer

2. **Clone the repository**:
   ```bash
   git clone https://github.com/your-username/ios-terminal.git
   cd ios-terminal
   ```

3. **Start the server**:
   ```bash
   docker-compose up
   ```

4. The server will be available at `http://localhost:3000`

5. **Update your Swift code** to use `http://localhost:3000` as the `baseURL` if testing locally

## Security Considerations

By default, this server is designed for personal use and simplicity. Some security considerations:

1. **Public Deployment**: If you deploy publicly, consider enabling authentication:
   - Set `USE_AUTH=true` in your environment variables
   - Set a strong `API_KEY`
   - Update your Swift code to include the API key in requests

2. **Resource Limits**: The server has no built-in resource limits. On shared hosting:
   - Users could potentially run resource-intensive commands
   - Consider monitoring usage if this becomes a concern

3. **Data Persistence**: User data persists between sessions:
   - This is convenient for most use cases
   - But means files from one session will be available in future sessions
   - Consider periodically clearing unused data for long-running servers

## Using with Your iOS App

1. **Copy the Swift client code** from the README.md into your iOS project

2. **Set the correct base URL** in the `TerminalService` class:
   ```swift
   self.baseURL = "https://your-terminal-server.onrender.com"
   ```

3. **Call the terminal service** from your app:
   ```swift
   TerminalService.shared.executeCommand("echo Hello from iOS!") { result in
       switch result {
       case .success(let output):
           print(output)
       case .failure(let error):
           print("Error: \(error.localizedDescription)")
       }
   }
   ```

4. **Chain commands** for more complex operations:
   ```swift
   // Create a directory
   TerminalService.shared.executeCommand("mkdir -p projects") { _ in
       // Create a file in that directory
       TerminalService.shared.executeCommand("echo 'print(\"Hello\")' > projects/hello.py") { _ in
           // Run the Python script
           TerminalService.shared.executeCommand("python3 projects/hello.py") { result in
               if case .success(let output) = result {
                   print(output)
               }
           }
       }
   }
   ```

## Available Commands

Since this is a full Linux environment, you can run any installed commands:

- **Filesystem**: `ls`, `cd`, `mkdir`, `touch`, `rm`, `cp`, `mv`
- **Text Processing**: `cat`, `grep`, `sed`, `awk`
- **Networking**: `curl`, `wget`, `netstat`
- **Programming**: `python3`, `node`, `gcc`
- **Package Management**: `pip`, `apt-get` (if available)

## Troubleshooting

- **Connection issues**: Ensure your iOS app can reach the server and that the URL is correct
- **Command errors**: Check that the command is available in the server environment
- **Session issues**: Sessions expire after the configured timeout; your code should handle reconnection
