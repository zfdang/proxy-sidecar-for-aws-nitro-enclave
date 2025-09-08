# AWS Nitro Enclave Sidecar Proxy

A sidecar proxy solution for AWS Nitro Enclave applications to communicate with external services using TLS encryption, ensuring the host cannot access the transmitted content.

## Architecture

This project consists of three main components:

1. **Sidecar Service** - Runs inside the Nitro Enclave and handles TLS-encrypted communication with external services
2. **Host Proxy Service** - Runs on the host and forwards traffic between the enclave and external services
3. **Demo Application** - A sample application that demonstrates the sidecar capabilities

### Communication Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        AWS Nitro Enclave                                 │
│  ┌─────────────────┐    ┌─────────────────┐                             │
│  │                 │    │                 │    ╔═══════════════════╗    │
│  │   Demo App      │◄──►│  Sidecar Proxy  │◄═══╣   TLS 1.3 Tunnel ║    │
│  │                 │    │                 │    ╚═══════════════════╝    │
│  │  - HTTP Client  │    │ - TLS Handler   │              │              │
│  │  - Test Suite   │    │ - VSock Server  │              │              │
│  │                 │    │ - Attestation   │              │              │
│  └─────────────────┘    └─────────────────┘              │              │
│                                   │                      │              │
│                                   │ Metadata Only        │              │
│                                   │ via VSock            │              │
└───────────────────────────────────┼──────────────────────┼──────────────┘
                                    │                      │
                                    ▼                      │
┌─────────────────────────────────────────────────────────┼──────────────┐
│                           Host EC2 Instance             │              │
│                      ┌─────────────────┐                │              │
│                      │                 │                │              │
│                      │  Host Proxy     │                │              │
│                      │                 │        🔒 Host cannot         │
│                      │ - HTTP Server   │        decrypt this traffic   │
│                      │ - VSock Client  │                │              │
│                      │ - Metadata Fwd  │                │              │
│                      └─────────────────┘                │              │
│                               │                          │              │
│                               │ Routing Only             │              │
└───────────────────────────────┼──────────────────────────┼──────────────┘
                                │                          │
                                ▼                          │
┌─────────────────────────────────────────────────────────┼──────────────┐
│                        External Services                │              │
│                                                         │              │
│  ┌─────────────────┐  ┌─────────────────┐  ┌───────────▼─────────────┐ │
│  │   httpbin.org   │  │   GitHub API    │  │   Other APIs            │ │
│  │                 │  │                 │  │                         │ │
│  │ - Test Endpoint │  │ - User Data     │  │ - Custom APIs          │ │
│  │ - JSON Response │  │ - Public Data   │  │ - REST/GraphQL         │ │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

Security Flow:
1. Demo App sends HTTP request to Sidecar (within enclave)
2. Sidecar establishes DIRECT TLS 1.3 connection to external service
3. Sidecar sends only routing metadata to Host Proxy via VSock  
4. Host Proxy cannot decrypt the TLS traffic - it only routes packets
5. All cryptographic operations happen within the secure enclave
6. Response flows back encrypted through the same secure channel

Key Security Features:
• TLS termination happens inside the enclave, not on the host
• Host only sees encrypted packets and routing metadata  
• End-to-end encryption from enclave to external service
• Zero-knowledge proxy - host cannot access sensitive data
```

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

**📖 Detailed instructions:**
- **English**: See [USAGE_EN.md](USAGE_EN.md) for comprehensive usage guide
- **中文**: See [USAGE.md](USAGE.md) for detailed Chinese documentation

## Security Features

- **True End-to-End TLS Encryption**: TLS 1.3 connections established directly from within the enclave
- **Zero-Knowledge Host Proxy**: Host only forwards encrypted packets without access to content
- **Raw Socket Tunneling**: Network tunnel service provides transparent packet forwarding
- **Enclave-Terminated TLS**: All cryptographic operations happen within the secure enclave
- **Cryptographic Attestation**: Using Nitro Enclave attestation for trust verification
- **Memory Isolation**: Application and crypto keys protected by hardware-level isolation

## Prerequisites

- AWS EC2 instance with Nitro Enclave support
- Python 3.8+
- Docker
- AWS Nitro CLI

## License

MIT License
