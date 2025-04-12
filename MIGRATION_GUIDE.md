# Migration Guide: Terminal Server Redesign

This guide helps you migrate from the original terminal server to the redesigned version.

## For Server Administrators

### Deployment Changes

1. **Update your deployment:**
   ```bash
   # Pull the latest changes
   git pull origin terminal-redesign
   
   # Install any new dependencies
   pip install -r requirements.txt
   
   # Run the enhanced server
   python run_enhanced_server.py
   ```

2. **Using Docker:**
   ```bash
   # Build and run with the enhanced Dockerfile
   docker build -t enhanced-terminal-server -f Dockerfile.enhanced .
   docker run -p 3000:3000 enhanced-terminal-server
   
   # Or use Docker Compose
   docker-compose -f docker-compose-enhanced.yml up -d
   ```

3. **Environment Variables:**
   - PORT=3000 (default, can be changed)
   - DEBUG=false (set to true for development)
   - SESSION_TIMEOUT=3600 (session timeout in seconds)
   - USER_DATA_DIR=user_data (directory for user data)
   - SCRIPT_DIR=user_scripts (directory for scripts)

### Data Migration

Sessions will not be automatically migrated. Users will need to create new sessions. Any files created in the old system will not be available in the new system.

If you need to preserve user files:

1. Copy files from the old user_data directory to the new one
2. Update file ownership and permissions

## For iOS App Developers

### WebSocket API (Recommended)

1. **Update your iOS app to use WebSockets:**
   - Implement the Socket.IO client as shown in README.md
   - Use events instead of HTTP endpoints for real-time interaction

2. **Replace file operation endpoints:**
   - Instead of `/files`, use `ls` command
   - Instead of `/files/download`, use `cat` command
   - Instead of `/files/upload`, use `echo` command
   - Instead of `/files/mkdir`, use `mkdir` command
   - Instead of `/files` (DELETE), use `rm` command

3. **Modified HTTP endpoints:**
   - `/create-session` - Same usage
   - `/execute-command` - Now includes `exitCode` in response
   - `/session` (DELETE) - Same usage

### HTTP API (Fallback)

If you cannot use WebSockets immediately:

1. **HTTP endpoints still available:**
   - `/create-session`
   - `/execute-command`
   - `/session` (DELETE)

2. **Removed HTTP endpoints:**
   - `/files` (GET) - Use `/execute-command` with `ls`
   - `/files/download` - Use `/execute-command` with `cat`
   - `/files/upload` - Use `/execute-command` with `echo`
   - `/files/mkdir` - Use `/execute-command` with `mkdir`
   - `/files` (DELETE) - Use `/execute-command` with `rm`

## Testing Your Migration

1. Run the test script to verify everything is working:
   ```bash
   python test_enhanced_server.py
   ```

2. Test your iOS app against the new server
   - Create sessions
   - Execute commands
   - Perform file operations using terminal commands
   - Check real-time output with WebSockets

3. Check that documentation is still accessible at `/`

## Troubleshooting

1. **Session creation fails:**
   - Check that USER_DATA_DIR is writable
   - Verify permissions on user_scripts directory

2. **Commands fail to execute:**
   - Check logs/flask_server.log for errors
   - Verify that the session exists and is valid

3. **WebSocket connection issues:**
   - Ensure your client supports Socket.IO v4+
   - Check for CORS issues in browser console
   - Try forcing WebSocket transport instead of polling

For additional help, see:
- REDESIGN.md for architecture details
- API_CHANGES.md for specific API changes
