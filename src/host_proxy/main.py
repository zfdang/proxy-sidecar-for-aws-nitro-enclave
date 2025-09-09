#!/usr/bin/env python3
"""
Host proxy service for AWS Nitro Enclave
Forwards traffic between applications and the enclave sidecar
"""

import asyncio
import json
import socket
import logging
from typing import Dict, Any, Optional
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
from urllib.parse import urlparse, parse_qs
from socketserver import ThreadingMixIn

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class HostConfig:
    """Configuration for the host proxy"""
    HTTP_PORT = 8080  # Port for receiving HTTP requests
    ENCLAVE_CID = 3   # Enclave CID
    ENCLAVE_PORT = 5000  # Enclave VSock port
    MAX_RETRIES = 3
    RETRY_DELAY = 1.0

class VSockClient:
    """VSock client for communication with enclave sidecar"""
    
    def __init__(self, config: HostConfig):
        self.config = config
        self.connection = None
        self.reader = None
        self.writer = None
    
    async def connect(self) -> bool:
        """Connect to the enclave sidecar"""
        try:
            # Create VSock connection to enclave
            self.reader, self.writer = await asyncio.open_connection(
                host=self.config.ENCLAVE_CID,
                port=self.config.ENCLAVE_PORT,
                family=socket.AF_VSOCK
            )
            logger.info(f"Connected to enclave CID {self.config.ENCLAVE_CID}, port {self.config.ENCLAVE_PORT}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to enclave: {e}")
            return False
    
    async def disconnect(self):
        """Disconnect from the enclave"""
        if self.writer:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None
            self.reader = None
        logger.info("Disconnected from enclave")
    
    async def send_request(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request to enclave and get response"""
        if not self.writer or not self.reader:
            if not await self.connect():
                return None
        
        try:
            # Serialize request
            request_data = json.dumps(request).encode('utf-8')
            
            # Send message length first
            length_bytes = len(request_data).to_bytes(4, byteorder='big')
            self.writer.write(length_bytes)
            
            # Send the actual request
            self.writer.write(request_data)
            await self.writer.drain()
            
            # Read response length
            length_data = await self.reader.readexactly(4)
            response_length = int.from_bytes(length_data, byteorder='big')
            
            # Read the actual response
            response_data = await self.reader.readexactly(response_length)
            response = json.loads(response_data.decode('utf-8'))
            
            return response
            
        except Exception as e:
            logger.error(f"Error communicating with enclave: {e}")
            await self.disconnect()
            return None

class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    """HTTP Server that can handle requests in separate threads"""
    daemon_threads = True

class ProxyHandler(BaseHTTPRequestHandler):
    """HTTP request handler that forwards to enclave"""
    
    def __init__(self, *args, **kwargs):
        self.config = HostConfig()
        self.vsock_client = VSockClient(self.config)
        super().__init__(*args, **kwargs)
    
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.info(f"{self.address_string()} - {format % args}")
    
    def do_GET(self):
        """Handle GET requests"""
        self._handle_request('GET')
    
    def do_POST(self):
        """Handle POST requests"""
        self._handle_request('POST')
    
    def do_PUT(self):
        """Handle PUT requests"""
        self._handle_request('PUT')
    
    def do_DELETE(self):
        """Handle DELETE requests"""
        self._handle_request('DELETE')
    
    def do_HEAD(self):
        """Handle HEAD requests"""
        self._handle_request('HEAD')
    
    def do_OPTIONS(self):
        """Handle OPTIONS requests"""
        self._handle_request('OPTIONS')
    
    def _handle_request(self, method: str):
        """Handle incoming HTTP request - forward metadata only, enclave handles TLS"""
        try:
            # Handle health check
            if self.path == '/health':
                self._handle_health_check()
                return
            
            # Extract request information
            url = self.path
            headers = dict(self.headers)
            
            # Read request body if present
            body = None
            if 'Content-Length' in headers:
                content_length = int(headers['Content-Length'])
                body = self.rfile.read(content_length).decode('utf-8')
            
            logger.info(f"Routing request: {method} to enclave sidecar")
            # Note: URL and other details are logged but the actual TLS connection
            # and encryption will be handled entirely within the enclave
            
            # Create minimal request for enclave (enclave will handle TLS directly)
            enclave_request = {
                'method': method,
                'url': url,
                'headers': headers,
                'body': body
            }
            
            # Send to enclave with retries
            response = self._send_with_retry(enclave_request)
            
            if response is None:
                self._send_error_response(503, 'Service unavailable: Unable to connect to enclave')
                return
            
            if not response.get('success', False):
                error_msg = response.get('error', 'Unknown error')
                status_code = response.get('status', 500)
                self._send_error_response(status_code, error_msg)
                return
            
            # Send successful response
            self._send_success_response(response)
            
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            self._send_error_response(500, f'Internal proxy error: {str(e)}')
    
    def _send_with_retry(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request with retry logic"""
        last_error = None
        
        for attempt in range(self.config.MAX_RETRIES):
            try:
                # Create new connection for each attempt
                if not asyncio.get_event_loop().is_running():
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                else:
                    loop = asyncio.get_event_loop()
                
                # Run the async request in the event loop
                response = loop.run_until_complete(self.vsock_client.send_request(request))
                if response is not None:
                    return response
                    
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config.MAX_RETRIES - 1:
                    import time
                    time.sleep(self.config.RETRY_DELAY)
        
        logger.error(f"All retry attempts failed. Last error: {last_error}")
        return None
    
    def _handle_health_check(self):
        """Health check endpoint"""
        try:
            # Create event loop if needed
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            
            # Try to connect to enclave
            connected = loop.run_until_complete(self.vsock_client.connect())
            if connected:
                loop.run_until_complete(self.vsock_client.disconnect())
                self._send_text_response(200, 'OK: Proxy and enclave are healthy')
            else:
                self._send_text_response(503, 'Unhealthy: Cannot connect to enclave')
                
        except Exception as e:
            self._send_text_response(503, f'Unhealthy: {str(e)}')
    
    def _send_success_response(self, response: Dict[str, Any]):
        """Send successful response from enclave"""
        status_code = response.get('status', 200)
        headers = response.get('headers', {})
        body = response.get('body', '')
        
        self.send_response(status_code)
        
        # Send headers
        for header, value in headers.items():
            if header.lower() not in ['content-length', 'connection']:
                self.send_header(header, value)
        
        # Send content
        body_bytes = body.encode('utf-8')
        self.send_header('Content-Length', str(len(body_bytes)))
        self.send_header('Content-Type', headers.get('Content-Type', 'text/plain'))
        self.end_headers()
        
        if body_bytes:
            self.wfile.write(body_bytes)
    
    def _send_error_response(self, status_code: int, message: str):
        """Send error response"""
        self._send_text_response(status_code, message)
    
    def _send_text_response(self, status_code: int, message: str):
        """Send plain text response"""
        self.send_response(status_code)
        self.send_header('Content-Type', 'text/plain')
        message_bytes = message.encode('utf-8')
        self.send_header('Content-Length', str(len(message_bytes)))
        self.end_headers()
        self.wfile.write(message_bytes)

class HostProxyService:
    """Main host proxy service"""
    
    def __init__(self):
        self.config = HostConfig()
        self.server = None
    
    def start(self):
        """Start the proxy service"""
        logger.info("Starting Host Proxy Service")
        
        try:
            # Create HTTP server
            server_address = ('0.0.0.0', self.config.HTTP_PORT)
            self.server = ThreadedHTTPServer(server_address, ProxyHandler)
            
            logger.info(f"Host proxy listening on port {self.config.HTTP_PORT}")
            logger.info(f"Health check available at http://localhost:{self.config.HTTP_PORT}/health")
            
            # Start serving requests
            self.server.serve_forever()
            
        except Exception as e:
            logger.error(f"Failed to start proxy service: {e}")
            raise
    
    def stop(self):
        """Stop the proxy service"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        
        logger.info("Host proxy service stopped")

def main():
    """Main entry point"""
    try:
        proxy = HostProxyService()
        proxy.start()
    except KeyboardInterrupt:
        logger.info("Shutting down host proxy service")
        if 'proxy' in locals():
            proxy.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(main())
