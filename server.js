const express = require('express');
const { exec, spawn } = require('child_process');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');
const { v4: uuidv4 } = require('uuid');
const rateLimit = require('express-rate-limit');
const Docker = require('dockerode');
const morgan = require('morgan');
const helmet = require('helmet');

const app = express();
const port = process.env.PORT || 3000;
const docker = new Docker(); // Connect to Docker socket

// Security configuration
const API_KEY = process.env.API_KEY || 'change-this-in-production';
const SESSION_TIMEOUT = parseInt(process.env.SESSION_TIMEOUT || '3600000'); // 1 hour by default
const MAX_CONTAINERS = parseInt(process.env.MAX_CONTAINERS || '100');
const CONTAINER_MEMORY = process.env.CONTAINER_MEMORY || '256m';
const CONTAINER_CPU = process.env.CONTAINER_CPU || '0.5';
const USER_CONTAINER_IMAGE = process.env.USER_CONTAINER_IMAGE || 'terminal-user-image:latest';

// Session storage
const sessions = {};
let containerCount = 0;

// Create logs directory
if (!fs.existsSync('logs')) {
  fs.mkdirSync('logs');
}

// Setup secure HTTP headers
app.use(helmet());

// Setup request logging
const accessLogStream = fs.createWriteStream(path.join(__dirname, 'logs', 'access.log'), { flags: 'a' });
app.use(morgan('combined', { stream: accessLogStream }));

// Add security logging
const securityLogger = (req, res, next) => {
  const logEntry = {
    timestamp: new Date().toISOString(),
    ip: req.ip,
    method: req.method,
    path: req.path,
    headers: req.headers,
    body: req.body
  };
  
  fs.appendFileSync(
    path.join(__dirname, 'logs', 'security.log'), 
    JSON.stringify(logEntry) + '\n'
  );
  
  next();
};

app.use(securityLogger);

// Rate limiting
const limiter = rateLimit({
  windowMs: 15 * 60 * 1000, // 15 minutes
  max: 100, // limit each IP to 100 requests per windowMs
  message: { error: 'Too many requests, please try again later' }
});

app.use(limiter);
app.use(express.json());

// Authentication middleware
const authenticate = (req, res, next) => {
  const providedApiKey = req.headers['x-api-key'];
  
  if (!providedApiKey) {
    return res.status(401).json({ error: 'API key is required' });
  }
  
  // Constant-time comparison to prevent timing attacks
  try {
    if (!crypto.timingSafeEqual(
      Buffer.from(providedApiKey, 'utf8'), 
      Buffer.from(API_KEY, 'utf8')
    )) {
      return res.status(401).json({ error: 'Invalid API key' });
    }
  } catch (error) {
    return res.status(401).json({ error: 'Invalid API key format' });
  }
  
  next();
};

// Session validation middleware
const validateSession = (req, res, next) => {
  const sessionId = req.headers['x-session-id'];
  
  if (!sessionId || !sessions[sessionId]) {
    return res.status(401).json({ error: 'Invalid or expired session' });
  }
  
  const session = sessions[sessionId];
  
  // Check if session has expired
  if (Date.now() - session.lastAccessed > SESSION_TIMEOUT) {
    // Cleanup container
    cleanupSession(sessionId);
    return res.status(401).json({ error: 'Session expired' });
  }
  
  // Update last accessed time
  session.lastAccessed = Date.now();
  req.session = session;
  
  next();
};

// Session cleanup function
const cleanupSession = async (sessionId) => {
  const session = sessions[sessionId];
  if (!session) return;
  
  try {
    // Remove Docker container
    const container = docker.getContainer(session.containerId);
    await container.stop();
    await container.remove();
    containerCount--;
    
    console.log(`Cleaned up container for session ${sessionId}`);
    
    // Remove session
    delete sessions[sessionId];
  } catch (error) {
    console.error(`Error cleaning up session ${sessionId}:`, error);
  }
};

// Periodic cleanup of expired sessions
setInterval(() => {
  const now = Date.now();
  
  Object.keys(sessions).forEach(sessionId => {
    const session = sessions[sessionId];
    if (now - session.lastAccessed > SESSION_TIMEOUT) {
      cleanupSession(sessionId);
    }
  });
}, 60000); // Check every minute

// Create new session (and Docker container)
app.post('/create-session', authenticate, async (req, res) => {
  try {
    // Check container limits
    if (containerCount >= MAX_CONTAINERS) {
      return res.status(503).json({ 
        error: 'Maximum number of active sessions reached. Please try again later.' 
      });
    }
    
    // Generate unique IDs
    const sessionId = uuidv4();
    const userId = req.body.userId || uuidv4();
    const clientIp = req.ip || '0.0.0.0';
    
    // Create Docker container
    const container = await docker.createContainer({
      Image: USER_CONTAINER_IMAGE,
      Cmd: ['/bin/bash'],
      Tty: true,
      OpenStdin: true,
      StdinOnce: false,
      AttachStdin: true,
      AttachStdout: true,
      AttachStderr: true,
      HostConfig: {
        Memory: CONTAINER_MEMORY,
        CpuShares: Math.floor(parseFloat(CONTAINER_CPU) * 1024),
        NetworkMode: 'bridge',
        AutoRemove: true,
        SecurityOpt: ['no-new-privileges'],
        CapDrop: ['ALL'], // Drop all capabilities for security
        ReadonlyRootfs: false, // Allow package installation
      },
      Labels: {
        'app': 'terminal-server',
        'userId': userId,
        'sessionId': sessionId,
        'clientIp': clientIp
      }
    });
    
    await container.start();
    containerCount++;
    
    // Store session information
    sessions[sessionId] = {
      userId,
      clientIp,
      containerId: container.id,
      created: Date.now(),
      lastAccessed: Date.now()
    };
    
    console.log(`Created new container for user ${userId} from IP ${clientIp}`);
    
    // Return session information to client
    res.json({
      sessionId,
      userId,
      message: 'Session created successfully',
      expiresIn: SESSION_TIMEOUT,
    });
    
  } catch (error) {
    console.error('Error creating session:', error);
    res.status(500).json({ error: 'Failed to create session: ' + error.message });
  }
});

// Execute command in user's container
app.post('/execute-command', authenticate, validateSession, async (req, res) => {
  const { command } = req.body;
  const session = req.session;
  
  if (!command) {
    return res.status(400).json({ error: 'Command is required' });
  }
  
  try {
    // Get container
    const container = docker.getContainer(session.containerId);
    
    // Log command for audit
    const logEntry = {
      timestamp: new Date().toISOString(),
      userId: session.userId,
      sessionId: req.headers['x-session-id'],
      clientIp: session.clientIp,
      command: command
    };
    
    fs.appendFileSync(
      path.join(__dirname, 'logs', 'commands.log'), 
      JSON.stringify(logEntry) + '\n'
    );
    
    // Execute command in container
    const exec = await container.exec({
      Cmd: ['/bin/bash', '-c', command],
      AttachStdout: true,
      AttachStderr: true
    });
    
    const stream = await exec.start();
    
    // Collect output
    let output = '';
    
    // Handle the stream data
    stream.on('data', (chunk) => {
      output += chunk.toString('utf8');
    });
    
    // Handle stream errors
    stream.on('error', (err) => {
      res.status(500).json({ error: err.message });
    });
    
    // Wait for command to complete
    stream.on('end', async () => {
      try {
        // Get exit code
        const inspect = await exec.inspect();
        const exitCode = inspect.ExitCode;
        
        if (exitCode !== 0) {
          return res.status(400).json({ 
            error: output || 'Command failed', 
            exitCode 
          });
        }
        
        res.json({ output });
      } catch (inspectError) {
        res.status(500).json({ error: 'Failed to get command status' });
      }
    });
    
  } catch (error) {
    console.error('Error executing command:', error);
    res.status(500).json({ error: 'Failed to execute command: ' + error.message });
  }
});

// Fallback for compatibility with original API
app.post('/execute-command-legacy', authenticate, async (req, res) => {
  const { command } = req.body;
  
  if (!command) {
    return res.status(400).json({ error: 'Command is required' });
  }
  
  // Extract device ID from request if available
  const deviceId = req.headers['x-device-id'] || req.ip || uuidv4();
  
  // Find existing session for this device or create new one
  let sessionId = null;
  for (const [id, session] of Object.entries(sessions)) {
    if (session.userId === deviceId) {
      sessionId = id;
      break;
    }
  }
  
  // If no session exists, create one
  if (!sessionId) {
    try {
      // Call create-session endpoint
      req.body.userId = deviceId;
      
      // Check container limits
      if (containerCount >= MAX_CONTAINERS) {
        return res.status(503).json({ 
          error: 'Maximum number of active sessions reached. Please try again later.' 
        });
      }
      
      // Generate unique IDs
      sessionId = uuidv4();
      const userId = deviceId;
      const clientIp = req.ip || '0.0.0.0';
      
      // Create Docker container
      const container = await docker.createContainer({
        Image: USER_CONTAINER_IMAGE,
        Cmd: ['/bin/bash'],
        Tty: true,
        OpenStdin: true,
        StdinOnce: false,
        AttachStdin: true,
        AttachStdout: true,
        AttachStderr: true,
        HostConfig: {
          Memory: CONTAINER_MEMORY,
          CpuShares: Math.floor(parseFloat(CONTAINER_CPU) * 1024),
          NetworkMode: 'bridge',
          AutoRemove: true,
          SecurityOpt: ['no-new-privileges'],
          CapDrop: ['ALL'],
          ReadonlyRootfs: false,
        },
        Labels: {
          'app': 'terminal-server',
          'userId': userId,
          'sessionId': sessionId,
          'clientIp': clientIp
        }
      });
      
      await container.start();
      containerCount++;
      
      // Store session information
      sessions[sessionId] = {
        userId,
        clientIp,
        containerId: container.id,
        created: Date.now(),
        lastAccessed: Date.now()
      };
      
      console.log(`Created new container for legacy device ${userId} from IP ${clientIp}`);
    } catch (error) {
      console.error('Error creating legacy session:', error);
      return res.status(500).json({ error: 'Failed to create session' });
    }
  }
  
  // Now execute the command using the session
  try {
    const session = sessions[sessionId];
    session.lastAccessed = Date.now();
    
    // Get container
    const container = docker.getContainer(session.containerId);
    
    // Log command for audit
    const logEntry = {
      timestamp: new Date().toISOString(),
      userId: session.userId,
      sessionId: sessionId,
      clientIp: session.clientIp,
      command: command,
      isLegacy: true
    };
    
    fs.appendFileSync(
      path.join(__dirname, 'logs', 'commands.log'), 
      JSON.stringify(logEntry) + '\n'
    );
    
    // Execute command in container
    const exec = await container.exec({
      Cmd: ['/bin/bash', '-c', command],
      AttachStdout: true,
      AttachStderr: true
    });
    
    const stream = await exec.start();
    
    // Collect output
    let output = '';
    
    // Handle the stream data
    stream.on('data', (chunk) => {
      output += chunk.toString('utf8');
    });
    
    // Handle stream errors
    stream.on('error', (err) => {
      res.status(500).json({ error: err.message });
    });
    
    // Wait for command to complete
    stream.on('end', async () => {
      try {
        // Get exit code
        const inspect = await exec.inspect();
        const exitCode = inspect.ExitCode;
        
        if (exitCode !== 0) {
          return res.status(400).json({ 
            error: output || 'Command failed', 
            exitCode 
          });
        }
        
        res.json({ output });
      } catch (inspectError) {
        res.status(500).json({ error: 'Failed to get command status' });
      }
    });
  } catch (error) {
    console.error('Error executing legacy command:', error);
    res.status(500).json({ error: 'Failed to execute command: ' + error.message });
  }
});

// Get session information
app.get('/session', authenticate, validateSession, (req, res) => {
  const session = req.session;
  
  res.json({
    userId: session.userId,
    created: new Date(session.created).toISOString(),
    lastAccessed: new Date(session.lastAccessed).toISOString(),
    expiresIn: SESSION_TIMEOUT - (Date.now() - session.lastAccessed)
  });
});

// End session (cleanup container)
app.delete('/session', authenticate, validateSession, async (req, res) => {
  const sessionId = req.headers['x-session-id'];
  
  try {
    await cleanupSession(sessionId);
    res.json({ message: 'Session terminated successfully' });
  } catch (error) {
    console.error('Error terminating session:', error);
    res.status(500).json({ error: 'Failed to terminate session' });
  }
});

// Health check endpoint
app.get('/health', (req, res) => {
  res.json({ 
    status: 'ok',
    activeSessions: Object.keys(sessions).length,
    containerCount,
    maxContainers: MAX_CONTAINERS
  });
});

// Graceful shutdown
process.on('SIGTERM', async () => {
  console.log('Shutting down server...');
  
  // Cleanup all containers
  for (const sessionId of Object.keys(sessions)) {
    await cleanupSession(sessionId);
  }
  
  process.exit(0);
});

app.listen(port, () => {
  console.log(`Terminal server running on port ${port}`);
});