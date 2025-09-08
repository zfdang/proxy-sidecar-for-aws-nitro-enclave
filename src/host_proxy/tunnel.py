#!/usr/bin/env python3
"""
Network tunnel service running on the host
Provides raw socket forwarding for enclave without decrypting content
"""

import asyncio
import json
import socket
import logging
from typing import Dict, Any, Optional

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class TunnelConfig:
    """Configuration for the network tunnel"""
    ENCLAVE_CID = 3
    ENCLAVE_TUNNEL_PORT = 5001  # Different port for tunnel service
    BUFFER_SIZE = 8192

class NetworkTunnel:
    """Raw network tunnel that forwards encrypted packets without inspection"""
    
    def __init__(self, config: TunnelConfig):
        self.config = config
        self.active_connections = {}
        
    async def start_tunnel_server(self):
        """Start VSock server for tunnel requests"""
        try:
            server = await asyncio.start_server(
                self.handle_tunnel_request,
                family=socket.AF_VSOCK,
                host=socket.VMADDR_CID_ANY,  # Listen on host
                port=self.config.ENCLAVE_TUNNEL_PORT
            )
            
            logger.info(f"Network tunnel server started on port {self.config.ENCLAVE_TUNNEL_PORT}")
            
            async with server:
                await server.serve_forever()
                
        except Exception as e:
            logger.error(f"Failed to start tunnel server: {e}")
            raise
    
    async def handle_tunnel_request(self, enclave_reader: asyncio.StreamReader, enclave_writer: asyncio.StreamWriter):
        """Handle tunnel request from enclave"""
        try:
            # Read tunnel establishment request
            request_length = await enclave_reader.readexactly(4)
            length = int.from_bytes(request_length, byteorder='big')
            
            request_data = await enclave_reader.readexactly(length)
            request = json.loads(request_data.decode('utf-8'))
            
            target_host = request.get('host')
            target_port = request.get('port')
            
            if not target_host or not target_port:
                logger.error("Invalid tunnel request: missing host or port")
                enclave_writer.close()
                return
            
            logger.info(f"Creating tunnel to {target_host}:{target_port}")
            
            # Establish connection to target server
            try:
                target_reader, target_writer = await asyncio.open_connection(
                    target_host, target_port
                )
                
                # Send success response to enclave
                response = {'status': 'connected'}
                response_data = json.dumps(response).encode('utf-8')
                response_length = len(response_data).to_bytes(4, byteorder='big')
                
                enclave_writer.write(response_length)
                enclave_writer.write(response_data)
                await enclave_writer.drain()
                
                # Start bidirectional data forwarding
                await self._forward_data_bidirectional(
                    enclave_reader, enclave_writer,
                    target_reader, target_writer,
                    f"{target_host}:{target_port}"
                )
                
            except Exception as e:
                logger.error(f"Failed to connect to {target_host}:{target_port}: {e}")
                
                # Send error response
                response = {'status': 'error', 'message': str(e)}
                response_data = json.dumps(response).encode('utf-8')
                response_length = len(response_data).to_bytes(4, byteorder='big')
                
                enclave_writer.write(response_length)
                enclave_writer.write(response_data)
                await enclave_writer.drain()
                
                enclave_writer.close()
                
        except Exception as e:
            logger.error(f"Error handling tunnel request: {e}")
        finally:
            if not enclave_writer.is_closing():
                enclave_writer.close()
    
    async def _forward_data_bidirectional(self, 
                                        enclave_reader: asyncio.StreamReader,
                                        enclave_writer: asyncio.StreamWriter,
                                        target_reader: asyncio.StreamReader, 
                                        target_writer: asyncio.StreamWriter,
                                        connection_id: str):
        """Forward data bidirectionally between enclave and target"""
        
        async def forward_enclave_to_target():
            """Forward data from enclave to target (encrypted data)"""
            try:
                while True:
                    data = await enclave_reader.read(self.config.BUFFER_SIZE)
                    if not data:
                        break
                    
                    target_writer.write(data)
                    await target_writer.drain()
                    
            except Exception as e:
                logger.debug(f"Enclave->Target forwarding ended for {connection_id}: {e}")
            finally:
                target_writer.close()
        
        async def forward_target_to_enclave():
            """Forward data from target to enclave (encrypted data)"""
            try:
                while True:
                    data = await target_reader.read(self.config.BUFFER_SIZE)
                    if not data:
                        break
                    
                    enclave_writer.write(data)
                    await enclave_writer.drain()
                    
            except Exception as e:
                logger.debug(f"Target->Enclave forwarding ended for {connection_id}: {e}")
            finally:
                enclave_writer.close()
        
        # Start both forwarding tasks
        logger.info(f"Starting bidirectional forwarding for {connection_id}")
        
        await asyncio.gather(
            forward_enclave_to_target(),
            forward_target_to_enclave(),
            return_exceptions=True
        )
        
        logger.info(f"Tunnel closed for {connection_id}")

class TunnelService:
    """Main tunnel service"""
    
    def __init__(self):
        self.config = TunnelConfig()
        self.tunnel = NetworkTunnel(self.config)
    
    async def start(self):
        """Start the tunnel service"""
        logger.info("Starting Network Tunnel Service")
        logger.info("This service provides raw packet forwarding without content inspection")
        
        try:
            await self.tunnel.start_tunnel_server()
        except Exception as e:
            logger.error(f"Failed to start tunnel service: {e}")
            raise

async def main():
    """Main entry point"""
    try:
        service = TunnelService()
        await service.start()
    except KeyboardInterrupt:
        logger.info("Shutting down tunnel service")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        return 1
    
    return 0

if __name__ == "__main__":
    exit(asyncio.run(main()))
