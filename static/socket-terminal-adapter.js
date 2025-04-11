// Adapter script to connect new iOS-styled UI with existing socket-terminal.js functionality
document.addEventListener('DOMContentLoaded', function() {
    console.log('Socket terminal adapter loading');
    
    // Initialize UI components
    const commandInput = document.getElementById('command-input');
    const terminalOutput = document.getElementById('terminal-output');
    const clearBtn = document.getElementById('clear-btn');
    const clearTerminalBtn = document.getElementById('clear-terminal-btn');
    const endSessionBtn = document.getElementById('end-session-btn');
    const newSessionBtn = document.getElementById('new-session-btn');
    const quickCommands = document.querySelectorAll('.quick-command');
    const statusIndicator = document.getElementById('status-indicator');
    const sidebarToggle = document.querySelector('.sidebar-toggle');
    const terminalSidebar = document.querySelector('.terminal-sidebar');
    const sidebarClose = document.querySelector('.sidebar-close');
    
    // Add sidebar toggle functionality
    if (sidebarToggle && terminalSidebar) {
        sidebarToggle.addEventListener('click', function() {
            terminalSidebar.classList.add('expanded');
        });
    }
    
    // Add sidebar close functionality
    if (sidebarClose && terminalSidebar) {
        sidebarClose.addEventListener('click', function() {
            terminalSidebar.classList.remove('expanded');
        });
    }
    
    // Directly initialize socket.io connection without waiting for functions
    let socket = null;
    
    // Initialize Socket.IO
    function initSocketConnection() {
        console.log('Initializing socket connection');
        if (io) {
            try {
                socket = io(window.location.origin, {
                    reconnection: true,
                    reconnectionAttempts: 5,
                    reconnectionDelay: 1000,
                    transports: ['websocket', 'polling']
                });
                
                socket.on('connect', function() {
                    console.log('Socket connected from adapter:', socket.id);
                    addStatusMessage('Connected to server');
                    if (statusIndicator) {
                        statusIndicator.textContent = 'Connected';
                        statusIndicator.classList.remove('connecting', 'error');
                        statusIndicator.classList.add('connected');
                    }
                    
                    // Automatically create a session
                    createSession();
                });
                
                socket.on('disconnect', function(reason) {
                    console.log('Socket disconnected:', reason);
                    addStatusMessage('Disconnected from server: ' + reason);
                    if (statusIndicator) {
                        statusIndicator.textContent = 'Disconnected';
                        statusIndicator.classList.remove('connected', 'connecting');
                        statusIndicator.classList.add('error');
                    }
                });
                
                // Handle session created event
                socket.on('session_created', function(data) {
                    console.log('Session created:', data);
                    addStatusMessage('Session created: ' + data.sessionId);
                    
                    // Update session info display
                    updateSessionDisplay(data);
                    
                    // Welcome message
                    addTerminalEntry('Connected to session ' + data.sessionId, 'system');
                    addTerminalEntry('Type commands and press Enter to execute', 'system');
                });
                
                // Handle command output events
                socket.on('command_output', function(data) {
                    if (data.output) {
                        addTerminalEntry(data.output, 'output');
                    }
                });
                
                // Handle command completion
                socket.on('command_complete', function(data) {
                    console.log('Command complete:', data);
                });
                
                // Handle command errors
                socket.on('command_error', function(data) {
                    if (data.error) {
                        addTerminalEntry(data.error, 'error');
                    }
                });
                
            } catch (error) {
                console.error('Error initializing socket:', error);
                addStatusMessage('Connection error: ' + error.message);
            }
        } else {
            console.error('Socket.io library not loaded');
            addStatusMessage('Socket.io library not loaded');
        }
    }
    
    // Create a new session
    function createSession() {
        if (socket && socket.connected) {
            console.log('Creating new session');
            socket.emit('create_session', {
                userId: 'ios-terminal-user-' + Date.now()
            });
        } else {
            console.error('Cannot create session - socket not connected');
            addStatusMessage('Cannot create session - not connected');
        }
    }
    
    // Execute a command
    function executeCommandAdapter(command) {
        if (!command || typeof command !== 'string') return;
        
        // Display command in terminal
        addTerminalEntry(command, 'command');
        
        // Send command to server
        if (socket && socket.connected) {
            socket.emit('execute_command', {
                command: command
            });
        } else {
            addTerminalEntry('Not connected to server. Please refresh the page.', 'error');
        }
    }
    
    // Add entry to terminal
    function addTerminalEntry(text, type) {
        if (!terminalOutput || !text) return;
        
        const entry = document.createElement('div');
        entry.className = `command-entry ${type || 'output'}`;
        
        if (type === 'command') {
            entry.textContent = '$ ' + text;
        } else {
            entry.textContent = text;
        }
        
        terminalOutput.appendChild(entry);
        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }
    
    // Add status message (not visible in terminal)
    function addStatusMessage(message) {
        console.log('Status:', message);
    }
    
    // Update session info display
    function updateSessionDisplay(sessionData) {
        if (!sessionData) return;
        
        const sessionIdElement = document.getElementById('session-id');
        const sessionCreatedElement = document.getElementById('session-created');
        
        if (sessionIdElement && sessionData.sessionId) {
            sessionIdElement.textContent = sessionData.sessionId;
        }
        
        if (sessionCreatedElement) {
            const created = new Date().toLocaleString();
            sessionCreatedElement.textContent = created;
        }
    }
    
    // Start socket connection
    initSocketConnection();
    
    // Handle command input
    if (commandInput) {
        commandInput.addEventListener('keydown', function(event) {
            if (event.key === 'Enter') {
                const command = commandInput.value.trim();
                if (command) {
                    executeCommandAdapter(command);
                    commandInput.value = '';
                }
                event.preventDefault();
            }
        });
    }
    
    // Connect UI buttons
    
    // Also check if the original functions are loaded (backwards compatibility)
    setTimeout(function() {
        if (window.executeCommand && window.createNewSession && window.clearTerminal && window.endSession) {
            console.log('Original socket terminal functions also found');
            
            // Handle clear button clicks
            if (clearBtn) {
                clearBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    window.clearTerminal();
                });
            }
            
            // Connect clear terminal button
            if (clearTerminalBtn) {
                clearTerminalBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    window.clearTerminal();
                });
            }
            
            // Connect end session button
            if (endSessionBtn) {
                endSessionBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    window.endSession();
                });
            }
            
            // Connect new session button
            if (newSessionBtn) {
                newSessionBtn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    window.createNewSession();
                });
            }
            
            // Connect quick command buttons
            quickCommands.forEach(function(btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    e.stopPropagation();
                    const command = btn.getAttribute('data-command');
                    if (command) {
                        commandInput.value = command;
                        window.executeCommand(command);
                    }
                });
            });
            
            // Custom addTerminalText function to override the one in socket-terminal.js
            window.customAddTerminalText = function(text, type) {
                // Create a new terminal entry
                const entryDiv = document.createElement('div');
                entryDiv.className = `command-entry ${type}`;
                
                if (type === 'command') {
                    entryDiv.textContent = `$ ${text}`;
                } else {
                    entryDiv.textContent = text;
                }
                
                terminalOutput.appendChild(entryDiv);
                
                // Scroll to bottom
                terminalOutput.scrollTop = terminalOutput.scrollHeight;
                
                // Performance optimization: remove old entries if there are too many
                const maxEntries = 1000;
                while (terminalOutput.childElementCount > maxEntries) {
                    terminalOutput.removeChild(terminalOutput.firstChild);
                }
            };
            
            // Override addTerminalText if it exists
            if (window.addTerminalText) {
                const originalAddTerminalText = window.addTerminalText;
                window.addTerminalText = function(text, type) {
                    // Call both implementations to ensure compatibility
                    originalAddTerminalText(text, type);
                    window.customAddTerminalText(text, type);
                };
            }
            
            // Mobile sidebar toggle for small screens
            if (window.innerWidth < 768) {
                const terminalSidebar = document.querySelector('.terminal-sidebar');
                
                // Add sidebar handle if it doesn't exist
                if (terminalSidebar && !document.querySelector('.sidebar-handle')) {
                    const handle = document.createElement('div');
                    handle.className = 'sidebar-handle';
                    terminalSidebar.prepend(handle);
                    
                    handle.addEventListener('click', function() {
                        terminalSidebar.classList.toggle('expanded');
                    });
                }
            }
        } else {
            console.error('Socket terminal functions not found');
            // Display error message
            if (terminalOutput) {
                const errorDiv = document.createElement('div');
                errorDiv.className = 'command-entry error';
                errorDiv.textContent = 'Error: Terminal functionality not loaded properly. Please refresh the page.';
                terminalOutput.appendChild(errorDiv);
            }
        }
        
        // Focus input field on load
        if (commandInput) {
            setTimeout(function() {
                commandInput.focus();
            }, 500);
        }
    }, 1000); // Wait 1 second for socket-terminal.js to initialize
    
    // Connect quick commands directly to the adapter
    if (quickCommands) {
        quickCommands.forEach(function(btn) {
            btn.addEventListener('click', function(e) {
                e.preventDefault();
                e.stopPropagation();
                const command = btn.getAttribute('data-command');
                if (command) {
                    executeCommandAdapter(command);
                }
            });
        });
    }
    
    // Connect new session button to the adapter
    if (newSessionBtn) {
        newSessionBtn.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
            initSocketConnection();
        });
    }
    
    // Connect clear terminal button to the adapter
    if (clearBtn) {
        clearBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (terminalOutput) {
                // Keep only status messages
                const statusMessages = terminalOutput.querySelectorAll('.command-entry.system');
                terminalOutput.innerHTML = '';
                statusMessages.forEach(msg => terminalOutput.appendChild(msg.cloneNode(true)));
                addTerminalEntry('Terminal cleared', 'system');
            }
        });
    }
    
    if (clearTerminalBtn) {
        clearTerminalBtn.addEventListener('click', function(e) {
            e.preventDefault();
            if (terminalOutput) {
                // Keep only status messages
                const statusMessages = terminalOutput.querySelectorAll('.command-entry.system');
                terminalOutput.innerHTML = '';
                statusMessages.forEach(msg => terminalOutput.appendChild(msg.cloneNode(true)));
                addTerminalEntry('Terminal cleared', 'system');
            }
        });
    }
});
