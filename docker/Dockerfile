# Dockerfile for AWS Nitro Enclave Application
# This builds a container that includes both the sidecar proxy and demo application

FROM python:3.9-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libc6-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY src/ ./src/

# Copy configuration files
COPY config/ ./config/

# Create necessary directories
RUN mkdir -p /app/logs /app/data

# Set Python path
ENV PYTHONPATH="/app/src"

# Create startup script
COPY docker/start-enclave.sh /app/start-enclave.sh
RUN chmod +x /app/start-enclave.sh

# Expose ports for debugging (not used in actual enclave)
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import socket; s = socket.socket(socket.AF_INET, socket.SOCK_STREAM); s.settimeout(5); s.connect(('localhost', 5000)); s.close()" || exit 1

# Run the enclave application
CMD ["/app/start-enclave.sh"]
