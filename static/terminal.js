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
    // Add event listeners with explicit event prevention
    commandInput.addEventListener('keydown', handleCommandInput);
    
    newSessionBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        createNewSession();
    });
    
    clearTerminalBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        clearTerminal();
    });
    
    endSessionBtn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        endSession();
    });
    
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

// Execute command in the terminal session with retry capability
async function executeCommand(command, retryCount = 0, isRetry = false) {
    // CRITICAL FIX: Make sure command is a string to prevent issues with PointerEvent being passed
    if (typeof command !== 'string') {
        console.error('Invalid command type received:', typeof command);
        if (command instanceof Event) {
            console.error('Received an Event object instead of a command string');
            addTerminalText('Error: Browser event detected instead of command text. This is a bug.', 'error');
            return;
        }
        // Try to convert to string if possible
        try {
            command = String(command);
        } catch (e) {
            console.error('Failed to convert command to string:', e);
            return;
        }
    }
    
    // Additional check for object strings that might have slipped through
    if (command && command.includes('[object ') && command.includes(']')) {
        console.error('Command contains object reference:', command);
        addTerminalText('Error: Invalid command format detected.', 'error');
        return;
    }
    
    if (!command.trim()) return;
    
    // Define constants for retries
    const MAX_RETRIES = 3;
    const RETRY_DELAY = 1000; // 1 second
    
    try {
        // Only show the command if this is not a retry
        if (!isRetry) {
            // Display the command in the terminal
            addTerminalText(command, 'command');
        }
        
        // Check if we have a valid session
        if (!currentSession.id) {
            addTerminalText('No active session. Creating new session...', 'system');
            await createNewSession();
            if (!currentSession.id) {
                addTerminalText('Failed to create session. Please try again.', 'error');
                return;
            }
        }
        
        // Add a timeout to detect hanging commands
        const timeout = setTimeout(() => {
            // Provide visual feedback for long-running commands
            addTerminalText('Command is taking longer than expected...', 'system');
        }, 10000); // 10 seconds timeout
        
        // Execute the command via API
        const response = await fetch(`${API_BASE_URL}/execute-command`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-Session-Id': currentSession.id
            },
            body: JSON.stringify({ command })
        });
        
        // Clear the timeout
        clearTimeout(timeout);
        
        // Check for non-OK response
        if (!response.ok) {
            // Handle session expiration
            if (response.status === 401) {
                addTerminalText('Session expired. Creating new session and retrying...', 'system');
                await createNewSession();
                
                if (retryCount < MAX_RETRIES) {
                    setTimeout(() => {
                        executeCommand(command, retryCount + 1, true);
                    }, RETRY_DELAY);
                    return;
                } else {
                    throw new Error('Session expired and max retries reached');
                }
            } else if (response.status >= 500) {
                // Server errors - retry with backoff
                if (retryCount < MAX_RETRIES) {
                    addTerminalText(`Server error (${response.status}). Retrying command...`, 'system');
                    setTimeout(() => {
                        executeCommand(command, retryCount + 1, true);
                    }, RETRY_DELAY * (retryCount + 1)); // Exponential backoff
                    return;
                }
            }
            
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update session last activity
        currentSession.lastActivity = new Date();
        updateSessionInfo();
        
        // Display the result
        if (data.error) {
            // Check if this is a system error that we should retry
            if ((data.error.includes('invalid') || data.error.includes('expired') || 
                 data.error.includes('failed')) && retryCount < MAX_RETRIES) {
                addTerminalText(`Command error: ${data.error}. Retrying...`, 'system');
                setTimeout(() => {
                    executeCommand(command, retryCount + 1, true);
                }, RETRY_DELAY * (retryCount + 1));
                return;
            } else {
                addTerminalText(data.error, 'error');
            }
        } else {
            // Show the output with proper formatting
            addTerminalText(data.output || '(Command executed with no output)', 'output');
        }
    } catch (error) {
        // Check if we should retry based on error type
        if (retryCount < MAX_RETRIES && 
            (error.message.includes('network') || 
             error.message.includes('timeout') || 
             error.message.includes('HTTP error'))) {
            
            addTerminalText(`Error: ${error.message}. Retrying (${retryCount + 1}/${MAX_RETRIES})...`, 'system');
            
            // Wait before retrying with exponential backoff
            setTimeout(() => {
                executeCommand(command, retryCount + 1, true);
            }, RETRY_DELAY * Math.pow(2, retryCount));
        } else {
            // Max retries reached or non-retryable error
            addTerminalText(`Error executing command: ${error.message}`, 'error');
            console.error('Command execution error:', error);
            
            // For session errors, try to create a new session
            if (error.message.includes('401') || error.message.includes('session')) {
                addTerminalText('Session may have expired. Try creating a new session.', 'system');
            }
        }
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
        // Clear input field before execution to prevent duplicate execution
        commandInput.value = '';
        if (command) {
            executeCommand(command);
        }
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
