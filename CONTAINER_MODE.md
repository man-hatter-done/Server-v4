# Multi-User Container Isolation Mode

This document explains the container-based isolation mode that allows multiple users to share the same server while maintaining isolation between them.

## Overview

The container-based isolation approach:

1. Creates a pool of Docker containers (default: 10)
2. Distributes users evenly across containers
3. Creates Linux user accounts for each user within the containers
4. Routes commands to the appropriate container and user
5. Maintains proper isolation between users

This design maximizes resource utilization while providing strong isolation, perfect for free-tier deployments.

## How It Works

### User Distribution

When a user connects:
1. They're assigned a unique, deterministic user ID
2. The system finds the container with the fewest users
3. A Linux user account is created in that container 
4. Subsequent commands are executed in that container as that user

This ensures:
- Users are evenly distributed across all containers
- The same user always gets the same container and Linux username
- Each user has their own isolated home directory

### User Isolation

Users are isolated from each other through Linux user accounts:
- Each user has their own home directory with strict permissions (700)
- Users cannot see or access other users' files
- Process isolation prevents users from seeing each other's processes

### File Persistence

User files are persistent across sessions:
- Files are stored in a Docker volume mounted at `/workspace`
- Each user has their own subdirectory (`/workspace/username`)
- When the same user reconnects, they're routed to the same container+user

## Setting Up Container Mode

### Prerequisites

- Docker and Docker Compose installed
- Python 3.6+ with pip
- Docker Python library (`pip install docker`)

### Quick Setup

1. Install dependencies:
   ```bash
   ./setup-dependencies.sh
   ```

2. Set up container mode:
   ```bash
   ./setup-container-mode.sh
   ```

3. Start the server in container mode:
   ```bash
   docker-compose -f docker-compose-multi-user.yml up -d
   ```

4. Access the container terminal:
   http://localhost:3000/container-terminal

### Environment Variables

Configure the system with these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| USE_CONTAINERS | false | Set to "true" to enable container mode |
| MAX_CONTAINERS | 10 | Maximum number of containers in the pool |
| USERS_PER_CONTAINER | 20 | Maximum users per container |
| CONTAINER_IMAGE | terminal-multi-user:latest | Container image to use |

## Testing

To test the container-based terminal:

1. Open http://localhost:3000/container-terminal in your browser
2. Run commands like:
   - `whoami` - See your Linux username
   - `container-info` - Display container and user info
   - `ls -la` - List files in your home directory
   - `mkdir test && cd test` - Create and navigate to a directory
   - `echo "Hello" > file.txt && cat file.txt` - Create and read a file

3. To verify isolation, open the terminal in multiple browsers or incognito windows

## Troubleshooting

### Command Outputs Generic Error

If commands fail with a generic error, check:
1. Docker daemon is running
2. The terminal server has access to the Docker socket
3. The `docker` Python library is installed

### Container Creation Fails

If container creation fails:
1. Check your Docker permissions
2. Ensure you have enough system resources
3. Check the container logs: `docker logs <container-id>`

### Terminal Disconnects

If the terminal disconnects unexpectedly:
1. Check the server logs for errors
2. Ensure your Docker daemon is running properly
3. Try restarting the terminal server

## Architecture Details

The system consists of:

1. **Main Server Container**: Runs the Flask/Socket.IO server
2. **User Container Pool**: Multiple containers that host user environments
3. **Shared Volume**: For persistent user data

Commands flow:
1. User enters command in web UI
2. Command sent via WebSocket to server
3. Server routes command to appropriate container
4. Command executed as specific Linux user
5. Output streamed back to user's browser

## Container Resources

Each container has:
- Memory limit: 512MB
- CPU quota: 50% of one core
- Storage: Shared Docker volume
- Network: Bridge mode (can access internet)

## Security Considerations

While this system provides good isolation, note:
1. Users in the same container share the Linux kernel
2. Container breakout vulnerabilities could affect isolation
3. Use in trusted environments or add additional security layers
