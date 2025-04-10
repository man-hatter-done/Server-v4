#!/usr/bin/env python3

# This script will fix the indentation issue by rewriting the file

with open('flask_server.py', 'r') as f:
    lines = f.readlines()

# Find line 616 and fix its indentation
bad_line_index = 615  # Line 616 (0-indexed is 615)
if bad_line_index < len(lines):
    # Get the line with the potential indentation error
    bad_line = lines[bad_line_index]
    # Let's standardize its indentation to match the surrounding code
    # Get indentation of previous line
    prev_line = lines[bad_line_index - 1]
    prev_indent = len(prev_line) - len(prev_line.lstrip())
    
    # Fix the problematic line
    fixed_line = ' ' * prev_indent + bad_line.lstrip()
    
    # Replace the line in the lines list
    lines[bad_line_index] = fixed_line
    
    # Write the fixed file
    with open('flask_server.py', 'w') as f:
        f.writelines(lines)
    
    print(f"Fixed indentation on line {bad_line_index + 1}")
    print(f"Old: {repr(bad_line)}")
    print(f"New: {repr(fixed_line)}")
