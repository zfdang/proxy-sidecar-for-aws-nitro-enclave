# AWS Nitro Enclave Sidecar Proxy

A sidecar proxy solution for AWS Nitro Enclave applications to communicate with external services using TLS encryption, ensuring the host cannot access the transmitted content.

## Architecture

This project consists of three main components:

1. **Sidecar Service** - Runs inside the Nitro Enclave and handles TLS-encrypted communication with external services
2. **Host Proxy Service** - Runs on the host and forwards traffic between the enclave and external services
3. **Demo Application** - A sample application that demonstrates the sidecar capabilities

## Features

- End-to-end TLS encryption between enclave applications and external services
- Secure communication using vsock between enclave and host
- Host-transparent encrypted traffic (host cannot decrypt the content)
- Dockerized enclave application for easy deployment
- Complete demo application showcasing the proxy capabilities

## Project Structure

```
├── src/
│   ├── sidecar/          # Enclave sidecar service
│   ├── host_proxy/       # Host proxy service
│   └── demo_app/         # Demo application
├── docker/               # Docker configurations
├── scripts/              # Build and deployment scripts
├── config/               # Configuration files
└── README.md
```

## Quick Start

1. Build the Docker image for the enclave application
2. Start the host proxy service
3. Launch the enclave with the sidecar
4. Run the demo application

Detailed instructions are provided in each component's directory.

## Security Features

- TLS 1.3 encryption for all external communications
- Cryptographic attestation using Nitro Enclave features
- Zero-knowledge proxy - host cannot access encrypted content
- Secure key management within the enclave

## Prerequisites

- AWS EC2 instance with Nitro Enclave support
- Python 3.8+
- Docker
- AWS Nitro CLI

## License

MIT License
