#!/usr/bin/env python3

with open('flask_server.py', 'r') as f:
    lines = f.readlines()

print("Lines containing 'return' with unusual indentation:")
for i, line in enumerate(lines):
    line = line.rstrip('\n')
    if 'return' in line:
        indent = len(line) - len(line.lstrip())
        # Check if indentation is not a multiple of 4
        if indent % 4 != 0:
            print(f"Line {i+1}: {indent} spaces | {repr(line)}")
            
            # Show context
            start = max(0, i-2)
            end = min(len(lines), i+3)
            print("Context:")
            for j in range(start, end):
                context_line = lines[j].rstrip('\n')
                context_indent = len(context_line) - len(context_line.lstrip())
                print(f"  Line {j+1}: {context_indent} spaces | {context_line}")
            print()

print("\nChecking for lines with mixed indentation:")
for i, line in enumerate(lines):
    if line.strip():  # Skip empty lines
        # Check if the line contains both spaces and tabs
        if ' ' in line[:len(line) - len(line.lstrip())] and '\t' in line[:len(line) - len(line.lstrip())]:
            print(f"Line {i+1}: Mixed indentation | {repr(line)}")
