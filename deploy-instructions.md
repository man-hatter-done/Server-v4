# Terminal Server Deployment

This document provides instructions for deploying the terminal server to Render.com and other platforms.

## Building and Deploying to Render.com

### Step 1: Create a new Web Service

1. Sign up for an account on Render.com if you don't already have one
2. Create a new Web Service and connect your GitHub repository
3. Select "Docker" as the environment
4. Set the following environment variables:
   - `API_KEY`: A long, random string (generate with `openssl rand -hex 32`)
   - `SESSION_TIMEOUT`: `3600000` (1 hour in milliseconds)
   - `MAX_CONTAINERS`: `100` (or whatever limit you want)
   - `CONTAINER_MEMORY`: `256m` (memory limit per container)
   - `CONTAINER_CPU`: `0.5` (CPU limit per container)
   - `USER_CONTAINER_IMAGE`: Use a publicly accessible image like `yourusername/terminal-user-image:latest`

### Step 2: Build and Push the User Container Image

Since Render.com doesn't support Docker-in-Docker natively for web services, you'll need to build and push the user container image separately:

```bash
# Build the user container image
docker build -t yourusername/terminal-user-image:latest -f Dockerfile.user .

# Login to Docker Hub
docker login

# Push the image to Docker Hub
docker push yourusername/terminal-user-image:latest
```

Then update your `USER_CONTAINER_IMAGE` environment variable on Render to point to this image.

### Step 3: Set Up Persistent Disk

In your Render dashboard, add a persistent disk to your web service:
1. Go to your web service dashboard
2. Click "Add Disk"
3. Name it "terminal-logs"
4. Set the mount path to `/app/logs`
5. Choose a size (1GB should be sufficient for logs)

## Local Development

To run the server locally:

```bash
# Build the images
npm run build-images

# Start the server with Docker Compose
docker-compose up
```

## Integrating with Swift

Update your Swift code to use the new API with authentication and session management. See the Swift client code in the README.md file.

## Security Considerations

1. **API Key**: Keep your API key secure and don't commit it to source control
2. **Sessions**: User sessions expire after 1 hour by default, which can be adjusted
3. **Resource Limits**: Each container has memory and CPU limits to prevent abuse

## Monitoring

Check the health of your server using the `/health` endpoint, which provides information about active sessions and container count.
