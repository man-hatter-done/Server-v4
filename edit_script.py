#!/usr/bin/env python3

# A script to edit specific parts of flask_server.py

import re

# Read the file
with open('flask_server.py', 'r') as f:
    content = f.read()

# Count occurrences of the pattern we want to replace
openssl_pattern = r"# Special handling for OpenSSL commands - use our wrapper if available\s+if command\.strip\(\)\.startswith\('openssl '\):"
matches = re.finditer(openssl_pattern, content)
match_positions = [match.start() for match in matches]

if len(match_positions) != 2:
    print(f"Expected 2 matches, found {len(match_positions)}")
    exit(1)

# The first occurrence is related to the websocket handler around line 440
# Replace the entire OpenSSL handling block with our new code
openssl_block_pattern = r"# Special handling for OpenSSL commands - use our wrapper if available\s+if command\.strip\(\)\.startswith\('openssl '\):.*?print\(f\"Using direct openssl command \(wrapper not available at \{openssl_wrapper\}\)\"\)"
replacement = """# Special handling for OpenSSL commands - use our wrapper if available
    if command.strip().startswith('openssl '):
        # Use the improved OpenSSL command handler
        new_command = handle_openssl_command(command, session, session_id, auto_renewed, socketio, request.sid, setup_user_environment)
        # If handler returned None, there was an error that's already been reported
        if new_command is None:
            return
        command = new_command"""

# Use re.DOTALL to match across multiple lines
modified_content = re.sub(openssl_block_pattern, replacement, content, count=1, flags=re.DOTALL)

# Write the file back
with open('flask_server.py', 'w') as f:
    f.write(modified_content)

print("Edit completed successfully")
