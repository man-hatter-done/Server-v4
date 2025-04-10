# User Isolation Modes

This server supports different methods of isolating users from each other:

## 1. Directory-Based Isolation (Default)

**How it works**: 
- Each user gets their own directory in the filesystem
- All users share the same server process
- File permissions separate user data

**Benefits**:
- Simpler setup
- Works on all hosting providers
- Lower resource usage

**Downsides**:
- Less secure isolation
- Users share process resources

**When to use**:
- For small deployments
- When running on free tier hosting
- For trusted users

**Configuration**:
```
USE_CONTAINERS=false
```

## 2. Single Container Isolation

**How it works**:
- All users share one container
- Each user gets their own Linux user account in that container 
- Linux permissions and user isolation separate users

**Benefits**:
- Better isolation than directory-based
- Efficient resource usage (just one container)
- True user-level isolation

**Downsides**:
- Requires Docker support
- All users still share one container

**When to use**:
- For small to medium deployments
- When Docker is available
- For better isolation without much overhead

**Configuration**:
```
USE_CONTAINERS=true
MULTI_CONTAINER_MODE=false
```

## 3. Multi-Container Isolation

**How it works**:
- Users are distributed across multiple containers
- Each user gets their own Linux user account
- Container load-balancing for even distribution

**Benefits**:
- Best isolation between users
- Load distribution across containers
- Higher user capacity

**Downsides**:
- Highest resource usage
- More complex setup
- Requires Docker support

**When to use**:
- For larger deployments
- When maximum isolation is needed
- When you have adequate resources

**Configuration**:
```
USE_CONTAINERS=true
MULTI_CONTAINER_MODE=true
MAX_CONTAINERS=10  # Adjust as needed
```

## Switching Between Modes

You can change the isolation mode using environment variables:

1. **In render.yaml**:
   ```yaml
   envVars:
     - key: USE_CONTAINERS
       value: true
     - key: MULTI_CONTAINER_MODE
       value: false
   ```

2. **In docker-compose-multi-user.yml**:
   ```yaml
   environment:
     - USE_CONTAINERS=true
     - MULTI_CONTAINER_MODE=false
   ```

3. **With environment variables**:
   ```bash
   export USE_CONTAINERS=true
   export MULTI_CONTAINER_MODE=false
   ```

## Recommendation

Start with directory-based isolation. If you need better isolation and have Docker support, upgrade to single-container mode. Only use multi-container mode for large deployments with many users.
