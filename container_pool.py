import docker
import hashlib
import json
import os
import time
import threading
import uuid
import logging

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("container_pool.log"),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger("container_pool")

class ContainerPool:
    """
    Manages a pool of containers for multi-user terminal sessions
    Each container can host multiple users with Linux user-level isolation
    
    Supports two modes:
    1. Single container - All users share one container (MULTI_CONTAINER_MODE=false)
    2. Multiple containers - Users are distributed across multiple containers (MULTI_CONTAINER_MODE=true)
    """
    
    def __init__(self, max_containers=10, users_per_container=20, 
                 image_name="terminal-multi-user:latest",
                 multi_container_mode=False):
        self.max_containers = max_containers
        self.users_per_container = users_per_container
        self.image_name = image_name
        self.multi_container_mode = multi_container_mode
        self.containers = []  # List of active container IDs
        self.user_map = {}    # Maps user_id to (container_id, linux_username)
        self.lock = threading.RLock()  # Lock for thread safety
        
        try:
            self.docker_client = docker.from_env()
            logger.info("Docker client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize Docker client: {str(e)}")
            raise
            
        # Load saved state if available
        self.load_state()
        
        # Verify containers on startup
        self._verify_containers()
        
        logger.info(f"Container pool initialized with {len(self.containers)} containers")
    
    def load_state(self):
        """Load container pool state from disk"""
        try:
            state_file = 'container_state.json'
            if os.path.exists(state_file):
                with self.lock:
                    with open(state_file, 'r') as f:
                        state = json.load(f)
                        self.containers = state.get('containers', [])
                        self.user_map = state.get('user_map', {})
                logger.info(f"Loaded {len(self.containers)} containers and {len(self.user_map)} user mappings")
        except Exception as e:
            logger.error(f"Error loading container state: {str(e)}")
    
    def save_state(self):
        """Save container pool state to disk"""
        try:
            state_file = 'container_state.json'
            with self.lock:
                state = {
                    'containers': self.containers,
                    'user_map': self.user_map
                }
                with open(state_file, 'w') as f:
                    json.dump(state, f)
            logger.debug("Container state saved")
        except Exception as e:
            logger.error(f"Error saving container state: {str(e)}")
    
    def _verify_containers(self):
        """Verify that all containers in our list exist and are running"""
        with self.lock:
            verified_containers = []
            for container_id in self.containers:
                try:
                    container = self.docker_client.containers.get(container_id)
                    # Check if container is running
                    if container.status != "running":
                        logger.info(f"Container {container_id} is not running. Status: {container.status}")
                        # Try to restart it
                        try:
                            container.restart()
                            logger.info(f"Container {container_id} restarted")
                            verified_containers.append(container_id)
                        except Exception as e:
                            logger.error(f"Failed to restart container {container_id}: {str(e)}")
                    else:
                        verified_containers.append(container_id)
                except docker.errors.NotFound:
                    logger.warning(f"Container {container_id} no longer exists, removing from pool")
                except Exception as e:
                    logger.error(f"Error verifying container {container_id}: {str(e)}")
            
            # Update the container list
            self.containers = verified_containers
            self.save_state()
    
    def get_container_for_user(self, user_id):
        """Get or assign a container for a user"""
        with self.lock:
            # If user already has a container assigned, use that
            if user_id in self.user_map:
                container_id, username = self.user_map[user_id]
                # Verify container still exists
                try:
                    self.docker_client.containers.get(container_id)
                    logger.debug(f"User {user_id} already assigned to container {container_id}")
                    return container_id, username
                except Exception as e:
                    logger.warning(f"Container {container_id} for user {user_id} no longer exists: {str(e)}")
                    # Container no longer exists, remove mapping
                    del self.user_map[user_id]
            
            # Find container with space or create a new one
            container_id = self._find_available_container()
            
            # Generate consistent username for this user (use hash for uniqueness)
            # This ensures the same user always gets the same Linux username
            username = f"user{int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 10000}"
            
            # Create user in container
            self._create_user_in_container(container_id, username, user_id)
            
            # Store mapping
            self.user_map[user_id] = (container_id, username)
            self.save_state()
            
            logger.info(f"User {user_id} assigned to container {container_id} as {username}")
            return container_id, username
    
    def _find_available_container(self):
        """
        Find an appropriate container based on the mode:
        - In multi-container mode: Find container with fewest users for optimal distribution
        - In single-container mode: Use the one container for all users
        """
        with self.lock:
            # Initialize counts for all containers
            container_counts = {}
            for container_id in self.containers:
                container_counts[container_id] = 0
            
            # Count current users in each container
            for container_id, _ in self.user_map.values():
                if container_id in container_counts:
                    container_counts[container_id] += 1
            
            # First, verify all containers are running
            active_containers = []
            for container_id in list(container_counts.keys()):
                try:
                    container = self.docker_client.containers.get(container_id)
                    if container.status != "running":
                        container.restart()
                        logger.info(f"Restarted container {container_id}")
                    active_containers.append(container_id)
                except Exception as e:
                    logger.error(f"Error checking container {container_id}: {str(e)}")
                    # Container doesn't exist or is invalid, remove it from our list
                    if container_id in self.containers:
                        self.containers.remove(container_id)
                    # Remove from counts too
                    if container_id in container_counts:
                        del container_counts[container_id]
            
            # Single container mode - all users go to one container
            if not self.multi_container_mode:
                # If we have any active container, use the first one
                if active_containers:
                    container_id = active_containers[0]
                    logger.info(f"Single container mode: Using container {container_id} for all users")
                    return container_id
                else:
                    # No containers exist, create one
                    logger.info("Single container mode: Creating container for all users")
                    return self._create_new_container()
            
            # Multi-container mode - distribute users across containers
            else:
                # If we have containers with space, use the one with fewest users
                available_containers = [cid for cid in active_containers 
                                      if container_counts.get(cid, 0) < self.users_per_container]
                
                if available_containers:
                    # Find container with fewest users for even distribution
                    container_id = min(available_containers, 
                                      key=lambda cid: container_counts.get(cid, 0))
                    logger.info(f"Multi-container mode: Assigning to container {container_id} with {container_counts.get(container_id, 0)} users")
                    return container_id
                
                # Need to create a new container if we haven't reached max
                if len(self.containers) < self.max_containers:
                    logger.info(f"Multi-container mode: Creating new container (current count: {len(self.containers)})")
                    return self._create_new_container()
                
                # If all containers are at capacity, use the one with the fewest users
                if active_containers:
                    container_id = min(active_containers, key=lambda cid: container_counts.get(cid, 9999))
                    logger.warning(f"Multi-container mode: All containers at capacity. Using {container_id}")
                    return container_id
            
            # Fallback: create a new container anyway (will exceed max)
            logger.warning("No active containers available, creating a new one")
            return self._create_new_container()
    
    def _create_new_container(self):
        """Create a new container and return its ID"""
        try:
            container_name = f"terminal-pool-{int(time.time())}"
            logger.info(f"Creating new container: {container_name}")
            
            container = self.docker_client.containers.run(
                self.image_name,
                detach=True,
                name=container_name,
                volumes={
                    "terminal-workspace": {"bind": "/workspace", "mode": "rw"}
                },
                mem_limit="512m",
                cpu_quota=50000,  # 50% of CPU
                network_mode="bridge",
                restart_policy={"Name": "unless-stopped"}
            )
            
            container_id = container.id
            
            with self.lock:
                self.containers.append(container_id)
                self.save_state()
                
            logger.info(f"Created new container {container_id}")
            return container_id
            
        except Exception as e:
            logger.error(f"Error creating container: {str(e)}")
            
            # Fallback to first container if we have any
            with self.lock:
                if self.containers:
                    fallback_id = self.containers[0]
                    logger.warning(f"Using fallback container {fallback_id}")
                    return fallback_id
            
            # If we have no containers, this is a critical error
            logger.critical("No containers available and failed to create new one")
            raise
    
    def _create_user_in_container(self, container_id, username, user_id):
        """Create a Linux user in the container"""
        try:
            container = self.docker_client.containers.get(container_id)
            
            # Generate a deterministic user ID from user_id (between 2000-9999)
            # This ensures the same user always gets the same UID
            userid = 2000 + (int(hashlib.md5(user_id.encode()).hexdigest(), 16) % 8000)
            
            # Run user creation script
            logger.info(f"Creating user {username} (UID: {userid}) in container {container_id}")
            result = container.exec_run(
                f"/usr/local/bin/create-user.sh {username} {userid}",
                user="root"
            )
            
            exit_code = result.exit_code
            output = result.output.decode('utf-8', errors='replace')
            
            if exit_code != 0:
                logger.error(f"Failed to create user {username}: {output}")
                return False
            
            logger.info(f"User {username} created successfully in container {container_id}")
            return True
            
        except Exception as e:
            logger.error(f"Error creating user in container: {str(e)}")
            return False
    
    def execute_command(self, user_id, command):
        """Execute command for a user in their assigned container"""
        try:
            # Get container and username for this user
            container_id, username = self.get_container_for_user(user_id)
            container = self.docker_client.containers.get(container_id)
            
            logger.debug(f"Executing command for user {username} in container {container_id}: {command}")
            
            # Execute command as the user
            result = container.exec_run(
                f"su - {username} -c '{command}'",
                user="root",
                demux=True
            )
            
            exit_code = result.exit_code
            
            # Process stdout/stderr
            stdout, stderr = result.output
            stdout = stdout.decode('utf-8', errors='replace') if stdout else ''
            stderr = stderr.decode('utf-8', errors='replace') if stderr else ''
            
            logger.debug(f"Command completed with exit code {exit_code}")
            
            # Combine stdout and stderr
            output = stdout
            if stderr:
                if output:
                    output += "\n" + stderr
                else:
                    output = stderr
            
            return {
                "output": output,
                "exit_code": exit_code
            }
            
        except Exception as e:
            logger.error(f"Error executing command for user {user_id}: {str(e)}")
            return {
                "error": f"Failed to execute command: {str(e)}",
                "exit_code": 1
            }
    
    def execute_command_stream(self, user_id, command, callback):
        """
        Execute command with streaming output
        
        Args:
            user_id: User identifier
            command: Command to execute
            callback: Function to call with streaming output
        """
        try:
            # Get container and username for this user
            container_id, username = self.get_container_for_user(user_id)
            container = self.docker_client.containers.get(container_id)
            
            logger.debug(f"Executing streaming command for user {username}: {command}")
            
            # Create exec instance
            exec_instance = container.client.api.exec_create(
                container.id,
                f"su - {username} -c '{command}'",
                user="root",
                tty=True
            )
            
            # Start exec instance with stream=True
            exec_output = container.client.api.exec_start(
                exec_instance['Id'],
                stream=True
            )
            
            # Stream output to callback
            for chunk in exec_output:
                if chunk:
                    text = chunk.decode('utf-8', errors='replace')
                    callback(text)
            
            # Get exit code
            inspect_result = container.client.api.exec_inspect(exec_instance['Id'])
            exit_code = inspect_result.get('ExitCode', 0)
            
            logger.debug(f"Streaming command completed with exit code {exit_code}")
            
            return {
                "exit_code": exit_code
            }
            
        except Exception as e:
            logger.error(f"Error executing streaming command: {str(e)}")
            callback(f"Error: {str(e)}")
            return {
                "error": f"Failed to execute command: {str(e)}",
                "exit_code": 1
            }
    
    def cleanup(self):
        """Clean up inactive users and containers"""
        with self.lock:
            # Implement cleanup logic as needed
            # For example, remove users that haven't been active for a while
            # or stop containers that have no users
            pass
    
    def stop_all_containers(self):
        """Stop all containers managed by this pool"""
        with self.lock:
            for container_id in self.containers:
                try:
                    container = self.docker_client.containers.get(container_id)
                    container.stop(timeout=10)
                    logger.info(f"Stopped container {container_id}")
                except Exception as e:
                    logger.error(f"Error stopping container {container_id}: {str(e)}")
