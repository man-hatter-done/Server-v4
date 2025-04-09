// Terminal functionality for iOS Terminal Web Interface

// Store session information
let currentSession = {
    id: null,
    created: null,
    lastActivity: null,
    expiresIn: null
};

// Base URL for API requests
const API_BASE_URL = window.location.origin;

// DOM Elements
const terminalOutput = document.getElementById('terminal-output');
const commandInput = document.getElementById('command-input');
const sessionIdElement = document.getElementById('session-id');
const sessionCreatedElement = document.getElementById('session-created');
const sessionLastActivityElement = document.getElementById('session-last-activity');
const sessionExpiresElement = document.getElementById('session-expires');
const newSessionBtn = document.getElementById('new-session-btn');
const clearTerminalBtn = document.getElementById('clear-terminal-btn');
const endSessionBtn = document.getElementById('end-session-btn');

// Initialize terminal
document.addEventListener('DOMContentLoaded', () => {
    // Add event listeners
    commandInput.addEventListener('keydown', handleCommandInput);
    newSessionBtn.addEventListener('click', createNewSession);
    clearTerminalBtn.addEventListener('click', clearTerminal);
    endSessionBtn.addEventListener('click', endSession);
    
    // Create initial session
    createNewSession();
    
    // Focus input
    commandInput.focus();
});

// Create a new terminal session
async function createNewSession() {
    try {
        addTerminalText('Creating new terminal session...', 'system');
        
        const response = await fetch(`${API_BASE_URL}/create-session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                userId: 'web-terminal-' + Date.now()
            })
        });
        
        const data = await response.json();
        
        if (data.error) {
            addTerminalText(`Error: ${data.error}`, 'error');
            return;
        }
        
        // Store session information
        currentSession = {
            id: data.sessionId,
            created: new Date(),
            lastActivity: new Date(),
            expiresIn: data.expiresIn
        };
        
        // Update session info display
        updateSessionInfo();
        
        addTerminalText('Session created successfully.', 'success');
        addTerminalText('Type commands and press Enter to execute.', 'system');
        addTerminalText('Try: ls, pwd, python3 --version', 'system');
        
    } catch (error) {
        addTerminalText(`Connection error: ${error.message}`, 'error');
        console.error('Session creation error:', error);
    }
}

// Execute command in the terminal session
async function executeCommand(command) {
    if (!command.trim()) return;
    
    try {
        // Display the command in the terminal
        addTerminalText(command, 'command');
        
        // Check if we have a valid session
        if (!currentSession.id) {
            addTerminalText('No active session. Creating new session...', 'system');
            await createNewSession();
            if (!currentSession.id) {
                addTerminalText('Failed to create session. Please try again.', 'error');
                return;
            }
        }
        
        // Execute the command via API
        const response = await fetch(`${API_BASE_URL}/execute-command`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Id': currentSession.id
            },
            body: JSON.stringify({ command })
        });
        
        const data = await response.json();
        
        // Update session last activity
        currentSession.lastActivity = new Date();
        updateSessionInfo();
        
        // Display the result
        if (data.error) {
            addTerminalText(data.error, 'error');
        } else {
            // Show the output with proper formatting
            addTerminalText(data.output || '(Command executed with no output)', 'output');
        }
    } catch (error) {
        addTerminalText(`Error executing command: ${error.message}`, 'error');
        console.error('Command execution error:', error);
    }
}

// Add text to the terminal output
function addTerminalText(text, type = 'output') {
    const entryDiv = document.createElement('div');
    entryDiv.className = 'command-entry';
    
    if (type === 'command') {
        const commandSpan = document.createElement('div');
        commandSpan.className = 'command-text';
        commandSpan.textContent = '$ ' + text;
        entryDiv.appendChild(commandSpan);
    } else {
        const outputDiv = document.createElement('div');
        outputDiv.className = `output-text ${type === 'error' ? 'error-text' : ''}`;
        outputDiv.textContent = text;
        entryDiv.appendChild(outputDiv);
    }
    
    terminalOutput.appendChild(entryDiv);
    
    // Scroll to bottom
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Handle command input (keydown event)
function handleCommandInput(event) {
    if (event.key === 'Enter') {
        const command = commandInput.value.trim();
        executeCommand(command);
        commandInput.value = '';
        event.preventDefault();
    }
}

// Clear the terminal output
function clearTerminal() {
    terminalOutput.innerHTML = '';
    addTerminalText('Terminal cleared.', 'system');
}

// End the current session
async function endSession() {
    if (!currentSession.id) {
        addTerminalText('No active session to terminate.', 'system');
        return;
    }
    
    try {
        const response = await fetch(`${API_BASE_URL}/session`, {
            method: 'DELETE',
            headers: {
                'X-Session-Id': currentSession.id
            }
        });
        
        // Clear session info
        currentSession = {
            id: null,
            created: null,
            lastActivity: null,
            expiresIn: null
        };
        
        updateSessionInfo();
        addTerminalText('Session terminated.', 'system');
        
    } catch (error) {
        addTerminalText(`Error terminating session: ${error.message}`, 'error');
        console.error('Session termination error:', error);
    }
}

// Update session info display
function updateSessionInfo() {
    if (currentSession.id) {
        sessionIdElement.textContent = currentSession.id;
        sessionCreatedElement.textContent = currentSession.created.toLocaleString();
        sessionLastActivityElement.textContent = currentSession.lastActivity.toLocaleString();
        
        // Calculate time left for session
        const expiresInMs = currentSession.expiresIn;
        const elapsedMs = Date.now() - currentSession.lastActivity.getTime();
        const remainingMs = Math.max(0, expiresInMs - elapsedMs);
        const remainingMinutes = Math.round(remainingMs / 60000);
        
        sessionExpiresElement.textContent = `${remainingMinutes} minutes`;
    } else {
        sessionIdElement.textContent = 'Not connected';
        sessionCreatedElement.textContent = '-';
        sessionLastActivityElement.textContent = '-';
        sessionExpiresElement.textContent = '-';
    }
}

// Periodically update session info (every 30 seconds)
setInterval(updateSessionInfo, 30000);
