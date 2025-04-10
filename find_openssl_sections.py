#!/usr/bin/env python3

# Script to find all the OpenSSL handling sections in the code

with open('flask_server.py', 'r') as f:
    lines = f.readlines()

# Find all occurrences of OpenSSL handling
openssl_starts = []
for i, line in enumerate(lines):
    if "if command.strip().startswith('openssl ')" in line:
        openssl_starts.append(i)

print(f"Found {len(openssl_starts)} OpenSSL sections at lines: {openssl_starts}")

# For each section, print the first few lines to verify
for start_line in openssl_starts:
    print(f"\nOpenSSL section at line {start_line + 1}:")
    # Print 10 lines of context
    for i in range(start_line, min(start_line + 10, len(lines))):
        print(f"{i+1}: {lines[i].rstrip()}")
