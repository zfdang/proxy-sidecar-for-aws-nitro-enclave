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
from urllib.parse import urlparse

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TunnelClient:
    """Client for establishing network tunnels through host"""
    
    def __init__(self, host_cid: int = 2, tunnel_port: int = 5001):
        self.host_cid = host_cid
        self.tunnel_port = tunnel_port
    
    async def create_tunnel(self, target_host: str, target_port: int):
        """Create a network tunnel to target host through host proxy"""
        try:
            # Connect to tunnel service on host
            reader, writer = await asyncio.open_connection(
                host=self.host_cid,
                port=self.tunnel_port,
                family=socket.AF_VSOCK
            )
            
            # Send tunnel request
            request = {
                'host': target_host,
                'port': target_port
            }
            
            request_data = json.dumps(request).encode('utf-8')
            request_length = len(request_data).to_bytes(4, byteorder='big')
            
            writer.write(request_length)
            writer.write(request_data)
            await writer.drain()
            
            # Read response
            response_length = await reader.readexactly(4)
            length = int.from_bytes(response_length, byteorder='big')
            
            response_data = await reader.readexactly(length)
            response = json.loads(response_data.decode('utf-8'))
            
            if response.get('status') != 'connected':
                raise Exception(f"Tunnel creation failed: {response.get('message', 'Unknown error')}")
            
            logger.info(f"Tunnel established to {target_host}:{target_port}")
            return reader, writer
            
        except Exception as e:
            logger.error(f"Failed to create tunnel: {e}")
            raise

class EnclaveConfig:
    """Configuration for the enclave sidecar"""
    VSOCK_CID = 3  # Enclave CID
    VSOCK_PORT = 5000  # Port for communication with applications
    HOST_CID = 2  # Host CID
    TUNNEL_PORT = 5001  # Port for tunnel service
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
        """Process HTTP request through direct TLS to external service via tunnel"""
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
            
            # Parse URL to get host and port for direct connection
            parsed_url = urlparse(url)
            host = parsed_url.hostname
            port = parsed_url.port or (443 if parsed_url.scheme == 'https' else 80)
            path = parsed_url.path or '/'
            if parsed_url.query:
                path += '?' + parsed_url.query
            
            if parsed_url.scheme != 'https':
                return {
                    'status': 400,
                    'error': 'Only HTTPS URLs are supported for security'
                }
            
            # Create tunnel to target host
            tunnel_client = TunnelClient(self.config.HOST_CID, self.config.TUNNEL_PORT)
            
            try:
                # Establish tunnel
                tunnel_reader, tunnel_writer = await tunnel_client.create_tunnel(host, port)
                
                # Create TLS connection over the tunnel
                ssl_context = self._get_ssl_context()
                
                # Wrap the tunnel connection with TLS
                transport = tunnel_writer.transport
                protocol = transport.get_protocol()
                
                # Create SSL connection over tunnel
                ssl_transport = await asyncio.get_event_loop().start_tls(
                    transport, protocol, ssl_context, server_hostname=host
                )
                
                ssl_reader = asyncio.StreamReader()
                ssl_protocol = asyncio.StreamReaderProtocol(ssl_reader)
                ssl_transport.set_protocol(ssl_protocol)
                
                # Build and send HTTP request over TLS
                http_request = self._build_http_request(method, path, headers, body, host)
                ssl_transport.write(http_request.encode('utf-8'))
                
                # Read response
                response_data = await self._read_http_response(ssl_reader)
                
                # Close connections
                ssl_transport.close()
                tunnel_writer.close()
                await tunnel_writer.wait_closed()
                
                return response_data
                
            except Exception as e:
                logger.error(f"TLS connection through tunnel failed: {e}")
                return {
                    'status': 503,
                    'error': f'Connection failed: {str(e)}',
                    'success': False
                }
                
        except Exception as e:
            logger.error(f"Error processing request: {e}")
            return {
                'status': 500,
                'error': f'Internal error: {str(e)}',
                'success': False
            }
    
    def _get_ssl_context(self):
        """Get SSL context for direct TLS connections"""
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = True
        ssl_context.verify_mode = ssl.CERT_REQUIRED
        ssl_context.minimum_version = ssl.TLSVersion.TLSv1_3
        return ssl_context
    
    def _build_http_request(self, method: str, path: str, headers: Dict[str, str], body: str, host: str) -> str:
        """Build raw HTTP request"""
        # Ensure Host header is set
        if 'Host' not in headers:
            headers['Host'] = host
        
        # Build request line
        request_lines = [f"{method} {path} HTTP/1.1"]
        
        # Add headers
        for header, value in headers.items():
            request_lines.append(f"{header}: {value}")
        
        # Add Content-Length if body exists
        if body:
            if 'Content-Length' not in headers:
                request_lines.append(f"Content-Length: {len(body.encode('utf-8'))}")
        
        # Add Connection: close to avoid keep-alive issues
        if 'Connection' not in headers:
            request_lines.append("Connection: close")
        
        # Empty line before body
        request_lines.append("")
        
        # Add body if exists
        if body:
            request_lines.append(body)
        
        return "\r\n".join(request_lines)
    
    async def _read_http_response(self, reader: asyncio.StreamReader) -> Dict[str, Any]:
        """Read and parse HTTP response"""
        try:
            # Read status line
            status_line = await reader.readline()
            status_line = status_line.decode('utf-8').strip()
            
            if not status_line.startswith('HTTP/'):
                raise ValueError(f"Invalid HTTP response: {status_line}")
            
            # Parse status code
            parts = status_line.split(' ', 2)
            status_code = int(parts[1])
            
            # Read headers
            response_headers = {}
            while True:
                header_line = await reader.readline()
                header_line = header_line.decode('utf-8').strip()
                
                if not header_line:  # Empty line indicates end of headers
                    break
                
                if ':' in header_line:
                    key, value = header_line.split(':', 1)
                    response_headers[key.strip()] = value.strip()
            
            # Read body
            body_data = b""
            if 'Content-Length' in response_headers:
                content_length = int(response_headers['Content-Length'])
                body_data = await reader.readexactly(content_length)
            else:
                # Read until connection closes
                body_data = await reader.read()
            
            response_body = body_data.decode('utf-8', errors='ignore')
            
            return {
                'status': status_code,
                'headers': response_headers,
                'body': response_body,
                'success': True
            }
            
        except Exception as e:
            logger.error(f"Error parsing HTTP response: {e}")
            return {
                'status': 502,
                'error': f'Response parsing failed: {str(e)}',
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
        logger.info("This service provides secure TLS tunneling with zero-knowledge host proxy")
        
        try:
            # Generate initial attestation
            attestation_doc = await self.attestation.generate_attestation()
            logger.info(f"Attestation generated: {attestation_doc.get('timestamp')}")
            
            # Start VSock server for application requests
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
