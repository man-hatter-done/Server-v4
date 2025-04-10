#!/usr/bin/env python3

with open('flask_server.py', 'r') as f:
    lines = f.readlines()

# Let's check around line 602 specifically
start_line = max(0, 602 - 5 - 1)  # 5 lines before line 602
end_line = min(len(lines), 602 + 5)  # 5 lines after line 602

print("Analysis around line 602:")
for i in range(start_line, end_line):
    line = lines[i].rstrip('\n')
    indent = len(line) - len(line.lstrip())
    # Show the actual characters for each space to spot any tabs or irregular whitespace
    spaces = ' ' * indent
    print(f"Line {i+1}: {indent} spaces | {repr(spaces)} | {line}")
