"""
Terminal Command Handler with integrated file operations

This module handles the execution of terminal commands with enhanced Linux emulation
capabilities, integrating file operations directly into the command execution process
rather than exposing them as separate HTTP endpoints.
"""

import os
import subprocess
import shutil
import threading
import signal
import time
import logging
import select
import re
from datetime import datetime
from werkzeug.utils import secure_filename

# Create a logger
logger = logging.getLogger("terminal_command_handler")

class TerminalCommandHandler:
    """
    Handles terminal commands with integrated file operations.
    Provides a more robust Linux terminal emulation experience.
    """
    
    def __init__(self):
        # Keep track of running processes
        self.processes = {}
        self.process_lock = threading.Lock()
        
    def execute_command(self, command, session_id, session_data, callback=None):
        """
        Execute a terminal command with integrated file management capabilities.
        
        Args:
            command: The command to execute
            session_id: The session ID
            session_data: Dictionary containing session data (e.g., home_dir, user_id)
            callback: Function to call with streaming output
            
        Returns:
            Dict containing command output or error
        """
        # Validate inputs
        if not command or not isinstance(command, str):
            return {"error": "Invalid command format", "exit_code": 1}
            
        if not session_id or not session_data:
            return {"error": "Invalid session", "exit_code": 1}
            
        home_dir = session_data.get('home_dir')
        if not home_dir or not os.path.isdir(home_dir):
            return {"error": f"Session directory not found: {home_dir}", "exit_code": 1}
            
        # Check for built-in file operations first and handle them directly
        file_op_result = self._handle_file_operations(command, home_dir, callback)
        if file_op_result is not None:
            return file_op_result
            
        # Add environment variables to help user-level installations
        env = os.environ.copy()
        env['HOME'] = home_dir
        env['PYTHONUSERBASE'] = os.path.join(home_dir, '.local')
        env['PATH'] = os.path.join(home_dir, '.local', 'bin') + ':' + env.get('PATH', '')
        env['USER'] = 'terminal-user'  # Provide a username for commands that need it
        env['TERM'] = 'xterm-256color'  # Standard terminal type
        
        # Source .profile instead of just .bashrc to get all environment variables
        profile_path = os.path.join(home_dir, '.profile')
        if os.path.exists(profile_path):
            source_cmd = f"source {profile_path}"
        else:
            source_cmd = "source .bashrc 2>/dev/null || true"
        
        # Execute command with bash to ensure profile or bashrc is sourced
        full_command = f'cd {home_dir} && {source_cmd}; {command}'
        
        try:
            # Start process in its own process group with stdout and stderr piped
            process = subprocess.Popen(
                full_command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,  # Line buffered
                cwd=home_dir,
                env=env,
                preexec_fn=os.setsid  # Create new process group
            )
            
            # Store process information
            with self.process_lock:
                self.processes[session_id] = {
                    'process': process,
                    'start_time': time.time()
                }
            
            # Stream output in real-time (for WebSocket)
            stdout_data = ""
            stderr_data = ""
            
            if callback:
                # Use callback for streaming (WebSocket)
                self._stream_output_with_callback(process, session_id, callback)
                return {"message": "Command execution started with streaming output"}
            else:
                # Collect output for HTTP API
                stdout_data, stderr_data = process.communicate(timeout=60)
                exit_code = process.poll() or 0
                
                # Clean up process tracking
                with self.process_lock:
                    if session_id in self.processes:
                        del self.processes[session_id]
                
                # Combine stdout and stderr
                output = stdout_data
                if stderr_data:
                    if output:
                        output += "\n" + stderr_data
                    else:
                        output = stderr_data
                
                return {
                    "output": output,
                    "exit_code": exit_code
                }
                
        except subprocess.TimeoutExpired:
            with self.process_lock:
                if session_id in self.processes:
                    try:
                        process = self.processes[session_id]['process']
                        os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    except Exception as e:
                        logger.error(f"Error terminating process: {str(e)}")
                    del self.processes[session_id]
            
            return {
                "error": "Command execution timed out",
                "exit_code": 124
            }
        except Exception as e:
            logger.error(f"Error executing command: {str(e)}")
            return {
                "error": f"Failed to execute command: {str(e)}",
                "exit_code": 1
            }

    def _stream_output_with_callback(self, process, session_id, callback):
        """Stream process output and call the callback with each chunk"""
        def stream_output():
            try:
                # File descriptors for select
                fd_stdout = process.stdout.fileno()
                fd_stderr = process.stderr.fileno()
                readable = [fd_stdout, fd_stderr]
                
                # Stream output while process is running
                while process.poll() is None:
                    # Check for available output using select with timeout
                    ready, _, _ = select.select(readable, [], [], 0.1)
                    
                    if fd_stdout in ready:
                        output = os.read(fd_stdout, 1024).decode('utf-8', errors='replace')
                        if output:
                            callback(output)
                    
                    if fd_stderr in ready:
                        error = os.read(fd_stderr, 1024).decode('utf-8', errors='replace')
                        if error:
                            callback(error)
                
                # Get any remaining output
                stdout_remainder = process.stdout.read()
                if stdout_remainder:
                    callback(stdout_remainder.decode('utf-8', errors='replace'))
                
                stderr_remainder = process.stderr.read()
                if stderr_remainder:
                    callback(stderr_remainder.decode('utf-8', errors='replace'))
                
                # Process finished
                exit_code = process.wait()
                
                # Clean up process tracking
                with self.process_lock:
                    if session_id in self.processes:
                        del self.processes[session_id]
                
                # Send command completion event with exit code
                callback("\n", exit_code=exit_code)
                
            except Exception as e:
                logger.error(f"Error in stream_output thread: {str(e)}")
                callback(f"\nError streaming command output: {str(e)}")
                
                # Clean up process tracking
                with self.process_lock:
                    if session_id in self.processes:
                        del self.processes[session_id]
        
        # Start output streaming in a separate thread
        threading.Thread(target=stream_output, daemon=True).start()

    def terminate_process(self, session_id):
        """Terminate a running process for a session"""
        with self.process_lock:
            if session_id in self.processes:
                try:
                    process_info = self.processes[session_id]
                    process = process_info['process']
                    # Send SIGTERM to the process group
                    os.killpg(os.getpgid(process.pid), signal.SIGTERM)
                    logger.info(f"Terminated process for session {session_id}")
                    return True
                except Exception as e:
                    logger.error(f"Error terminating process: {str(e)}")
                finally:
                    # Remove from tracking even if termination failed
                    del self.processes[session_id]
        return False

    def _handle_file_operations(self, command, home_dir, callback=None):
        """
        Handle file operations directly through terminal commands.
        This replaces the HTTP endpoints for file operations.
        
        Returns:
            Dict with operation result if command is a file operation, None otherwise
        """
        command = command.strip()
        
        # Check if this is an enhanced file operation command that needs special handling
        if command.startswith("ls") or command.startswith("pwd") or command.startswith("cd"):
            # These can be handled by the normal shell execution
            return None
            
        # File content commands (cat, more, less)
        if command.startswith("cat ") or command.startswith("more ") or command.startswith("less "):
            # Extract the file path from the command
            parts = command.split(" ", 1)
            if len(parts) < 2:
                return {"error": "File path required", "exit_code": 1}
                
            file_arg = parts[1].strip()
            
            # Process any quotes or special characters in the filename
            file_arg = file_arg.strip('"\'')
            
            # Handle ~ in paths
            if file_arg.startswith("~"):
                file_arg = file_arg.replace("~", home_dir, 1)
            elif not file_arg.startswith("/"):
                # Relative path
                file_arg = os.path.join(home_dir, file_arg)
            
            # Verify the path is within the home directory for security
            file_arg = os.path.normpath(file_arg)
            if not file_arg.startswith(home_dir):
                return {"error": "Access denied. Path outside of user directory.", "exit_code": 1}
                
            try:
                if not os.path.exists(file_arg):
                    return {"error": f"No such file or directory: {os.path.basename(file_arg)}", "exit_code": 1}
                    
                if os.path.isdir(file_arg):
                    return {"error": f"{os.path.basename(file_arg)} is a directory", "exit_code": 1}
                    
                # Read and return the file content
                with open(file_arg, 'r', errors='replace') as f:
                    content = f.read()
                    
                # Call callback if provided (WebSocket)
                if callback:
                    callback(content)
                    callback("\n", exit_code=0)
                    return {"message": "File content streamed", "exit_code": 0}
                    
                return {"output": content, "exit_code": 0}
                
            except Exception as e:
                logger.error(f"Error reading file: {str(e)}")
                return {"error": f"Error reading file: {str(e)}", "exit_code": 1}
        
        # File creation/editing commands
        if command.startswith("echo ") and ">" in command:
            # Parse the command to extract content and file path
            # This handles commands like: echo "content" > file.txt or echo "content" >> file.txt
            append_mode = ">>" in command
            
            # Remove the echo and determine where the redirection starts
            parts = command[5:]  # Remove 'echo '
            
            # Find the position of the first > character, handling >>
            redirect_pos = parts.find(">")
            if append_mode:
                redirect_pos = parts.find(">>")
                
            if redirect_pos == -1:
                return None  # Not a file write operation, let the shell handle it
                
            # Extract content and filepath
            content = parts[:redirect_pos].strip()
            if append_mode:
                filepath = parts[redirect_pos+2:].strip()
            else:
                filepath = parts[redirect_pos+1:].strip()
                
            # Remove quotes if present
            if content.startswith('"') and content.endswith('"'):
                content = content[1:-1]
            elif content.startswith("'") and content.endswith("'"):
                content = content[1:-1]
                
            # Handle ~ in paths
            if filepath.startswith("~"):
                filepath = filepath.replace("~", home_dir, 1)
            elif not filepath.startswith("/"):
                # Relative path
                filepath = os.path.join(home_dir, filepath)
                
            # Verify the path is within the home directory for security
            filepath = os.path.normpath(filepath)
            if not filepath.startswith(home_dir):
                return {"error": "Access denied. Path outside of user directory.", "exit_code": 1}
                
            try:
                # Create parent directories if they don't exist
                os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
                
                # Write to the file
                mode = "a" if append_mode else "w"
                with open(filepath, mode) as f:
                    f.write(content)
                    
                if callback:
                    callback(f"{'Appended to' if append_mode else 'Wrote to'} {os.path.basename(filepath)}\n")
                    callback("\n", exit_code=0)
                    return {"message": f"File {'appended' if append_mode else 'written'}", "exit_code": 0}
                    
                return {"output": f"{'Appended to' if append_mode else 'Wrote to'} {os.path.basename(filepath)}", "exit_code": 0}
                
            except Exception as e:
                logger.error(f"Error writing to file: {str(e)}")
                return {"error": f"Error writing to file: {str(e)}", "exit_code": 1}
                
        # mkdir - Directory creation
        if command.startswith("mkdir "):
            parts = command.split(" ", 1)
            if len(parts) < 2:
                return {"error": "Directory path required", "exit_code": 1}
                
            dir_arg = parts[1].strip()
            
            # Remove flags, keeping just the directory name(s)
            if dir_arg.startswith("-"):
                flag_end = dir_arg.find(" ")
                if flag_end == -1:
                    return {"error": "Directory path required", "exit_code": 1}
                dir_arg = dir_arg[flag_end+1:].strip()
                
            # Process multiple directories (space-separated)
            dir_paths = dir_arg.split()
            results = []
            
            for dir_path in dir_paths:
                # Process any quotes or special characters in the path
                dir_path = dir_path.strip('"\'')
                
                # Handle ~ in paths
                if dir_path.startswith("~"):
                    dir_path = dir_path.replace("~", home_dir, 1)
                elif not dir_path.startswith("/"):
                    # Relative path
                    dir_path = os.path.join(home_dir, dir_path)
                
                # Verify the path is within the home directory for security
                dir_path = os.path.normpath(dir_path)
                if not dir_path.startswith(home_dir):
                    results.append(f"mkdir: {dir_path}: Access denied. Path outside of user directory.")
                    continue
                    
                try:
                    # Create directory (and parent directories if -p flag was used)
                    # We'll always create parent directories for better user experience
                    os.makedirs(dir_path, exist_ok=True)
                    # No output on success (Unix behavior)
                except Exception as e:
                    logger.error(f"Error creating directory: {str(e)}")
                    results.append(f"mkdir: {dir_path}: {str(e)}")
            
            if results:
                # Only report errors
                result_text = "\n".join(results)
                if callback:
                    callback(result_text + "\n")
                    callback("\n", exit_code=1)
                    return {"message": "Directory creation errors", "exit_code": 1}
                return {"error": result_text, "exit_code": 1}
            else:
                # Success - no output for mkdir (Unix behavior)
                if callback:
                    callback("\n", exit_code=0)
                    return {"message": "Directory created", "exit_code": 0}
                return {"output": "", "exit_code": 0}
                
        # rm - File/directory removal
        if command.startswith("rm "):
            parts = command.split(" ", 1)
            if len(parts) < 2:
                return {"error": "Path required", "exit_code": 1}
                
            args = parts[1].strip()
            
            # Parse flags
            recursive = False
            force = False
            verbose = False
            
            if args.startswith("-"):
                flag_end = 0
                while flag_end < len(args) and args[flag_end] != " ":
                    flag_end += 1
                
                flags = args[:flag_end]
                if "r" in flags or "R" in flags:
                    recursive = True
                if "f" in flags:
                    force = True
                if "v" in flags:
                    verbose = True
                    
                args = args[flag_end:].strip()
            
            # Process multiple paths (space-separated)
            paths = args.split()
            results = []
            success = True
            
            for path in paths:
                # Process any quotes or special characters in the path
                path = path.strip('"\'')
                
                # Handle ~ in paths
                if path.startswith("~"):
                    path = path.replace("~", home_dir, 1)
                elif not path.startswith("/"):
                    # Relative path
                    path = os.path.join(home_dir, path)
                
                # Verify the path is within the home directory for security
                path = os.path.normpath(path)
                if not path.startswith(home_dir):
                    results.append(f"rm: {path}: Access denied. Path outside of user directory.")
                    success = False
                    continue
                    
                try:
                    if not os.path.exists(path):
                        if not force:
                            results.append(f"rm: {path}: No such file or directory")
                            success = False
                        continue
                        
                    if os.path.isdir(path):
                        if recursive:
                            shutil.rmtree(path)
                            if verbose:
                                results.append(f"removed directory '{path}'")
                        else:
                            results.append(f"rm: {path}: is a directory")
                            success = False
                    else:
                        os.remove(path)
                        if verbose:
                            results.append(f"removed '{path}'")
                except Exception as e:
                    logger.error(f"Error removing path: {str(e)}")
                    results.append(f"rm: {path}: {str(e)}")
                    success = False
            
            if results:
                result_text = "\n".join(results)
                if callback:
                    callback(result_text + "\n")
                    callback("\n", exit_code=0 if success else 1)
                    return {"message": "Removal completed", "exit_code": 0 if success else 1}
                return {"output" if success else "error": result_text, "exit_code": 0 if success else 1}
            else:
                # No output on success without verbose flag (Unix behavior)
                if callback:
                    callback("\n", exit_code=0)
                    return {"message": "Removal completed", "exit_code": 0}
                return {"output": "", "exit_code": 0}
                
        # touch - Create empty files
        if command.startswith("touch "):
            parts = command.split(" ", 1)
            if len(parts) < 2:
                return {"error": "File path required", "exit_code": 1}
                
            file_args = parts[1].strip()
            
            # Process multiple files (space-separated)
            file_paths = file_args.split()
            results = []
            success = True
            
            for file_path in file_paths:
                # Process any quotes or special characters in the path
                file_path = file_path.strip('"\'')
                
                # Handle ~ in paths
                if file_path.startswith("~"):
                    file_path = file_path.replace("~", home_dir, 1)
                elif not file_path.startswith("/"):
                    # Relative path
                    file_path = os.path.join(home_dir, file_path)
                
                # Verify the path is within the home directory for security
                file_path = os.path.normpath(file_path)
                if not file_path.startswith(home_dir):
                    results.append(f"touch: {file_path}: Access denied. Path outside of user directory.")
                    success = False
                    continue
                    
                try:
                    # Create parent directories if they don't exist
                    os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
                    
                    # Update the file access and modification times, create if it doesn't exist
                    with open(file_path, 'a'):
                        os.utime(file_path, None)
                except Exception as e:
                    logger.error(f"Error touching file: {str(e)}")
                    results.append(f"touch: {file_path}: {str(e)}")
                    success = False
            
            if results:
                result_text = "\n".join(results)
                if callback:
                    callback(result_text + "\n")
                    callback("\n", exit_code=0 if success else 1)
                    return {"message": "Touch completed", "exit_code": 0 if success else 1}
                return {"output" if success else "error": result_text, "exit_code": 0 if success else 1}
            else:
                # No output on success (Unix behavior)
                if callback:
                    callback("\n", exit_code=0)
                    return {"message": "Touch completed", "exit_code": 0}
                return {"output": "", "exit_code": 0}
        
        # If not a built-in file operation, return None to execute as a normal shell command
        return None
