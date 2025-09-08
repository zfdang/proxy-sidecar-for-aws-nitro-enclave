#!/usr/bin/env python3
"""
Sidecar service running inside AWS Nitro Enclave
Handles TLS-encrypted communication with external services
"""

import asyncio
import json
import socket
import ssl
import logging
from typing import Dict, Any, Optional
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
import aiohttp

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class EnclaveConfig:
    """Configuration for the enclave sidecar"""
    VSOCK_CID = 3  # Enclave CID
    VSOCK_PORT = 5000  # Port for communication with host
    TLS_VERSION = ssl.PROTOCOL_TLS_CLIENT
    CERT_VERIFY_MODE = ssl.CERT_REQUIRED

class TLSManager:
    """Manages TLS certificates and SSL contexts"""
    
    def __init__(self):
        self.ssl_context = None
        self._setup_ssl_context()
    
    def _setup_ssl_context(self):
        """Setup SSL context for secure external communications"""
        self.ssl_context = ssl.create_default_context()
        self.ssl_context.check_hostname = True
        self.ssl_context.verify_mode = ssl.CERT_REQUIRED
        # Use TLS 1.3 for maximum security
        self.ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        logger.info("SSL context configured for TLS 1.3")

class VSockServer:
    """VSock server for communication with host proxy"""
    
    def __init__(self, config: EnclaveConfig):
        self.config = config
        self.server = None
        self.clients = set()
    
    async def start(self):
        """Start the VSock server"""
        try:
            # Create VSock server
            self.server = await asyncio.start_server(
                self.handle_client,
                family=socket.AF_VSOCK,
                host=self.config.VSOCK_CID,
                port=self.config.VSOCK_PORT
            )
            logger.info(f"VSock server started on CID {self.config.VSOCK_CID}, port {self.config.VSOCK_PORT}")
            
            async with self.server:
                await self.server.serve_forever()
        except Exception as e:
            logger.error(f"Failed to start VSock server: {e}")
            raise
    
    async def handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle incoming client connections from host proxy"""
        client_addr = writer.get_extra_info('peername')
        logger.info(f"New client connected: {client_addr}")
        self.clients.add(writer)
        
        try:
            while True:
                # Read message length (4 bytes)
                length_data = await reader.readexactly(4)
                if not length_data:
                    break
                
                message_length = int.from_bytes(length_data, byteorder='big')
                
                # Read the actual message
                message_data = await reader.readexactly(message_length)
                message = json.loads(message_data.decode('utf-8'))
                
                logger.info(f"Received request: {message.get('method', 'UNKNOWN')} {message.get('url', 'N/A')}")
                
                # Process the request
                response = await self.process_request(message)
                
                # Send response
                await self.send_response(writer, response)
                
        except asyncio.IncompleteReadError:
            logger.info("Client disconnected")
        except Exception as e:
            logger.error(f"Error handling client: {e}")
        finally:
            self.clients.discard(writer)
            writer.close()
            await writer.wait_closed()
    
    async def process_request(self, request: Dict[str, Any]) -> Dict[str, Any]:
        """Process HTTP request through TLS to external service"""
        try:
            method = request.get('method', 'GET').upper()
            url = request.get('url')
            headers = request.get('headers', {})
            body = request.get('body')
            
            if not url:
                return {
                    'status': 400,
                    'error': 'URL is required'
                }
            
            # Create aiohttp session with TLS configuration
            connector = aiohttp.TCPConnector(ssl=TLSManager().ssl_context)
            
            async with aiohttp.ClientSession(connector=connector) as session:
                # Make the request to external service
                async with session.request(
                    method=method,
                    url=url,
                    headers=headers,
                    data=body,
                    timeout=aiohttp.ClientTimeout(total=30)
                ) as response:
                    response_body = await response.text()
                    
                    return {
                        'status': response.status,
                        'headers': dict(response.headers),
                        'body': response_body,
                        'success': True
                    }
                    
        except aiohttp.ClientError as e:
            logger.error(f"HTTP client error: {e}")
            return {
                'status': 500,
                'error': f'HTTP client error: {str(e)}',
                'success': False
            }
        except Exception as e:
            logger.error(f"Unexpected error processing request: {e}")
            return {
                'status': 500,
                'error': f'Internal error: {str(e)}',
                'success': False
            }
    
    async def send_response(self, writer: asyncio.StreamWriter, response: Dict[str, Any]):
        """Send response back to host proxy"""
        try:
            response_data = json.dumps(response).encode('utf-8')
            
            # Send message length first
            length_bytes = len(response_data).to_bytes(4, byteorder='big')
            writer.write(length_bytes)
            
            # Send the actual response
            writer.write(response_data)
            await writer.drain()
            
        except Exception as e:
            logger.error(f"Error sending response: {e}")

class EnclaveAttestation:
    """Handle Nitro Enclave attestation for security verification"""
    
    def __init__(self):
        self.attestation_doc = None
    
    async def generate_attestation(self, nonce: Optional[bytes] = None) -> Dict[str, Any]:
        """Generate attestation document"""
        try:
            # In a real implementation, this would use the Nitro Enclave attestation APIs
            # For demo purposes, we'll return a mock attestation
            return {
                'attestation_doc': 'mock_attestation_document',
                'pcrs': {
                    '0': 'mock_pcr0_value',
                    '1': 'mock_pcr1_value',
                    '2': 'mock_pcr2_value'
                },
                'timestamp': asyncio.get_event_loop().time(),
                'nonce': nonce.hex() if nonce else None
            }
        except Exception as e:
            logger.error(f"Failed to generate attestation: {e}")
            return {'error': str(e)}

class SidecarService:
    """Main sidecar service coordinator"""
    
    def __init__(self):
        self.config = EnclaveConfig()
        self.vsock_server = VSockServer(self.config)
        self.attestation = EnclaveAttestation()
        self.tls_manager = TLSManager()
    
    async def start(self):
        """Start the sidecar service"""
        logger.info("Starting Nitro Enclave Sidecar Service")
        
        try:
            # Generate initial attestation
            attestation_doc = await self.attestation.generate_attestation()
            logger.info(f"Attestation generated: {attestation_doc.get('timestamp')}")
            
            # Start VSock server
            await self.vsock_server.start()
            
        except Exception as e:
            logger.error(f"Failed to start sidecar service: {e}")
            raise

async def main():
    """Main entry point"""
    try:
        sidecar = SidecarService()
        await sidecar.start()
    except KeyboardInterrupt:
        logger.info("Shutting down sidecar service")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
