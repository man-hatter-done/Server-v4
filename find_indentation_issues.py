#!/usr/bin/env python3

import re

with open('flask_server.py', 'r') as f:
    lines = f.readlines()

# Check for lines with just 'return' and track indentation
for i, line in enumerate(lines):
    # Skip empty lines
    if not line.strip():
        continue
    
    # Look for standalone return statements or return with a value
    if re.match(r'
^
\s+return\s*(?:\S.*)?$', line):
        # Count spaces before 'return'
        leading_spaces = len(line) - len(line.lstrip())
        # Check if indentation is not a multiple of 4 (most common in Python)
        if leading_spaces % 4 != 0:
            print(f"Line {i+1}: Abnormal indentation ({leading_spaces} spaces): {line.rstrip()}")
        
        # Check surrounding lines to detect inconsistent indentation patterns
        if i > 0 and i < len(lines) - 1:
            prev_line_indent = len(lines[i-1]) - len(lines[i-1].lstrip()) if lines[i-1].strip() else 0
            next_line_indent = len(lines[i+1]) - len(lines[i+1].lstrip()) if lines[i+1].strip() else 0
            
            if leading_spaces != prev_line_indent and prev_line_indent > 0:
                print(f"  Previous line ({i}): {prev_line_indent} spaces: {lines[i-1].rstrip()}")
            if leading_spaces != next_line_indent and next_line_indent > 0 and "def " not in lines[i+1]:
                print(f"  Next line ({i+2}): {next_line_indent} spaces: {lines[i+1].rstrip()}")

# Specific check around line 602
line_to_check = 602
context_range = 5  # Lines before and after

start_line = max(0, line_to_check - context_range - 1)
end_line = min(len(lines), line_to_check + context_range)

print("\nDetailed analysis around line 602:")
for i in range(start_line, end_line):
    line = lines[i]
    indent = len(line) - len(line.lstrip())
    print(f"Line {i+1}: {indent} spaces: {line.rstrip()}")
