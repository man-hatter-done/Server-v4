#!/usr/bin/env python3

with open('flask_server.py', 'r') as f:
    lines = f.readlines()

# We need to check all context around the line that might have issues
start_line = 590
end_line = 620

print("Exact character dump around line 602:")
for i in range(start_line, end_line):
    if i < len(lines):
        line = lines[i]
        # Format for seeing actual spaces, tabs, etc.
        char_repr = ''.join([f"'{c}'" if c in ' \t\n\r' else c for c in line])
        print(f"Line {i+1}: {char_repr}")
