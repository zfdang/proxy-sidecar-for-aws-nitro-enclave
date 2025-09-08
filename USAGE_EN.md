# AWS Nitro Enclave Sidecar Proxy - Usage Guide

## Project Overview

This project provides a sidecar proxy solution for applications running in AWS Nitro Enclave environments, enabling secure communication with external services through TLS encryption while ensuring the host cannot access the transmitted content.

## Architecture Components

### 1. Sidecar Service (`src/sidecar/main.py`)
- Runs inside the Nitro Enclave
- Handles TLS-encrypted communication with external services
- Uses VSock for communication with the host
- Implements end-to-end encryption, host cannot decrypt content

### 2. Host Proxy Service (`src/host_proxy/main.py`)
- Runs on the host machine
- Receives HTTP requests from applications
- Forwards requests to the sidecar inside the enclave via VSock
- Provides health checking and monitoring capabilities

### 3. Network Tunnel Service (`src/host_proxy/tunnel.py`)
- Provides raw socket forwarding for encrypted traffic
- Enables direct TLS connections from enclave to external services
- Ensures zero-knowledge operation - host cannot inspect traffic content

### 4. Demo Application (`src/demo_app/main.py`)
- Sample application showcasing sidecar proxy capabilities
- Tests various HTTP request types
- Demonstrates concurrent request handling
- Generates test reports

## Quick Start

### 1. Environment Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Or use development script
./scripts/dev.sh deps
```

### 2. Local Development Mode
```bash
# Start development environment
./scripts/dev.sh start

# Check service status
./scripts/dev.sh status

# View logs
./scripts/dev.sh logs

# Run tests
./scripts/dev.sh test
```

### 3. Local Run (without Docker)
```bash
# Local run mode
./scripts/dev.sh local
```

## Build and Deployment

### 1. Build Docker Images
```bash
# Build all components
./scripts/build.sh

# Build Docker images only
./scripts/build.sh docker

# Build Enclave image only
./scripts/build.sh enclave
```

### 2. AWS EC2 Deployment
```bash
# 1. Copy build artifacts to EC2 instance
scp -r build/ ec2-user@your-instance:/home/ec2-user/

# 2. Run deployment script on EC2 instance
sudo ./deploy.sh
```

## Configuration

### Main Configuration File (`config/config.json`)
```json
{
  "enclave": {
    "cid": 3,                    // Enclave CID
    "port": 5000,                // VSock port
    "memory_mb": 512,            // Memory allocation
    "cpu_count": 1               // CPU core count
  },
  "host_proxy": {
    "port": 8080,                // HTTP proxy port
    "max_retries": 3,            // Maximum retry attempts
    "retry_delay": 1.0           // Retry delay
  },
  "tls": {
    "min_version": "TLSv1.3",    // Minimum TLS version
    "verify_certificates": true   // Certificate verification
  }
}
```

### Environment Variables (`config/.env`)
```bash
ENCLAVE_CID=3
ENCLAVE_PORT=5000
HOST_PROXY_PORT=8080
LOG_LEVEL=INFO
DEBUG_MODE=true
```

## API Usage

### Health Check
```bash
curl http://localhost:8080/health
```

### Proxy External Services
```bash
# GET request
curl http://localhost:8080/https://httpbin.org/get

# POST request
curl -X POST http://localhost:8080/https://httpbin.org/post \
  -H "Content-Type: application/json" \
  -d '{"key": "value"}'
```

## Security Features

### 1. True End-to-End TLS Encryption
- All external communications use TLS 1.3
- TLS connections terminate inside the enclave
- Host cannot decrypt transmission content
- Support for certificate verification

### 2. Enclave Isolation
- Applications run inside Nitro Enclave
- Memory encryption and isolation
- Verifiable execution environment
- Hardware-level security boundaries

### 3. VSock Communication
- Secure inter-process communication between enclave and host
- Does not go through network stack
- Only metadata transmission for routing

### 4. Zero-Knowledge Host Operation
- Host provides raw packet forwarding only
- No access to encrypted traffic content
- Complete isolation of sensitive data

## Development Tools

### Development Script (`scripts/dev.sh`)
```bash
./scripts/dev.sh start     # Start development environment
./scripts/dev.sh stop      # Stop development environment
./scripts/dev.sh test      # Run tests
./scripts/dev.sh logs      # View logs
./scripts/dev.sh clean     # Clean environment
./scripts/dev.sh local     # Local run
./scripts/dev.sh status    # Check status
```

### Build Script (`scripts/build.sh`)
```bash
./scripts/build.sh build     # Complete build
./scripts/build.sh docker    # Build Docker images
./scripts/build.sh enclave   # Build Enclave image
./scripts/build.sh clean     # Clean build artifacts
```

## Monitoring and Debugging

### 1. Log Viewing
```bash
# View all service logs
./scripts/dev.sh logs

# View specific service logs
./scripts/dev.sh logs host-proxy

# View Enclave logs
sudo nitro-cli describe-enclaves
sudo nitro-cli console --enclave-id <enclave-id>
```

### 2. Performance Monitoring
```bash
# Check Enclave status
sudo nitro-cli describe-enclaves

# View resource usage
docker stats

# Check network connections
netstat -tln | grep 8080
```

## Troubleshooting

### 1. Common Issues

#### Enclave Startup Failure
```bash
# Check resource allocation
sudo nitro-cli allocate-memory --memory 512

# Check device permissions
ls -la /dev/nitro_enclaves

# View detailed errors
sudo nitro-cli run-enclave --debug-mode ...
```

#### VSock Connection Failure
```bash
# Check Enclave CID configuration
sudo nitro-cli describe-enclaves

# Verify port listening
sudo netstat -na | grep vsock
```

#### TLS Connection Errors
```bash
# Check certificate configuration
openssl s_client -connect httpbin.org:443

# Verify TLS version support
python3 -c "import ssl; print(ssl.OPENSSL_VERSION)"
```

#### Network Tunnel Issues
```bash
# Check tunnel service status
ps aux | grep tunnel

# Verify tunnel port availability
netstat -tln | grep 5001

# Test direct tunnel connection
telnet localhost 5001
```

### 2. Debug Mode
```bash
# Enable debug mode
export DEBUG_MODE=true

# Increase log level
export LOG_LEVEL=DEBUG

# Run debug version
./scripts/dev.sh local
```

## Production Deployment

### 1. System Requirements
- AWS EC2 M5n, M5dn, R5n, R5dn, C5n, or C6in instance types
- Amazon Linux 2 or Ubuntu 18.04+
- At least 1GB RAM and 1 vCPU for enclave
- Docker 19.03+
- AWS Nitro CLI

### 2. Security Configuration
- Disable debug mode
- Use production certificates
- Configure appropriate IAM permissions
- Enable CloudWatch monitoring
- Implement proper key management

### 3. Monitoring and Alerting
- Integrate CloudWatch Logs
- Configure health check alerts
- Monitor Enclave status
- Set up performance metrics
- Implement security event monitoring

## Security Considerations

### 1. Threat Model
- Host compromise scenarios
- Network traffic analysis
- Side-channel attacks
- Certificate validation

### 2. Best Practices
- Regular security updates
- Proper key rotation
- Network segmentation
- Access control policies

## Performance Optimization

### 1. Resource Allocation
- Optimal memory allocation for enclaves
- CPU core assignment
- Network buffer tuning

### 2. Connection Management
- Connection pooling strategies
- Keep-alive optimization
- Request batching

## Integration Examples

### 1. With Existing Applications
```python
import requests

# Configure proxy
proxies = {
    'http': 'http://localhost:8080',
    'https': 'http://localhost:8080'
}

# Make requests through sidecar
response = requests.get('https://api.example.com/data', proxies=proxies)
```

### 2. Custom Client Implementation
```python
# Direct integration with sidecar service
from src.demo_app.main import SecureHttpClient

client = SecureHttpClient('http://localhost:8080')
response = client.get('https://api.example.com/data')
```

## Testing

### 1. Unit Tests
```bash
# Run unit tests
python -m pytest tests/

# Run with coverage
python -m pytest tests/ --cov=src/
```

### 2. Integration Tests
```bash
# Run integration tests
./scripts/dev.sh test

# Run specific test suite
./scripts/dev.sh test --suite integration
```

### 3. Security Tests
```bash
# Test TLS configuration
./tests/security/test_tls.sh

# Test enclave isolation
./tests/security/test_isolation.sh
```

## Contributing

### 1. Development Process
1. Fork the repository
2. Create a feature branch
3. Write tests for new functionality
4. Implement the feature
5. Run all tests
6. Submit a pull request

### 2. Code Standards
- Follow PEP 8 for Python code
- Use type hints where appropriate
- Write comprehensive docstrings
- Include unit tests for new features

### 3. Security Review
- All security-related changes require review
- Test security assumptions
- Document threat model changes

## License

MIT License - See LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: [Project Issues](https://github.com/zfdang/proxy-sidecar-for-aws-nitro-enclave/issues)
- Documentation: See project README and this usage guide
- Security Issues: Please report privately to maintainers

## Changelog

See CHANGELOG.md for version history and release notes.
