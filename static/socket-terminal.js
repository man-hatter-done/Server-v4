// WebSocket-based Terminal for iOS Terminal Web Interface
// Uses Socket.IO for real-time communication

// Store session information
let currentSession = {
    id: null,
    created: null,
    lastActivity: null,
    expiresIn: null,
    reconnectAttempts: 0
};

// Command history and state management
let commandHistory = [];
let historyPosition = -1;
let currentCommand = '';
let isExecuting = false;
let currentWorkingDirectory = '~';

// Socket.IO connection
let socket = null;

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
    
    // Add event listeners
    commandInput.addEventListener('keydown', handleCommandInput);
    newSessionBtn.addEventListener('click', createNewSession);
    clearTerminalBtn.addEventListener('click', clearTerminal);
    endSessionBtn.addEventListener('click', endSession);
    
    // Theme selector
    if (themeSelector) {
        themeSelector.addEventListener('change', (e) => {
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
        mobileMenuBtn.addEventListener('click', () => {
            controlPanel.classList.toggle('visible');
        });
    }
    
    // Make sure input is always focused when clicking anywhere in the terminal
    terminalContainer.addEventListener('click', () => {
        if (!isSelectingText()) {
            commandInput.focus();
        }
    });
    
    // Initialize Socket.IO connection
    initializeSocket();
    
    // Create initial session
    createNewSession();
    
    // Focus input
    commandInput.focus();
});

// Initialize Socket.IO connection
function initializeSocket() {
    setStatus('connecting');
    
    // Close existing socket if any
    if (socket) {
        socket.disconnect();
    }
    
    // Add retry constants
    const MAX_RECONNECT_ATTEMPTS = 5;
    const RECONNECT_DELAY = 2000; // ms
    let reconnectAttempts = 0;
    
    // Connect to Socket.IO server
    socket = io(window.location.origin, {
        transports: ['websocket', 'polling'],  // Allow fallback to polling if needed
        reconnection: true,
        reconnectionAttempts: MAX_RECONNECT_ATTEMPTS,
        reconnectionDelay: RECONNECT_DELAY,
        timeout: 15000  // Increased for better reliability
    });
    
    // Connection events
    socket.on('connect', () => {
        console.log('Socket connected:', socket.id);
        setStatus('connected');
        reconnectAttempts = 0;
        
        // Join session room if we have a session
        if (currentSession.id) {
            socket.emit('join_session', { session_id: currentSession.id });
        }
    });
    
    socket.on('disconnect', (reason) => {
        console.log('Socket disconnected:', reason);
        setStatus('disconnected');
        
        // If the disconnect was not initiated by the client, try to reconnect
        if (reason === 'io server disconnect' || reason === 'transport close') {
            // The server forcibly closed the connection, try to reconnect manually
            setTimeout(() => {
                if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
                    reconnectAttempts++;
                    socket.connect();
                    addTerminalText(`Attempting to reconnect (${reconnectAttempts}/${MAX_RECONNECT_ATTEMPTS})...`, 'system');
                } else {
                    addTerminalText('⚠️ Connection to server lost. Please refresh the page.', 'error');
                }
            }, RECONNECT_DELAY);
        }
    });
    
    socket.on('connect_error', (error) => {
        console.error('Socket connection error:', error);
        setStatus('error');
        addTerminalText(`Connection error: ${error.message}. Retrying...`, 'warning');
    });
    
    socket.on('reconnect_attempt', (attempt) => {
        console.log(`Socket reconnection attempt ${attempt}`);
        reconnectAttempts = attempt;
        setStatus('connecting');
        addTerminalText(`Reconnection attempt ${attempt}/${MAX_RECONNECT_ATTEMPTS}...`, 'system');
    });
    
    socket.on('reconnect_failed', () => {
        console.error('Socket reconnection failed');
        setStatus('error');
        addTerminalText('⚠️ Connection to server lost. Please refresh the page or try again later.', 'error');
    });
    
    // Add event for when reconnection is successful
    socket.on('reconnect', (attemptNumber) => {
        console.log(`Reconnected after ${attemptNumber} attempts`);
        setStatus('connected');
        addTerminalText('✅ Reconnected to server successfully!', 'success');
        
        // Re-join the session if we have one
        if (currentSession.id) {
            socket.emit('join_session', { session_id: currentSession.id });
        }
    });
    
    // Terminal-specific events
    socket.on('session_created', (data) => {
        handleSessionCreated(data);
    });
    
    socket.on('command_output', (data) => {
        handleCommandOutput(data);
    });
    
    socket.on('command_error', (data) => {
        handleCommandError(data);
    });
    
    socket.on('command_complete', (data) => {
        handleCommandComplete(data);
    });
    
    socket.on('session_expired', (data) => {
        handleSessionExpired(data);
    });
    
    socket.on('working_directory', (data) => {
        if (data.path) {
            currentWorkingDirectory = data.path;
            updatePrompt();
        }
    });
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

// Show or hide progress bar
function showProgress(visible) {
    if (progressBar) {
        progressBar.style.display = visible ? 'block' : 'none';
    }
}

// Create a new terminal session
function createNewSession() {
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
    
    if (!socket || !socket.connected) {
        initializeSocket();
    }
    
    // Request new session via Socket.IO
    socket.emit('create_session', {
        userId: 'web-terminal-' + Date.now()
    });
}

// Handle session creation response
function handleSessionCreated(data) {
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
    currentWorkingDirectory = data.workingDirectory || '~';
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

// Update the terminal prompt
function updatePrompt() {
    if (promptElement) {
        promptElement.textContent = `${currentWorkingDirectory} $`;
    }
}

// Handle command output
function handleCommandOutput(data) {
    if (data.output) {
        addTerminalText(data.output, 'output-stream');
    }
}

// Handle command error
function handleCommandError(data) {
    setStatus('connected');
    showProgress(false);
    isExecuting = false;
    
    if (data.error) {
        addTerminalText(data.error, 'error');
    }
    
    if (data.exitCode) {
        addTerminalText(`Command exited with code: ${data.exitCode}`, 'system');
    }
}

// Handle command completion
function handleCommandComplete(data) {
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

// Handle session expired event
function handleSessionExpired(data) {
    addTerminalText('Session expired. Creating new session...', 'system');
    createNewSession();
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

// Execute command via WebSocket
function executeCommand(command) {
    // Check if command is a valid string
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
    
    // Add to command history
    if (commandHistory.length === 0 || commandHistory[commandHistory.length - 1] !== command) {
        commandHistory.push(command);
        saveCommandHistory();
    }
    historyPosition = -1;
    
    // Check for built-in commands
    if (handleBuiltInCommands(command)) {
        return;
    }
    
    // Check if we have a valid session
    if (!currentSession.id) {
        addTerminalText('No active session. Creating new session...', 'system');
        createNewSession();
        
        // Queue the command to run after session is created
        const checkSessionInterval = setInterval(() => {
            if (currentSession.id) {
                clearInterval(checkSessionInterval);
                setTimeout(() => executeCommand(command), 500);
            }
        }, 1000);
        return;
    }
    
    // Check for socket connection
    if (!socket || !socket.connected) {
        addTerminalText('Socket disconnected. Attempting to reconnect...', 'warning');
        initializeSocket();
        
        // Queue the command to run after connection is established
        socket.once('connect', () => {
            // Wait a moment to ensure session is joined
            setTimeout(() => {
                executeCommand(command);
            }, 500);
        });
        return;
    }
    
    // Display the command in the terminal
    addTerminalText(command, 'command');
    
    // Set executing state
    isExecuting = true;
    setStatus('executing');
    showProgress(true);
    
    // Set a timeout to provide feedback if the command is taking too long
    const timeoutId = setTimeout(() => {
        if (isExecuting) {
            addTerminalText('Command is taking longer than expected. Please wait...', 'system');
        }
    }, 5000);
    
    try {
        // Send command to server via Socket.IO
        socket.emit('execute_command', {
            command: command,
            session_id: currentSession.id
        });
        
        // Set a longer timeout to detect completely hung commands
        setTimeout(() => {
            if (isExecuting) {
                addTerminalText('Command execution timed out. You may need to refresh the page.', 'error');
                setStatus('error');
                isExecuting = false;
                showProgress(false);
            }
        }, 60000); // 1 minute timeout
        
    } catch (error) {
        clearTimeout(timeoutId);
        console.error('Error sending command:', error);
        addTerminalText(`Error sending command: ${error.message}`, 'error');
        isExecuting = false;
        setStatus('error');
        showProgress(false);
    }
}

// Add text to the terminal output
function addTerminalText(text, type = 'output') {
    // Safety check for empty terminal output element
    if (!terminalOutput) {
        console.warn("Terminal output element not available. Message queued.");
        
        // Queue the message to be displayed once the DOM is fully loaded
        document.addEventListener('DOMContentLoaded', () => {
            setTimeout(() => addTerminalText(text, type), 100);
        });
        return;
    }
    
    // Sanitize text to prevent XSS when using innerHTML
    const sanitizeHTML = (str) => {
        const temp = document.createElement('div');
        temp.textContent = str;
        return temp.innerHTML;
    };
    
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
        // For streaming output, append to the last output element if it exists
        const lastEntry = terminalOutput.lastElementChild;
        if (lastEntry && lastEntry.classList.contains('output-stream')) {
            // Append text, ensuring we don't grow the DOM element too large
            const currentText = lastEntry.textContent;
            // If output is getting too large, trim it to avoid performance issues
            if (currentText.length > 100000) {
                lastEntry.textContent = currentText.slice(-50000) + text;
            } else {
                lastEntry.textContent += text;
            }
            
            // Scroll to bottom
            terminalOutput.scrollTop = terminalOutput.scrollHeight;
            return;
        }
        
        // Otherwise create a new output element
        entryDiv.textContent = text;
    } else if (type === 'error' || type === 'warning') {
        // For errors and warnings, make sure they stand out
        entryDiv.textContent = text;
        entryDiv.setAttribute('role', 'alert');
        entryDiv.setAttribute('aria-live', 'assertive');
    } else {
        // Special handling for different output types
        // Use textContent for most types to prevent XSS
        if (type === 'help-header' || type === 'help-category' || type === 'help-command' || 
            type === 'help-tip' || type === 'welcome' || type === 'system' || type === 'example') {
            entryDiv.textContent = text;
        } else {
            // For backwards compatibility with existing code that uses HTML
            entryDiv.innerHTML = sanitizeHTML(text);
        }
    }
    
    terminalOutput.appendChild(entryDiv);
    
    // Scroll to bottom
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
    
    // Performance optimization: remove old entries if there are too many
    const maxEntries = 1000;
    while (terminalOutput.childElementCount > maxEntries) {
        terminalOutput.removeChild(terminalOutput.firstChild);
    }
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
function endSession() {
    if (!currentSession.id) {
        addTerminalText('No active session to terminate.', 'system');
        return;
    }
    
    setStatus('connecting');
    showProgress(true);
    
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
