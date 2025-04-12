# API Changes Documentation

This document outlines the API changes in the redesigned iOS Terminal Server.

## Removed Endpoints

The following HTTP endpoints have been removed:

### File Management Endpoints

These endpoints have been removed as file operations are now handled directly through terminal commands:

| Endpoint | Method | Description | Replacement |
|----------|--------|-------------|-------------|
| `/files` | GET | List files in a directory | Use `ls` command in terminal |
| `/files/download` | GET | Download a file | Use `cat` command to view file contents |
| `/files/upload` | POST | Upload a file | Use `echo` command to create files |
| `/files` | DELETE | Delete a file or directory | Use `rm` command in terminal |
| `/files/mkdir` | POST | Create a directory | Use `mkdir` command in terminal |

### Testing Terminal Endpoints

These testing endpoints have been consolidated:

| Endpoint | Description | Replacement |
|----------|-------------|-------------|
| `/ws` | WebSocket terminal interface | Use WebSocket connection directly |
| `/ios-terminal` | iOS terminal test interface | Use WebSocket connection directly |

## Preserved Endpoints

The following endpoints have been preserved:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/` | GET | Documentation page |
| `/status` | GET | Server status page |

## New Session API

The session management API has been improved:

### WebSocket Events

| Event | Direction | Description |
|-------|-----------|-------------|
| `connect` | Client → Server | Connect to the WebSocket server |
| `create_session` | Client → Server | Create a new terminal session |
| `session_created` | Server → Client | Confirm session creation with details |
| `join_session` | Client → Server | Join an existing session |
| `session_joined` | Server → Client | Confirm session joined |
| `execute_command` | Client → Server | Execute a command in the terminal |
| `command_output` | Server → Client | Real-time command output |
| `command_complete` | Server → Client | Command execution completed |
| `command_error` | Server → Client | Command execution error |
| `end_session` | Client → Server | End a terminal session |
| `session_ended` | Server → Client | Confirm session ended |

### HTTP API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/create-session` | POST | Create a new terminal session |
| `/execute-command` | POST | Execute a command in the terminal |
| `/session` | DELETE | End a terminal session |

## WebSocket vs HTTP API

The system prioritizes the WebSocket API for real-time interaction but maintains an HTTP API for compatibility:

### WebSocket Benefits

- Real-time streaming of command output
- Lower latency and overhead
- Better interactive experience
- Support for long-running commands

### HTTP API Benefits

- Compatible with clients that don't support WebSockets
- Easier to use with simple HTTP clients
- Suitable for single command execution

## Terminal Command Integration

Terminal commands now directly handle file operations with improved functionality:

### File Viewing Commands
- `ls`: List files and directories
- `pwd`: Show current directory
- `cat`: View file contents

### File Creation Commands
- `mkdir`: Create directories
- `touch`: Create empty files
- `echo "content" > file`: Create/overwrite files with content
- `echo "content" >> file`: Append to existing files

### File Deletion Commands
- `rm`: Remove files
- `rm -r`: Remove directories recursively

## Session Management Changes

The session management has been improved:

1. **Persistence**: Sessions now persist across server restarts
2. **Auto-renewal**: Expired sessions are automatically renewed with state preservation
3. **Improved cleanup**: Better cleanup of resources when sessions end
4. **User mapping**: Users are mapped to sessions for continuity

## Example: Creating and Using a Session

### Using WebSocket API:

```javascript
// Connect to WebSocket
const socket = io(serverUrl);

// Create a session
socket.emit('create_session', { userId: 'user-123' });

// Handle session creation
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
  console.log(data.output);
});

// Handle command completion
socket.on('command_complete', (data) => {
  console.log(`Command completed with exit code: ${data.exitCode}`);
});
```

### Using HTTP API:

```javascript
// Create a session
fetch(`${serverUrl}/create-session`, {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({ userId: 'user-123' })
})
.then(response => response.json())
.then(data => {
  const sessionId = data.sessionId;
  console.log(`Session created: ${sessionId}`);
  
  // Execute a command
  return fetch(`${serverUrl}/execute-command`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Session-Id': sessionId
    },
    body: JSON.stringify({ command: 'ls -la' })
  });
})
.then(response => response.json())
.then(data => {
  console.log(`Command output: ${data.output}`);
  console.log(`Exit code: ${data.exitCode}`);
});
```
