// Adapter script to connect new iOS-styled UI with existing socket-terminal.js functionality
document.addEventListener('DOMContentLoaded', function() {
    // Initialize UI components
    const commandInput = document.getElementById('command-input');
    const terminalOutput = document.getElementById('terminal-output');
    const clearBtn = document.getElementById('clear-btn');
    const clearTerminalBtn = document.getElementById('clear-terminal-btn');
    const endSessionBtn = document.getElementById('end-session-btn');
    const newSessionBtn = document.getElementById('new-session-btn');
    const quickCommands = document.querySelectorAll('.quick-command');
    const statusIndicator = document.getElementById('status-indicator');
    
    // Wait for socket-terminal.js to load
    setTimeout(function() {
        // Connect event listeners to the new UI elements
        if (window.executeCommand && window.createNewSession && window.clearTerminal && window.endSession) {
            console.log('Socket terminal functions loaded successfully');
            
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
});
