FROM python:3.10-slim

# Set up environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV USE_CONTAINERS=true
ENV MAX_CONTAINERS=10
ENV USERS_PER_CONTAINER=20
ENV CONTAINER_IMAGE=terminal-multi-user:latest

# Install Docker CLI and dependencies for container management
RUN apt-get update && apt-get install -y \
    apt-transport-https \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    software-properties-common \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /usr/share/keyrings/docker-archive-keyring.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/docker-archive-keyring.gpg] https://download.docker.com/linux/debian $(lsb_release -cs) stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install -y docker-ce-cli \
    # Real Linux utilities and developer tools
    gcc \
    g++ \
    make \
    git \
    openssh-client \
    openssl \
    python3-dev \
    vim \
    nano \
    sudo \
    tar \
    gzip \
    wget \
    procps \
    htop \
    net-tools \
    iproute2 \
    iputils-ping \
    locales \
    zip \
    unzip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Setup locale for proper UTF-8 support
RUN locale-gen en_US.UTF-8
ENV LANG=C.UTF-8 \
    LANGUAGE=en_US:en \
    LC_ALL=C.UTF-8

# Set up work directory
WORKDIR /app

# Install Docker Python library and dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir docker gunicorn

# Set up container scripts
RUN mkdir -p container-scripts
COPY container-scripts/ ./container-scripts/
RUN chmod +x container-scripts/*

# Copy application files
COPY *.py ./
COPY static/ ./static/
COPY user_scripts/ ./user_scripts/
RUN chmod +x user_scripts/*

# Copy multi-user container Dockerfile
COPY Dockerfile.multi-user ./

# Make directories for data, logs, and ensure proper permissions
RUN mkdir -p logs user_data && \
    chmod -R 755 user_scripts/ && \
    chmod -R 777 user_data/ logs/

# Set up user
RUN useradd -m -s /bin/bash app-user && \
    chown -R app-user:app-user /app

# Give user sudo access but remove docker group (not needed on Render)
RUN echo "app-user ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/app-user && \
    chmod 0440 /etc/sudoers.d/app-user

# Expose the port for API and WebSocket connections
EXPOSE 3000

# Specify entrypoint script
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# Switch to non-root user for better security
USER app-user

# Start server with proper initialization
ENTRYPOINT ["/entrypoint.sh"]
