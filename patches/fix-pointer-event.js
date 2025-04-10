/**
 * Fix for [object PointerEvent] error in terminal interfaces
 * 
 * This script should be included at the top of all terminal HTML files before other scripts.
 * It provides several layers of protection against browser events being treated as commands:
 * 
 * 1. Monitors errors related to PointerEvent objects being used as commands
 * 2. Adds validation to the global window object to catch issues early
 * 3. Adds defensive checks to prevent click events from being passed to command handlers
 */

// Immediately executing function to avoid polluting global namespace
(function() {
    // Flag to track if we've already fixed the issue
    let pointerEventFixed = false;
    
    // Global error monitor to catch any PointerEvent issues
    window.addEventListener('error', function(event) {
        // Check if the error message contains PointerEvent references
        if (event.message && (
            event.message.includes('[object PointerEvent]') || 
            event.message.includes('PointerEvent') ||
            (event.message.includes('is not a function') && event.error && event.error.toString().includes('PointerEvent'))
        )) {
            console.error('Prevented PointerEvent error:', event);
            
            // Stop error propagation
            event.preventDefault();
            event.stopPropagation();
            
            // Show alert only once
            if (!pointerEventFixed) {
                pointerEventFixed = true;
                alert('Error: Browser event detected as command. Please reload the page and try again.');
            }
            
            return false;
        }
    }, true); // Use capturing to get the event before other handlers
    
    // Function to add validation to executeCommand functions
    function fixExecuteCommandFunction() {
        // Wait for the document to be ready
        if (document.readyState === 'loading') {
            document.addEventListener('DOMContentLoaded', checkAndFixFunctions);
        } else {
            checkAndFixFunctions();
        }
        
        function checkAndFixFunctions() {
            // Check for global executeCommand function
            if (typeof window.executeCommand === 'function') {
                const originalFn = window.executeCommand;
                window.executeCommand = function(command) {
                    // Validate command is not an event object
                    if (command instanceof Event) {
                        console.error('Prevented Event object from being used as command');
                        return;
                    }
                    
                    // Validate command is a string
                    if (typeof command !== 'string') {
                        try {
                            command = String(command);
                        } catch (e) {
                            console.error('Command is not a valid string:', command);
                            return;
                        }
                    }
                    
                    // Check for object string
                    if (command && command.includes('[object ') && command.includes(']')) {
                        console.error('Prevented object string from being used as command:', command);
                        return;
                    }
                    
                    // Call the original function with validated command
                    return originalFn.apply(this, arguments);
                };
                console.log('Added validation to executeCommand function');
            }
            
            // Add click event protection for terminal containers
            const terminalContainers = document.querySelectorAll('.terminal-container, .terminal-output');
            terminalContainers.forEach(container => {
                // Add protection only if not already added
                if (!container.dataset.eventProtected) {
                    container.dataset.eventProtected = 'true';
                    
                    container.addEventListener('click', function(event) {
                        // Prevent event from being passed as a command
                        event.stopPropagation();
                    }, true); // Use capturing to get event before other handlers
                    
                    console.log('Added event protection to terminal container', container);
                }
            });
        }
    }
    
    // Run the fix
    fixExecuteCommandFunction();
    
    // Also run after any script loads (in case functions are defined later)
    document.addEventListener('DOMNodeInserted', function(e) {
        if (e.target.tagName === 'SCRIPT') {
            setTimeout(fixExecuteCommandFunction, 100);
        }
    });
    
    console.log('PointerEvent protection installed');
})();
