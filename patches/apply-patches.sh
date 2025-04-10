#!/bin/bash
# Apply patches to fix the PointerEvent issues across all terminal HTML files

# Create directory for backup files
mkdir -p backups

# Add the JS fix to all HTML files that contain terminal functionality
for file in static/*.html; do
  echo "Patching $file..."
  # Create backup
  cp "$file" "backups/$(basename $file).bak"
  
  # Check if file already contains our fix
  if grep -q "pointerEventFixed" "$file"; then
    echo "  Fix already applied, skipping."
    continue
  fi
  
  # Insert our fix right after the opening <head> tag
  awk '
  /<head>/ {
    print $0;
    print "    <!-- PointerEvent fix -->";
    print "    <script src=\"/patches/fix-pointer-event.js\"></script>";
    next;
  }
  {print}
  ' "$file" > "${file}.tmp"
  
  mv "${file}.tmp" "$file"
  echo "  Patched!"
done

# Create directory for the patches
mkdir -p static/patches
cp patches/fix-pointer-event.js static/patches/

# Apply server-side fix to flask_server.py
echo "Patching flask_server.py..."
cp flask_server.py backups/flask_server.py.bak

# Add object detection to command validation
sed -i 's/    command = data.get("command")/    command = data.get("command")\n    \n    # Reject any command that looks like an event object\n    if isinstance(command, str) and "[object " in command and "]" in command:\n        logger.warning(f"Rejected command that appears to be an object string: {command}")\n        return jsonify({"error": "Invalid command format: Object reference detected"}), 400/g' flask_server.py

echo "All patches applied!"
