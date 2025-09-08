#!/bin/bash
# Build script for AWS Nitro Enclave Sidecar Proxy

set -e

echo "Building AWS Nitro Enclave Sidecar Proxy Project"
echo "================================================="

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
BUILD_DIR="$PROJECT_ROOT/build"
IMAGE_NAME="nitro-enclave-sidecar"
IMAGE_TAG="latest"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check prerequisites
check_prerequisites() {
    log_info "Checking prerequisites..."
    
    # Check Docker
    if ! command -v docker &> /dev/null; then
        log_error "Docker is not installed or not in PATH"
        exit 1
    fi
    
    # Check Nitro CLI (if available)
    if command -v nitro-cli &> /dev/null; then
        log_info "Nitro CLI found: $(nitro-cli --version)"
    else
        log_warn "Nitro CLI not found. Install it for full enclave functionality."
    fi
    
    log_info "Prerequisites check completed"
}

# Clean previous builds
clean_build() {
    log_info "Cleaning previous builds..."
    rm -rf "$BUILD_DIR"
    mkdir -p "$BUILD_DIR"
    
    # Remove Docker images if they exist
    if docker images | grep -q "$IMAGE_NAME"; then
        log_info "Removing existing Docker images..."
        docker rmi "$IMAGE_NAME:$IMAGE_TAG" 2>/dev/null || true
    fi
}

# Build Docker images
build_docker_images() {
    log_info "Building Docker images..."
    
    cd "$PROJECT_ROOT"
    
    # Build enclave image
    log_info "Building enclave image..."
    docker build -f docker/Dockerfile -t "$IMAGE_NAME:$IMAGE_TAG" .
    
    # Build host proxy image
    log_info "Building host proxy image..."
    docker build -f docker/Dockerfile.host -t "$IMAGE_NAME-host:$IMAGE_TAG" .
    
    # Build demo client image
    log_info "Building demo client image..."
    docker build -f docker/Dockerfile.client -t "$IMAGE_NAME-client:$IMAGE_TAG" .
    
    log_info "Docker images built successfully"
}

# Create Nitro Enclave Image File (EIF)
build_enclave_image() {
    if command -v nitro-cli &> /dev/null; then
        log_info "Creating Nitro Enclave Image File (EIF)..."
        
        cd "$BUILD_DIR"
        
        # Create EIF from Docker image
        nitro-cli build-enclave \
            --docker-uri "$IMAGE_NAME:$IMAGE_TAG" \
            --output-file "$IMAGE_NAME.eif" 2>&1 | tee build-enclave.log
        
        if [ -f "$IMAGE_NAME.eif" ]; then
            log_info "Enclave image file created: $BUILD_DIR/$IMAGE_NAME.eif"
            
            # Get EIF info
            nitro-cli describe-eif --eif-path "$IMAGE_NAME.eif" > eif-info.json
            log_info "EIF information saved to: $BUILD_DIR/eif-info.json"
        else
            log_error "Failed to create enclave image file"
            return 1
        fi
    else
        log_warn "Skipping EIF creation - Nitro CLI not available"
    fi
}

# Create deployment artifacts
create_artifacts() {
    log_info "Creating deployment artifacts..."
    
    # Copy configuration files
    cp -r "$PROJECT_ROOT/config" "$BUILD_DIR/"
    cp -r "$PROJECT_ROOT/scripts" "$BUILD_DIR/"
    cp "$PROJECT_ROOT/requirements.txt" "$BUILD_DIR/"
    
    # Create deployment script
    cat > "$BUILD_DIR/deploy.sh" << 'EOF'
#!/bin/bash
# Deployment script for AWS Nitro Enclave Sidecar

set -e

echo "Deploying AWS Nitro Enclave Sidecar..."

# Check if running on EC2 instance with Nitro Enclave support
if [ ! -f /dev/nitro_enclaves ]; then
    echo "Warning: Nitro Enclave device not found. Ensure you're running on a supported EC2 instance."
fi

# Start host proxy
echo "Starting host proxy service..."
docker run -d \
    --name nitro-sidecar-proxy \
    --restart unless-stopped \
    -p 8080:8080 \
    nitro-enclave-sidecar-host:latest

# Allocate resources for enclave
echo "Allocating resources for enclave..."
sudo nitro-cli allocate-memory --memory 512

# Run enclave
if [ -f "nitro-enclave-sidecar.eif" ]; then
    echo "Starting Nitro Enclave..."
    sudo nitro-cli run-enclave \
        --cpu-count 1 \
        --memory 512 \
        --eif-path nitro-enclave-sidecar.eif \
        --enclave-cid 3 \
        --debug-mode
else
    echo "Warning: EIF file not found. Running in Docker mode for testing..."
    docker run -d \
        --name nitro-sidecar-enclave \
        --restart unless-stopped \
        nitro-enclave-sidecar:latest
fi

echo "Deployment completed"
EOF
    
    chmod +x "$BUILD_DIR/deploy.sh"
    
    # Create README for deployment
    cat > "$BUILD_DIR/README-DEPLOYMENT.md" << 'EOF'
# Deployment Instructions

## Prerequisites
- AWS EC2 instance with Nitro Enclave support
- Docker installed
- Nitro CLI installed
- Sufficient IAM permissions

## Deployment Steps

1. Copy the build artifacts to your EC2 instance
2. Run the deployment script:
   ```bash
   sudo ./deploy.sh
   ```

## Verification

1. Check host proxy health:
   ```bash
   curl http://localhost:8080/health
   ```

2. Check enclave status:
   ```bash
   sudo nitro-cli describe-enclaves
   ```

## Configuration

Edit the configuration files in the `config/` directory as needed before deployment.
EOF

    log_info "Deployment artifacts created in: $BUILD_DIR"
}

# Main build process
main() {
    cd "$PROJECT_ROOT"
    
    log_info "Starting build process for Nitro Enclave Sidecar Proxy"
    log_info "Project root: $PROJECT_ROOT"
    
    check_prerequisites
    clean_build
    build_docker_images
    build_enclave_image
    create_artifacts
    
    log_info "Build completed successfully!"
    log_info "Build artifacts location: $BUILD_DIR"
    log_info ""
    log_info "Next steps:"
    log_info "1. Copy the build directory to your AWS EC2 instance"
    log_info "2. Run the deployment script: sudo ./deploy.sh"
    log_info "3. Test the proxy: curl http://localhost:8080/health"
}

# Handle script arguments
case "${1:-build}" in
    "clean")
        clean_build
        ;;
    "docker")
        build_docker_images
        ;;
    "enclave")
        build_enclave_image
        ;;
    "artifacts")
        create_artifacts
        ;;
    "build"|"")
        main
        ;;
    *)
        echo "Usage: $0 [clean|docker|enclave|artifacts|build]"
        exit 1
        ;;
esac
