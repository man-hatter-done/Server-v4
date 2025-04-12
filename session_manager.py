"""
Session Manager for Terminal Server

Handles session creation, tracking, and cleanup with improved
isolation and persistence.
"""

import os
import threading
import time
import uuid
import json
import shutil
import logging
from datetime import datetime

logger = logging.getLogger("session_manager")

class SessionManager:
    """
    Manages terminal sessions, providing isolation and persistence.
    
    This class handles:
    - Creating and validating sessions
    - Managing session file systems
    - Session cleanup and expiration
    - User mapping to sessions
    """
    
    def __init__(self, session_timeout=3600, user_data_dir="user_data"):
        """
        Initialize the session manager.
        
        Args:
            session_timeout: Session timeout in seconds (default: 1 hour)
            user_data_dir: Base directory for user session data
        """
        self.sessions = {}
        self.user_sessions = {}  # Map user_id to session_id
        self.session_lock = threading.Lock()
        self.session_timeout = session_timeout
        self.user_data_dir = user_data_dir
        
        # Create user data directory if it doesn't exist
        os.makedirs(user_data_dir, exist_ok=True)
        
        # Start cleanup thread
        self.cleanup_thread = threading.Thread(target=self._cleanup_loop, daemon=True)
        self.cleanup_thread.start()
        
        # Load any saved sessions
        self._load_sessions()
        
        logger.info(f"Session manager initialized with timeout: {session_timeout}s")
    
    def create_session(self, user_id, client_ip=None):
        """
        Create a new session for a user.
        
        Args:
            user_id: Unique identifier for the user
            client_ip: IP address of the client
            
        Returns:
            Dict containing session information
        """
        session_id = str(uuid.uuid4())
        home_dir = os.path.join(self.user_data_dir, session_id)
        
        # Set up the user environment with necessary files
        try:
            # Create the directory if it doesn't exist
            os.makedirs(home_dir, exist_ok=True)
            
            # Set up environment files (this will be done when needed)
            # We'll delay this until the first command to improve session creation speed
            
            with self.session_lock:
                self.sessions[session_id] = {
                    'user_id': user_id,
                    'client_ip': client_ip,
                    'created': time.time(),
                    'last_accessed': time.time(),
                    'home_dir': home_dir
                }
                
                # Map user_id to this session
                self.user_sessions[user_id] = session_id
                
                # Save sessions to disk
                self._save_sessions()
            
            logger.info(f"Created session {session_id} for user {user_id}")
            
            return {
                'sessionId': session_id,
                'created': datetime.fromtimestamp(time.time()).isoformat(),
                'expiresIn': self.session_timeout,
                'workingDirectory': '~'
            }
        except Exception as e:
            logger.error(f"Error creating session: {str(e)}")
            # Clean up any partially created directory
            if os.path.exists(home_dir):
                try:
                    shutil.rmtree(home_dir)
                except Exception as cleanup_error:
                    logger.error(f"Error cleaning up session directory: {str(cleanup_error)}")
            
            return {
                'error': f"Failed to create session: {str(e)}"
            }
    
    def get_session(self, session_id):
        """
        Get a session by ID and update its last access time.
        
        Args:
            session_id: The session ID to retrieve
            
        Returns:
            Dict containing session data or None if invalid/expired
        """
        with self.session_lock:
            if session_id not in self.sessions:
                return None
            
            # Check if session has expired
            current_time = time.time()
            session = self.sessions[session_id]
            if current_time - session['last_accessed'] > self.session_timeout:
                # Session expired
                self._remove_session(session_id)
                return None
            
            # Update last accessed time
            session['last_accessed'] = current_time
            
            return session.copy()  # Return a copy to prevent external modification
    
    def end_session(self, session_id, preserve_data=False):
        """
        End a session and optionally clean up its data.
        
        Args:
            session_id: The session ID to end
            preserve_data: Whether to preserve the session data (default: False)
            
        Returns:
            Boolean indicating success
        """
        with self.session_lock:
            if session_id not in self.sessions:
                return False
            
            # Get the session data
            session = self.sessions[session_id]
            user_id = session.get('user_id')
            home_dir = session.get('home_dir')
            
            # Remove session
            self._remove_session(session_id)
            
            # Remove user-session mapping
            if user_id and user_id in self.user_sessions:
                if self.user_sessions[user_id] == session_id:
                    del self.user_sessions[user_id]
            
            # Clean up data unless preservation is requested
            if not preserve_data and home_dir and os.path.exists(home_dir):
                try:
                    shutil.rmtree(home_dir)
                    logger.info(f"Removed session directory: {home_dir}")
                except Exception as e:
                    logger.error(f"Error removing session directory: {str(e)}")
            
            # Save sessions to disk
            self._save_sessions()
            
            logger.info(f"Ended session {session_id}")
            
            return True
    
    def update_session_access(self, session_id):
        """Update the last accessed time for a session"""
        with self.session_lock:
            if session_id in self.sessions:
                self.sessions[session_id]['last_accessed'] = time.time()
                return True
        return False
    
    def get_all_sessions(self):
        """Get all active sessions (for admin purposes)"""
        with self.session_lock:
            return {sid: session.copy() for sid, session in self.sessions.items()}
    
    def _remove_session(self, session_id):
        """Internal method to remove a session"""
        if session_id in self.sessions:
            # Remove user mapping if exists
            user_id = self.sessions[session_id].get('user_id')
            if user_id and user_id in self.user_sessions and self.user_sessions[user_id] == session_id:
                del self.user_sessions[user_id]
            
            # Remove session
            del self.sessions[session_id]
            
            logger.info(f"Removed session {session_id}")
            return True
        return False
    
    def _cleanup_loop(self):
        """Background thread to clean up expired sessions"""
        while True:
            try:
                self._cleanup_expired_sessions()
            except Exception as e:
                logger.error(f"Error in session cleanup: {str(e)}")
            
            # Sleep for a while before next cleanup
            time.sleep(60)  # Check every minute
    
    def _cleanup_expired_sessions(self):
        """Clean up expired sessions"""
        current_time = time.time()
        expired_sessions = []
        
        with self.session_lock:
            for session_id, session in self.sessions.items():
                # Check if session has expired
                if current_time - session['last_accessed'] > self.session_timeout:
                    expired_sessions.append(session_id)
            
            # Remove expired sessions
            for session_id in expired_sessions:
                home_dir = self.sessions[session_id].get('home_dir')
                self._remove_session(session_id)
                
                # Clean up session directory
                if home_dir and os.path.exists(home_dir):
                    try:
                        shutil.rmtree(home_dir)
                        logger.info(f"Cleaned up expired session directory: {home_dir}")
                    except Exception as e:
                        logger.error(f"Error removing expired session directory: {str(e)}")
        
        if expired_sessions:
            logger.info(f"Cleaned up {len(expired_sessions)} expired sessions")
            self._save_sessions()
    
    def _save_sessions(self):
        """Save active sessions to disk for persistence"""
        try:
            sessions_file = os.path.join(self.user_data_dir, 'sessions.json')
            
            # Only save the minimal required data, not the complete session objects
            serializable_sessions = {}
            for session_id, session in self.sessions.items():
                serializable_sessions[session_id] = {
                    'user_id': session.get('user_id'),
                    'client_ip': session.get('client_ip'),
                    'created': session.get('created'),
                    'last_accessed': session.get('last_accessed'),
                    'home_dir': session.get('home_dir')
                }
            
            with open(sessions_file, 'w') as f:
                json.dump({
                    'sessions': serializable_sessions,
                    'user_sessions': self.user_sessions,
                    'timestamp': time.time()
                }, f)
                
            logger.debug(f"Saved {len(self.sessions)} sessions to disk")
        except Exception as e:
            logger.error(f"Error saving sessions to disk: {str(e)}")
    
    def _load_sessions(self):
        """Load sessions from disk"""
        try:
            sessions_file = os.path.join(self.user_data_dir, 'sessions.json')
            
            if not os.path.exists(sessions_file):
                logger.info("No saved sessions found")
                return
            
            with open(sessions_file, 'r') as f:
                data = json.load(f)
            
            with self.session_lock:
                self.sessions = data.get('sessions', {})
                self.user_sessions = data.get('user_sessions', {})
            
            # Verify session directories exist
            valid_sessions = {}
            for session_id, session in self.sessions.items():
                home_dir = session.get('home_dir')
                if home_dir and os.path.exists(home_dir):
                    valid_sessions[session_id] = session
                else:
                    logger.warning(f"Session {session_id} directory not found, skipping")
            
            # Update sessions with valid ones only
            with self.session_lock:
                self.sessions = valid_sessions
            
            logger.info(f"Loaded {len(self.sessions)} valid sessions from disk")
        except Exception as e:
            logger.error(f"Error loading sessions from disk: {str(e)}")
            # Start with empty sessions if load fails
            with self.session_lock:
                self.sessions = {}
                self.user_sessions = {}
