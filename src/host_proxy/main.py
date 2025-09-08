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
from urllib.parse import urlparse
import aiohttp
from aiohttp import web

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

class ProxyHandler:
    """HTTP request handler that forwards to enclave"""
    
    def __init__(self, config: HostConfig):
        self.config = config
        self.vsock_client = VSockClient(config)
    
    async def handle_request(self, request: web.Request) -> web.Response:
        """Handle incoming HTTP request - forward metadata only, enclave handles TLS"""
        try:
            # Extract only essential routing information
            method = request.method
            url = str(request.url)
            headers = dict(request.headers)
            
            # Read request body (this will be re-encrypted by sidecar)
            try:
                body = await request.text()
            except:
                body = None
            
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
            response = await self._send_with_retry(enclave_request)
            
            if response is None:
                return web.Response(
                    status=503,
                    text='Service unavailable: Unable to connect to enclave',
                    headers={'Content-Type': 'text/plain'}
                )
            
            if not response.get('success', False):
                return web.Response(
                    status=response.get('status', 500),
                    text=response.get('error', 'Unknown error'),
                    headers={'Content-Type': 'text/plain'}
                )
            
            # Return response from enclave (already decrypted within enclave)
            response_headers = response.get('headers', {})
            
            return web.Response(
                status=response.get('status', 200),
                text=response.get('body', ''),
                headers=response_headers
            )
            
        except Exception as e:
            logger.error(f"Error handling request: {e}")
            return web.Response(
                status=500,
                text=f'Internal proxy error: {str(e)}',
                headers={'Content-Type': 'text/plain'}
            )
    
    async def _send_with_retry(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Send request with retry logic"""
        last_error = None
        
        for attempt in range(self.config.MAX_RETRIES):
            try:
                response = await self.vsock_client.send_request(request)
                if response is not None:
                    return response
            except Exception as e:
                last_error = e
                logger.warning(f"Attempt {attempt + 1} failed: {e}")
                
                if attempt < self.config.MAX_RETRIES - 1:
                    await asyncio.sleep(self.config.RETRY_DELAY)
        
        logger.error(f"All retry attempts failed. Last error: {last_error}")
        return None
    
    async def handle_health_check(self, request: web.Request) -> web.Response:
        """Health check endpoint"""
        try:
            # Try to connect to enclave
            if await self.vsock_client.connect():
                await self.vsock_client.disconnect()
                return web.Response(
                    status=200,
                    text='OK: Proxy and enclave are healthy',
                    headers={'Content-Type': 'text/plain'}
                )
            else:
                return web.Response(
                    status=503,
                    text='Unhealthy: Cannot connect to enclave',
                    headers={'Content-Type': 'text/plain'}
                )
        except Exception as e:
            return web.Response(
                status=503,
                text=f'Unhealthy: {str(e)}',
                headers={'Content-Type': 'text/plain'}
            )

class HostProxyService:
    """Main host proxy service"""
    
    def __init__(self):
        self.config = HostConfig()
        self.handler = ProxyHandler(self.config)
        self.app = None
        self.runner = None
    
    def setup_routes(self):
        """Setup HTTP routes"""
        self.app = web.Application()
        
        # Health check endpoint
        self.app.router.add_get('/health', self.handler.handle_health_check)
        
        # Catch-all proxy route
        self.app.router.add_route('*', '/{path:.*}', self.handler.handle_request)
    
    async def start(self):
        """Start the proxy service"""
        logger.info("Starting Host Proxy Service")
        
        try:
            self.setup_routes()
            
            # Start the web server
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            site = web.TCPSite(self.runner, '0.0.0.0', self.config.HTTP_PORT)
            await site.start()
            
            logger.info(f"Host proxy listening on port {self.config.HTTP_PORT}")
            logger.info(f"Health check available at http://localhost:{self.config.HTTP_PORT}/health")
            
            # Keep the service running
            while True:
                await asyncio.sleep(1)
                
        except Exception as e:
            logger.error(f"Failed to start proxy service: {e}")
            raise
    
    async def stop(self):
        """Stop the proxy service"""
        if self.runner:
            await self.runner.cleanup()
        
        if self.handler.vsock_client:
            await self.handler.vsock_client.disconnect()
        
        logger.info("Host proxy service stopped")

async def main():
    """Main entry point"""
    try:
        proxy = HostProxyService()
        await proxy.start()
    except KeyboardInterrupt:
        logger.info("Shutting down host proxy service")
        if 'proxy' in locals():
            await proxy.stop()
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
