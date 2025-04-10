// Enhanced Terminal functionality for iOS Terminal Web Interface with WebSocket support

// Command history and state management
let commandHistory = [];
let historyPosition = -1;
let currentCommand = '';
let isExecuting = false;
let currentWorkingDirectory = '~';

// Socket.IO connection
let socket = null;
let isWebSocketMode = false;

// Store session information
let currentSession = {
    id: null,
    created: null,
    lastActivity: null,
    expiresIn: null,
    reconnectAttempts: 0
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
const promptElement = document.getElementById('prompt-text');
const statusIndicator = document.getElementById('status-indicator');
const progressBar = document.getElementById('progress-bar');
const themeSelector = document.getElementById('theme-selector');
const fontSizeSelector = document.getElementById('font-size-selector');
const terminalContainer = document.querySelector('.terminal-container');
const mobileMenuBtn = document.getElementById('mobile-menu-btn');
const controlPanel = document.querySelector('.control-panel');

// Initialize terminal
document.addEventListener('DOMContentLoaded', () => {
    // Load command history from localStorage
    loadCommandHistory();
    
    // Add event listeners with explicit event handling
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
    
    // Theme selector
    if (themeSelector) {
        themeSelector.addEventListener('change', (e) => {
            e.stopPropagation();
            document.body.setAttribute('data-theme', e.target.value);
            localStorage.setItem('terminal-theme', e.target.value);
        });
        
        // Load saved theme preference
        const savedTheme = localStorage.getItem('terminal-theme') || 'dark';
        themeSelector.value = savedTheme;
        document.body.setAttribute('data-theme', savedTheme);
    }
    
    // Font size selector
    if (fontSizeSelector) {
        fontSizeSelector.addEventListener('change', (e) => {
            e.stopPropagation();
            document.documentElement.style.setProperty('--font-size', e.target.value + 'px');
            localStorage.setItem('terminal-font-size', e.target.value);
        });
        
        // Load saved font size
        const savedFontSize = localStorage.getItem('terminal-font-size') || '14';
        fontSizeSelector.value = savedFontSize;
        document.documentElement.style.setProperty('--font-size', savedFontSize + 'px');
    }
    
    // Mobile menu toggle
    if (mobileMenuBtn) {
        mobileMenuBtn.addEventListener('click', (event) => {
            event.preventDefault();
            event.stopPropagation();
            controlPanel.classList.toggle('visible');
        });
    }
    
    // Make sure input is always focused when clicking anywhere in the terminal
    terminalContainer.addEventListener('click', (event) => {
        // Prevent the click event from being used as a command
        event.stopPropagation();
    
        // Only focus if not selecting text
        if (!isSelectingText()) {
            commandInput.focus();
        }
    });
    
    // Initialize Socket.IO if available
    initializeSocket();
    
    // Create initial session
    createNewSession();
    
    // Focus input
    commandInput.focus();
});

// Initialize Socket.IO connection
function initializeSocket() {
    try {
        // Check if Socket.IO is available
        if (typeof io !== 'undefined') {
            setStatus('connecting');
            
            // Connect to Socket.IO server
            socket = io(window.location.origin, {
                transports: ['websocket', 'polling'],  // Allow fallback to polling if websocket fails
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 1000,
                timeout: 10000
            });
            
            // Connection events
            socket.on('connect', () => {
                console.log('Socket connected:', socket.id);
                setStatus('connected');
                isWebSocketMode = true;
                
                // Join session room if we have a session
                if (currentSession.id) {
                    socket.emit('join_session', { session_id: currentSession.id });
                }
                
                addTerminalText('🔌 Connected using WebSockets for real-time interaction', 'system');
            });
            
            socket.on('disconnect', () => {
                console.log('Socket disconnected');
                setStatus('disconnected');
            });
            
            socket.on('connect_error', (error) => {
                console.error('Socket connection error:', error);
                setStatus('error');
                isWebSocketMode = false;
                
                // Fall back to HTTP mode
                addTerminalText('WebSocket connection failed, falling back to HTTP mode', 'warning');
            });
            
            // Terminal-specific events
            socket.on('session_created', (data) => {
                handleSocketSessionCreated(data);
            });
            
            socket.on('command_output', (data) => {
                handleSocketCommandOutput(data);
            });
            
            socket.on('command_error', (data) => {
                handleSocketCommandError(data);
            });
            
            socket.on('command_complete', (data) => {
                handleSocketCommandComplete(data);
            });
            
            socket.on('session_expired', (data) => {
                handleSocketSessionExpired(data);
            });
            
            socket.on('working_directory', (data) => {
                if (data.path) {
                    currentWorkingDirectory = data.path;
                    updatePrompt();
                }
            });
        } else {
            console.log('Socket.IO not available, using HTTP mode');
            isWebSocketMode = false;
        }
    } catch (error) {
        console.error('Error initializing Socket.IO:', error);
        isWebSocketMode = false;
    }
}

// Check if user is selecting text
function isSelectingText() {
    const selection = window.getSelection();
    return selection.toString().length > 0;
}

// Load command history from localStorage
function loadCommandHistory() {
    try {
        const savedHistory = localStorage.getItem('command-history');
        if (savedHistory) {
            commandHistory = JSON.parse(savedHistory);
        }
    } catch (e) {
        console.error('Failed to load command history:', e);
        commandHistory = [];
    }
}

// Save command history to localStorage
function saveCommandHistory() {
    try {
        // Only keep last 100 commands
        const trimmedHistory = commandHistory.slice(-100);
        localStorage.setItem('command-history', JSON.stringify(trimmedHistory));
    } catch (e) {
        console.error('Failed to save command history:', e);
    }
}

// Display status indicator
function setStatus(status) {
    if (!statusIndicator) return;
    
    statusIndicator.className = 'status-indicator';
    statusIndicator.classList.add(status);
    
    let text = '';
    switch (status) {
        case 'connected':
            text = 'Connected';
            break;
        case 'connecting':
            text = 'Connecting...';
            break;
        case 'error':
            text = 'Connection Error';
            break;
        case 'executing':
            text = 'Executing...';
            break;
        default:
            text = 'Disconnected';
    }
    
    statusIndicator.textContent = text;
}

// Create a new terminal session
async function createNewSession() {
    // Clear any existing session information
    currentSession = {
        id: null,
        created: null,
        lastActivity: null,
        expiresIn: null,
        reconnectAttempts: 0
    };
    
    setStatus('connecting');
    showProgress(true);
    addTerminalText('Creating new terminal session...', 'system');
    
    // Use WebSockets if available
    if (isWebSocketMode && socket && socket.connected) {
        // Request new session via Socket.IO
        socket.emit('create_session', {
            userId: 'web-terminal-' + Date.now()
        });
        return;
    }
    
    // Fall back to HTTP mode
    try {
        const response = await fetch(`${API_BASE_URL}/create-session`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({
                userId: 'web-terminal-' + Date.now()
            })
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            setStatus('error');
            addTerminalText(`Error: ${data.error}`, 'error');
            return;
        }
        
        // Store session information
        currentSession = {
            id: data.sessionId,
            created: new Date(),
            lastActivity: new Date(),
            expiresIn: data.expiresIn,
            reconnectAttempts: 0
        };
        
        // Update session info display
        updateSessionInfo();
        setStatus('connected');
        
        // Update terminal prompt with working directory
        updatePrompt();
        
        // Welcome message
        addTerminalText('Session created successfully.', 'success');
        addTerminalText('\n📱 Welcome to iOS Terminal', 'welcome');
        addTerminalText('Type commands and press Enter to execute.', 'system');
        addTerminalText('Use up/down arrows to navigate command history.', 'system');
        addTerminalText('Type "help" for available commands.', 'system');
        addTerminalText('\nSome commands to try:', 'system');
        addTerminalText('  ls, pwd, echo $PATH', 'example');
        addTerminalText('  python3 --version', 'example');
        addTerminalText('  mkdir test && cd test && touch file.txt && ls -la', 'example');
        addTerminalText('', 'spacer');
        
    } catch (error) {
        setStatus('error');
        addTerminalText(`Connection error: ${error.message}`, 'error');
        addTerminalText('Retrying in 5 seconds...', 'system');
        console.error('Session creation error:', error);
        
        // Retry connection after 5 seconds
        currentSession.reconnectAttempts++;
        const retryDelay = Math.min(5000 * currentSession.reconnectAttempts, 30000);
        
        setTimeout(() => {
            if (!currentSession.id) {
                createNewSession();
            }
        }, retryDelay);
    } finally {
        showProgress(false);
    }
}

// Update the terminal prompt
function updatePrompt() {
    if (promptElement) {
        promptElement.textContent = `${currentWorkingDirectory} $`;
    }
}

// Show or hide progress bar
function showProgress(visible) {
    if (progressBar) {
        progressBar.style.display = visible ? 'block' : 'none';
    }
}

// Handle built-in commands
function handleBuiltInCommands(command) {
    const lowerCommand = command.toLowerCase().trim();
    
    // Clear terminal command
    if (lowerCommand === 'clear' || lowerCommand === 'cls') {
        clearTerminal();
        return true;
    }
    
    // Help command
    if (lowerCommand === 'help') {
        showHelpMessage();
        return true;
    }
    
    // Change directory - we'll track the pwd ourselves
    if (lowerCommand.startsWith('cd ')) {
        // We'll still pass cd to the server, but also update our local path tracking
        const newPath = lowerCommand.substring(3).trim();
        
        // Simulate basic path resolution
        if (newPath === '~' || newPath === '') {
            currentWorkingDirectory = '~';
        } else if (newPath === '..') {
            if (currentWorkingDirectory !== '~') {
                const parts = currentWorkingDirectory.split('/');
                parts.pop();
                currentWorkingDirectory = parts.join('/') || '~';
            }
        } else if (newPath.startsWith('/')) {
            currentWorkingDirectory = newPath;
        } else {
            if (currentWorkingDirectory === '~') {
                currentWorkingDirectory = `~/${newPath}`;
            } else {
                currentWorkingDirectory = `${currentWorkingDirectory}/${newPath}`;
            }
        }
        
        updatePrompt();
        // We'll still let the server execute the real command
        return false;
    }
    
    return false;
}

// Show help message
function showHelpMessage() {
    addTerminalText('\n📚 Available Commands', 'help-header');
    addTerminalText('System Commands:', 'help-category');
    addTerminalText('  clear, cls       Clear the terminal screen', 'help-command');
    addTerminalText('  help             Show this help message', 'help-command');
    
    addTerminalText('\nLinux Commands (examples):', 'help-category');
    addTerminalText('  ls, pwd, cd      File navigation', 'help-command');
    addTerminalText('  mkdir, touch     File creation', 'help-command');
    addTerminalText('  cat, echo        Text output', 'help-command');
    addTerminalText('  python3          Run Python', 'help-command');
    addTerminalText('  pip install      Install Python packages', 'help-command');
    
    addTerminalText('\nTips:', 'help-category');
    addTerminalText('  • Use up/down arrows to navigate command history', 'help-tip');
    addTerminalText('  • Chain commands with && or ;', 'help-tip');
    addTerminalText('  • Run commands in background with &', 'help-tip');
    addTerminalText('  • All changes persist between sessions in your home directory', 'help-tip');
    addTerminalText('', 'spacer');
}

// Execute command in the terminal session with retry capability
async function executeCommand(command, retryCount = 0, isRetry = false) {
    // Make sure command is a string to prevent issues when clicking accidentally passes event objects
    if (typeof command !== 'string') {
        console.error('Invalid command type received:', typeof command);
        if (command instanceof Event) {
            console.error('Received an Event object instead of a command string');
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
    
    if (!command.trim()) return;
    
    // Add to command history (only if not a retry)
    if (!isRetry && (commandHistory.length === 0 || commandHistory[commandHistory.length - 1] !== command)) {
        commandHistory.push(command);
        saveCommandHistory();
    }
    historyPosition = -1;
    
    // Check for built-in commands
    if (handleBuiltInCommands(command)) {
        return;
    }
    
    // Only display the command if this is not a retry attempt
    if (!isRetry) {
        addTerminalText(command, 'command');
    }
    
    // Set executing state
    isExecuting = true;
    setStatus('executing');
    showProgress(true);
    
    // Check if we have a valid session
    if (!currentSession.id) {
        addTerminalText('No active session. Creating new session...', 'system');
        await createNewSession();
        if (!currentSession.id) {
            addTerminalText('Failed to create session. Please try again.', 'error');
            return;
        }
    }
    
    // Use WebSockets if available
    if (isWebSocketMode && socket && socket.connected) {
        // Send command to server via Socket.IO
        socket.emit('execute_command', {
            command: command,
            session_id: currentSession.id
        });
        return;
    }
    
    // Fall back to HTTP mode if WebSockets not available
    const MAX_RETRIES = 3;
    const RETRY_DELAY = 1000; // 1 second delay between retries
    
    try {
        // Add a timeout to detect hanging commands
        const timeout = setTimeout(() => {
            // Not aborting the fetch, but providing visual feedback
            if (isExecuting) {
                addTerminalText('Command is taking longer than expected...', 'warning');
            }
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
        
        // Clear the timeout since we got a response
        clearTimeout(timeout);
        
        if (!response.ok) {
            // Handle specific error cases
            if (response.status === 401) {
                // Session expired - create new session and retry
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
            } else if (response.status === 500 || response.status === 502 || response.status === 503 || response.status === 504) {
                // Server errors - retry
                if (retryCount < MAX_RETRIES) {
                    addTerminalText(`Server error (${response.status}). Retrying command in ${RETRY_DELAY/1000} second${RETRY_DELAY/1000 !== 1 ? 's' : ''}...`, 'system');
                    setTimeout(() => {
                        executeCommand(command, retryCount + 1, true);
                    }, RETRY_DELAY * (retryCount + 1)); // Exponential backoff
                    return;
                } else {
                    throw new Error(`Server error ${response.status} after ${MAX_RETRIES} retries`);
                }
            }
            
            throw new Error(`HTTP error ${response.status}`);
        }
        
        const data = await response.json();
        
        // Update session last activity
        currentSession.lastActivity = new Date();
        currentSession.reconnectAttempts = 0;
        updateSessionInfo();
        
        // Display the result
        if (data.error) {
            // Check if this is a recoverable error
            if (data.error.includes('invalid') || data.error.includes('expired') || data.error.includes('failed')) {
                if (retryCount < MAX_RETRIES) {
                    addTerminalText(`Command error: ${data.error}. Retrying...`, 'warning');
                    setTimeout(() => {
                        executeCommand(command, retryCount + 1, true);
                    }, RETRY_DELAY * (retryCount + 1)); // Exponential backoff
                    return;
                } else {
                    addTerminalText(`Command failed after ${MAX_RETRIES} attempts: ${data.error}`, 'error');
                    addTerminalText('Try executing the command again manually', 'system');
                }
            } else {
                // Normal command error (not a system error)
                addTerminalText(data.error, 'error');
            }
        } else {
            // Check if we need to update our working directory after a pwd command
            if (command.trim() === 'pwd') {
                try {
                    // Update working directory based on pwd output
                    let pwd = data.output.trim();
                    if (pwd) {
                        currentWorkingDirectory = pwd;
                        updatePrompt();
                    }
                } catch (e) {
                    console.error('Error updating working directory:', e);
                }
            }
            
            // Show the output with proper formatting
            addTerminalText(data.output || '(Command executed with no output)', 'output');
        }
        
        setStatus('connected');
    } catch (error) {
        setStatus('error');
        
        // Check if we should retry
        if (retryCount < MAX_RETRIES && 
            (error.message.includes('HTTP error') || 
             error.message.includes('network') || 
             error.message.includes('timeout'))) {
            
            addTerminalText(`Error: ${error.message}. Retrying (${retryCount + 1}/${MAX_RETRIES})...`, 'warning');
            console.error(`Command execution error (retry ${retryCount + 1}):`, error);
            
            // Wait before retrying with exponential backoff
            setTimeout(() => {
                executeCommand(command, retryCount + 1, true);
            }, RETRY_DELAY * Math.pow(2, retryCount));
            return;
        }
        
        // Max retries reached or non-retryable error
        addTerminalText(`Error executing command: ${error.message}`, 'error');
        console.error('Command execution error:', error);
        
        // If we've lost connection, attempt to reconnect
        if (error.message.includes('HTTP error 401')) {
            addTerminalText('Session expired or invalid. Creating new session...', 'system');
            createNewSession();
        }
    } finally {
        // Only set as not executing if we're not retrying
        if (!isRetry || retryCount >= MAX_RETRIES) {
            isExecuting = false;
            showProgress(false);
        }
    }
}

// Add text to the terminal output
function addTerminalText(text, type = 'output') {
    const entryDiv = document.createElement('div');
    entryDiv.className = `command-entry ${type}`;
    
    if (type === 'command') {
        const promptSpan = document.createElement('span');
        promptSpan.className = 'prompt-span';
        promptSpan.textContent = `${currentWorkingDirectory} $ `;
        
        const commandSpan = document.createElement('span');
        commandSpan.className = 'command-text';
        commandSpan.textContent = text;
        
        entryDiv.appendChild(promptSpan);
        entryDiv.appendChild(commandSpan);
    } else if (type === 'output-stream') {
        // For streaming output (WebSockets), append to the last output element if it exists
        const lastEntry = terminalOutput.lastElementChild;
        if (lastEntry && lastEntry.classList.contains('output-stream')) {
            lastEntry.textContent += text;
            
            // Scroll to bottom
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
            return;
        }
        
        // Otherwise create a new output element
        entryDiv.textContent = text;
    } else {
        // Special handling for different output types
        entryDiv.innerHTML = text;
    }
    
    terminalOutput.appendChild(entryDiv);
    
    // Scroll to bottom
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}

// Socket.IO-specific event handlers
function handleSocketSessionCreated(data) {
    showProgress(false);
    
    if (data.error) {
        setStatus('error');
        addTerminalText(`Error creating session: ${data.error}`, 'error');
        return;
    }
    
    // Store session information
    currentSession = {
        id: data.sessionId,
        created: new Date(),
        lastActivity: new Date(),
        expiresIn: data.expiresIn,
        reconnectAttempts: 0
    };
    
    // Join session room
    socket.emit('join_session', { session_id: data.sessionId });
    
    // Update session info display
    updateSessionInfo();
    setStatus('connected');
    
    // Update terminal prompt with working directory
    if (data.workingDirectory) {
        currentWorkingDirectory = data.workingDirectory;
    }
    updatePrompt();
    
    // Welcome message
    addTerminalText('Session created successfully.', 'success');
    addTerminalText('\n📱 Welcome to iOS Terminal', 'welcome');
    addTerminalText('Type commands and press Enter to execute.', 'system');
    addTerminalText('Using WebSockets for real-time command execution.', 'system');
    addTerminalText('Use up/down arrows to navigate command history.', 'system');
    addTerminalText('Type "help" for available commands.', 'system');
    addTerminalText('\nSome commands to try:', 'system');
    addTerminalText('  ls, pwd, echo $PATH', 'example');
    addTerminalText('  python3 --version', 'example');
    addTerminalText('  mkdir test && cd test && touch file.txt && ls -la', 'example');
    addTerminalText('', 'spacer');
}

function handleSocketCommandOutput(data) {
    if (data.output) {
        addTerminalText(data.output, 'output-stream');
    }
    
    // Update session last activity
    if (currentSession && currentSession.id) {
        currentSession.lastActivity = new Date();
        updateSessionInfo();
    }
    
    // If session was renewed, update session info
    if (data.sessionRenewed && data.newSessionId) {
        addTerminalText(`Session renewed with ID: ${data.newSessionId.substring(0, 8)}...`, 'system');
        currentSession.id = data.newSessionId;
        currentSession.created = new Date();
        updateSessionInfo();
        
        // Join the new session room
        socket.emit('join_session', { session_id: data.newSessionId });
    }
}

function handleSocketCommandError(data) {
    setStatus('connected');
    showProgress(false);
    isExecuting = false;
    
    if (data.error) {
        addTerminalText(data.error, 'error');
    }
    
    if (data.exitCode) {
        addTerminalText(`Command exited with code: ${data.exitCode}`, 'system');
    }
    
    // If session was renewed, update session info
    if (data.sessionRenewed && data.newSessionId) {
        addTerminalText(`Session renewed with ID: ${data.newSessionId.substring(0, 8)}...`, 'system');
        currentSession.id = data.newSessionId;
        currentSession.created = new Date();
        updateSessionInfo();
        
        // Join the new session room
        socket.emit('join_session', { session_id: data.newSessionId });
    }
}

function handleSocketCommandComplete(data) {
    setStatus('connected');
    showProgress(false);
    isExecuting = false;
    
    // Update session last activity
    currentSession.lastActivity = new Date();
    updateSessionInfo();
    
    // Check if we need to update the working directory
    if (data.workingDirectory) {
        currentWorkingDirectory = data.workingDirectory;
        updatePrompt();
    }
    
    // If session was renewed, update session info
    if (data.sessionRenewed && data.newSessionId) {
        addTerminalText(`Session renewed with ID: ${data.newSessionId.substring(0, 8)}...`, 'system');
        currentSession.id = data.newSessionId;
        currentSession.created = new Date();
        updateSessionInfo();
        
        // Join the new session room
        socket.emit('join_session', { session_id: data.newSessionId });
    }
}

function handleSocketSessionExpired(data) {
    addTerminalText('Session expired. Creating new session...', 'system');
    createNewSession();
}

// Handle command input (keydown event)
function handleCommandInput(event) {
    // Do nothing if we're executing a command
    if (isExecuting) {
        event.preventDefault();
        return;
    }
    
    // Handle Enter key
    if (event.key === 'Enter') {
        const command = commandInput.value.trim();
        if (command) {
            executeCommand(command);
            commandInput.value = '';
            currentCommand = '';
        }
        event.preventDefault();
        return;
    }
    
    // Handle Up Arrow (command history)
    if (event.key === 'ArrowUp') {
        event.preventDefault();
        
        if (commandHistory.length === 0) return;
        
        // Save current command if we're just starting to navigate
        if (historyPosition === -1) {
            currentCommand = commandInput.value;
        }
        
        // Navigate up in history
        historyPosition = Math.min(historyPosition + 1, commandHistory.length - 1);
        commandInput.value = commandHistory[commandHistory.length - 1 - historyPosition];
        
        // Move cursor to end of input
        setTimeout(() => {
            commandInput.selectionStart = commandInput.selectionEnd = commandInput.value.length;
        }, 0);
        return;
    }
    
    // Handle Down Arrow (command history)
    if (event.key === 'ArrowDown') {
        event.preventDefault();
        
        if (historyPosition === -1) return;
        
        // Navigate down in history
        historyPosition--;
        
        if (historyPosition === -1) {
            // Restore current command when we get back to the bottom
            commandInput.value = currentCommand;
        } else {
            commandInput.value = commandHistory[commandHistory.length - 1 - historyPosition];
        }
        
        // Move cursor to end of input
        setTimeout(() => {
            commandInput.selectionStart = commandInput.selectionEnd = commandInput.value.length;
        }, 0);
        return;
    }
    
    // Reset history position when typing
    if (event.key.length === 1 || event.key === 'Backspace' || event.key === 'Delete') {
        historyPosition = -1;
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
    
    setStatus('connecting');
    showProgress(true);
    
    // Use WebSockets if available
    if (isWebSocketMode && socket && socket.connected) {
        // Send session termination request via Socket.IO
        socket.emit('end_session', {
            session_id: currentSession.id
        });
        
        // Clear session info locally
        currentSession = {
            id: null,
            created: null,
            lastActivity: null,
            expiresIn: null,
            reconnectAttempts: 0
        };
        
        updateSessionInfo();
        setStatus('disconnected');
        showProgress(false);
        
        addTerminalText('Session terminated.', 'system');
        addTerminalText('Create a new session to continue.', 'system');
        return;
    }
    
    // Fall back to HTTP mode
    try {
        const response = await fetch(`${API_BASE_URL}/session`, {
            method: 'DELETE',
            headers: {
                'X-Session-Id': currentSession.id
            }
        });
        
        if (!response.ok) {
            throw new Error(`HTTP error ${response.status}`);
        }
        
        // Clear session info
        currentSession = {
            id: null,
            created: null,
            lastActivity: null,
            expiresIn: null,
            reconnectAttempts: 0
        };
        
        updateSessionInfo();
        setStatus('disconnected');
        addTerminalText('Session terminated.', 'system');
        addTerminalText('Create a new session to continue.', 'system');
        
    } catch (error) {
        setStatus('error');
        addTerminalText(`Error terminating session: ${error.message}`, 'error');
        console.error('Session termination error:', error);
    } finally {
        showProgress(false);
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
setInterval(() => {
    if (currentSession.id) {
        updateSessionInfo();
        
        // Check if session is about to expire and warn user
        const expiresInMs = currentSession.expiresIn;
        const elapsedMs = Date.now() - currentSession.lastActivity.getTime();
        const remainingMs = Math.max(0, expiresInMs - elapsedMs);
        
        if (remainingMs < 300000 && remainingMs > 290000) { // 5-minute warning
            addTerminalText('⚠️ Your session will expire in 5 minutes. Use any command to keep it active.', 'warning');
        }
    }
}, 30000);

// Check for keypress for focus recovery
document.addEventListener('keypress', (e) => {
    // Only handle keypresses when not in an input element
    const tagName = document.activeElement.tagName.toLowerCase();
    if (tagName !== 'input' && tagName !== 'textarea' && !isExecuting) {
        commandInput.focus();
    }
});
