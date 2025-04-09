#!/usr/bin/env python3

import re

# Read the code from flask_server.py
with open('flask_server.py', 'r') as f:
    code = f.read()

# Read our improved handler from the temporary file
from openssl_improved import get_openssl_handler_code
new_handler = get_openssl_handler_code()

# Find the pattern for the existing OpenSSL handler in the WebSocket section
pattern = r'(# Special handling for OpenSSL commands.*?to=request\.sid\))'
# Add the s flag for dotall mode to match across lines
first_match = re.search(pattern, code, re.DOTALL)

if first_match:
    # Replace only the first occurrence (the one in the WebSocket handler)
    updated_code = code[:first_match.start()] + new_handler + code[first_match.end():]
    
    # Write the updated code back to flask_server.py
    with open('flask_server.py', 'w') as f:
        f.write(updated_code)
    
    print("Successfully updated flask_server.py with improved OpenSSL handler")
else:
    print("Could not find the OpenSSL handler pattern in flask_server.py")
