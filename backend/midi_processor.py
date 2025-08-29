#!/usr/bin/env python3
"""
MIDI Processor for Piano LED Visualizer
Handles real-time MIDI input processing and WebSocket communication
"""

import asyncio
import json
import time
import logging
from typing import Dict, List, Optional, Callable
from dataclasses import dataclass, asdict
from threading import Thread, Lock
import websockets
from websockets.server import WebSocketServerProtocol

try:
    import rtmidi
except ImportError:
    rtmidi = None
    logging.warning("rtmidi not available - MIDI input will be simulated")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class MIDIEvent:
    """MIDI event data structure"""
    type: str  # 'note_on', 'note_off', 'control_change', etc.
    note: Optional[int] = None
    velocity: Optional[int] = None
    channel: int = 0
    timestamp: float = 0.0
    control: Optional[int] = None
    value: Optional[int] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON serialization"""
        return {k: v for k, v in asdict(self).items() if v is not None}

class MIDIInputHandler:
    """Handles MIDI input from various sources"""
    
    def __init__(self):
        self.midi_in = None
        self.port_name = None
        self.is_connected = False
        self.event_callback: Optional[Callable] = None
        self._lock = Lock()
        
    def set_event_callback(self, callback: Callable[[MIDIEvent], None]):
        """Set callback function for MIDI events"""
        with self._lock:
            self.event_callback = callback
    
    def get_available_ports(self) -> List[str]:
        """Get list of available MIDI input ports"""
        if not rtmidi:
            return ["Simulated MIDI Input"]
        
        try:
            midi_in = rtmidi.MidiIn()
            ports = []
            for i in range(midi_in.get_port_count()):
                ports.append(midi_in.get_port_name(i))
            midi_in.close_port()
            return ports
        except Exception as e:
            logger.error(f"Error getting MIDI ports: {e}")
            return []
    
    def connect(self, port_name: Optional[str] = None) -> bool:
        """Connect to MIDI input port"""
        if not rtmidi:
            logger.info("Using simulated MIDI input")
            self.is_connected = True
            self.port_name = "Simulated MIDI Input"
            return True
        
        try:
            self.midi_in = rtmidi.MidiIn()
            
            if port_name:
                # Connect to specific port
                ports = self.get_available_ports()
                if port_name in ports:
                    port_index = ports.index(port_name)
                    self.midi_in.open_port(port_index)
                    self.port_name = port_name
                else:
                    logger.error(f"Port '{port_name}' not found")
                    return False
            else:
                # Connect to first available port
                if self.midi_in.get_port_count() > 0:
                    self.midi_in.open_port(0)
                    self.port_name = self.midi_in.get_port_name(0)
                else:
                    logger.error("No MIDI input ports available")
                    return False
            
            # Set callback for MIDI messages
            self.midi_in.set_callback(self._midi_callback)
            self.is_connected = True
            logger.info(f"Connected to MIDI port: {self.port_name}")
            return True
            
        except Exception as e:
            logger.error(f"Error connecting to MIDI port: {e}")
            return False
    
    def _midi_callback(self, message, data):
        """Handle incoming MIDI messages"""
        try:
            midi_bytes, timestamp = message
            
            if len(midi_bytes) < 2:
                return
            
            status_byte = midi_bytes[0]
            message_type = status_byte & 0xF0
            channel = status_byte & 0x0F
            
            event = None
            current_time = time.time() * 1000  # Convert to milliseconds
            
            if message_type == 0x90:  # Note On
                note = midi_bytes[1]
                velocity = midi_bytes[2] if len(midi_bytes) > 2 else 64
                
                if velocity > 0:
                    event = MIDIEvent(
                        type='note_on',
                        note=note,
                        velocity=velocity,
                        channel=channel,
                        timestamp=current_time
                    )
                else:
                    # Velocity 0 is treated as note off
                    event = MIDIEvent(
                        type='note_off',
                        note=note,
                        channel=channel,
                        timestamp=current_time
                    )
            
            elif message_type == 0x80:  # Note Off
                note = midi_bytes[1]
                event = MIDIEvent(
                    type='note_off',
                    note=note,
                    channel=channel,
                    timestamp=current_time
                )
            
            elif message_type == 0xB0:  # Control Change
                control = midi_bytes[1]
                value = midi_bytes[2] if len(midi_bytes) > 2 else 0
                event = MIDIEvent(
                    type='control_change',
                    control=control,
                    value=value,
                    channel=channel,
                    timestamp=current_time
                )
            
            # Send event to callback if available
            if event and self.event_callback:
                with self._lock:
                    if self.event_callback:
                        self.event_callback(event)
                        
        except Exception as e:
            logger.error(f"Error processing MIDI message: {e}")
    
    def disconnect(self):
        """Disconnect from MIDI input"""
        if self.midi_in:
            try:
                self.midi_in.close_port()
                self.midi_in = None
            except Exception as e:
                logger.error(f"Error disconnecting MIDI: {e}")
        
        self.is_connected = False
        self.port_name = None
        logger.info("Disconnected from MIDI input")
    
    def simulate_note_on(self, note: int, velocity: int = 64, channel: int = 0):
        """Simulate a note on event (for testing)"""
        event = MIDIEvent(
            type='note_on',
            note=note,
            velocity=velocity,
            channel=channel,
            timestamp=time.time() * 1000
        )
        
        if self.event_callback:
            with self._lock:
                if self.event_callback:
                    self.event_callback(event)
    
    def simulate_note_off(self, note: int, channel: int = 0):
        """Simulate a note off event (for testing)"""
        event = MIDIEvent(
            type='note_off',
            note=note,
            channel=channel,
            timestamp=time.time() * 1000
        )
        
        if self.event_callback:
            with self._lock:
                if self.event_callback:
                    self.event_callback(event)

class WebSocketManager:
    """Manages WebSocket connections for real-time communication"""
    
    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.host = host
        self.port = port
        self.clients: Dict[WebSocketServerProtocol, Dict] = {}
        self.server = None
        self.is_running = False
        self._lock = Lock()
        
    async def register_client(self, websocket: WebSocketServerProtocol):
        """Register a new WebSocket client"""
        with self._lock:
            self.clients[websocket] = {
                'connected_at': time.time(),
                'messages_sent': 0,
                'last_ping': time.time()
            }
        
        logger.info(f"Client connected: {websocket.remote_address}")
        
        # Send connection confirmation
        await self.send_to_client(websocket, {
            'type': 'connection_established',
            'timestamp': time.time() * 1000,
            'server_info': {
                'version': '1.0.0',
                'features': ['midi_events', 'latency_tracking']
            }
        })
    
    async def unregister_client(self, websocket: WebSocketServerProtocol):
        """Unregister a WebSocket client"""
        with self._lock:
            if websocket in self.clients:
                del self.clients[websocket]
        
        logger.info(f"Client disconnected: {websocket.remote_address}")
    
    async def send_to_client(self, websocket: WebSocketServerProtocol, message: Dict):
        """Send message to specific client"""
        try:
            await websocket.send(json.dumps(message))
            
            with self._lock:
                if websocket in self.clients:
                    self.clients[websocket]['messages_sent'] += 1
                    
        except websockets.exceptions.ConnectionClosed:
            await self.unregister_client(websocket)
        except Exception as e:
            logger.error(f"Error sending message to client: {e}")
    
    async def broadcast_message(self, message: Dict):
        """Broadcast message to all connected clients"""
        if not self.clients:
            return
        
        # Create list of clients to avoid modification during iteration
        clients_list = list(self.clients.keys())
        
        # Send to all clients concurrently
        tasks = []
        for client in clients_list:
            tasks.append(self.send_to_client(client, message))
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
    
    async def handle_client_message(self, websocket: WebSocketServerProtocol, message: str):
        """Handle incoming message from client"""
        try:
            data = json.loads(message)
            message_type = data.get('type')
            
            if message_type == 'ping':
                # Respond to ping with pong
                await self.send_to_client(websocket, {
                    'type': 'pong',
                    'timestamp': time.time() * 1000,
                    'client_timestamp': data.get('timestamp')
                })
                
                with self._lock:
                    if websocket in self.clients:
                        self.clients[websocket]['last_ping'] = time.time()
            
            elif message_type == 'get_status':
                # Send server status
                await self.send_to_client(websocket, {
                    'type': 'status',
                    'timestamp': time.time() * 1000,
                    'connected_clients': len(self.clients),
                    'uptime': time.time() - (self.clients[websocket]['connected_at'] if websocket in self.clients else time.time())
                })
            
        except json.JSONDecodeError:
            logger.error(f"Invalid JSON received from client: {message}")
        except Exception as e:
            logger.error(f"Error handling client message: {e}")
    
    async def client_handler(self, websocket: WebSocketServerProtocol, path: str):
        """Handle WebSocket client connection"""
        await self.register_client(websocket)
        
        try:
            async for message in websocket:
                await self.handle_client_message(websocket, message)
        except websockets.exceptions.ConnectionClosed:
            pass
        except Exception as e:
            logger.error(f"Error in client handler: {e}")
        finally:
            await self.unregister_client(websocket)
    
    async def start_server(self):
        """Start the WebSocket server"""
        try:
            self.server = await websockets.serve(
                self.client_handler,
                self.host,
                self.port
            )
            self.is_running = True
            logger.info(f"WebSocket server started on {self.host}:{self.port}")
            
        except Exception as e:
            logger.error(f"Error starting WebSocket server: {e}")
            raise
    
    async def stop_server(self):
        """Stop the WebSocket server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.is_running = False
            logger.info("WebSocket server stopped")
    
    def get_client_count(self) -> int:
        """Get number of connected clients"""
        with self._lock:
            return len(self.clients)
    
    def get_client_stats(self) -> Dict:
        """Get statistics about connected clients"""
        with self._lock:
            stats = {
                'total_clients': len(self.clients),
                'clients': []
            }
            
            for websocket, info in self.clients.items():
                stats['clients'].append({
                    'address': str(websocket.remote_address),
                    'connected_at': info['connected_at'],
                    'messages_sent': info['messages_sent'],
                    'last_ping': info['last_ping']
                })
            
            return stats

class MIDIProcessor:
    """Main MIDI processor that coordinates MIDI input and WebSocket output"""
    
    def __init__(self, websocket_host: str = 'localhost', websocket_port: int = 8765):
        self.midi_handler = MIDIInputHandler()
        self.websocket_manager = WebSocketManager(websocket_host, websocket_port)
        self.is_running = False
        self.stats = {
            'events_processed': 0,
            'start_time': None,
            'last_event_time': None
        }
        
        # Set up MIDI event callback
        self.midi_handler.set_event_callback(self._handle_midi_event)
    
    def _handle_midi_event(self, event: MIDIEvent):
        """Handle MIDI event and broadcast to WebSocket clients"""
        try:
            # Update statistics
            self.stats['events_processed'] += 1
            self.stats['last_event_time'] = time.time()
            
            # Create message for WebSocket clients
            message = {
                'type': 'midi_event',
                'event': event.to_dict(),
                'server_timestamp': time.time() * 1000
            }
            
            # Broadcast to all connected clients
            asyncio.create_task(self.websocket_manager.broadcast_message(message))
            
            logger.debug(f"Processed MIDI event: {event.type} - Note: {event.note}")
            
        except Exception as e:
            logger.error(f"Error handling MIDI event: {e}")
    
    async def start(self, midi_port: Optional[str] = None):
        """Start the MIDI processor"""
        try:
            # Start WebSocket server
            await self.websocket_manager.start_server()
            
            # Connect to MIDI input
            if not self.midi_handler.connect(midi_port):
                logger.warning("Failed to connect to MIDI input, continuing with simulation mode")
            
            self.is_running = True
            self.stats['start_time'] = time.time()
            
            logger.info("MIDI Processor started successfully")
            
        except Exception as e:
            logger.error(f"Error starting MIDI processor: {e}")
            raise
    
    async def stop(self):
        """Stop the MIDI processor"""
        self.is_running = False
        
        # Disconnect MIDI input
        self.midi_handler.disconnect()
        
        # Stop WebSocket server
        await self.websocket_manager.stop_server()
        
        logger.info("MIDI Processor stopped")
    
    def get_status(self) -> Dict:
        """Get current status and statistics"""
        uptime = time.time() - self.stats['start_time'] if self.stats['start_time'] else 0
        
        return {
            'is_running': self.is_running,
            'midi_connected': self.midi_handler.is_connected,
            'midi_port': self.midi_handler.port_name,
            'websocket_clients': self.websocket_manager.get_client_count(),
            'events_processed': self.stats['events_processed'],
            'uptime': uptime,
            'last_event_time': self.stats['last_event_time'],
            'available_midi_ports': self.midi_handler.get_available_ports()
        }
    
    # Test methods
    def simulate_test_sequence(self):
        """Simulate a test sequence of MIDI events"""
        def run_sequence():
            # Play a C major scale
            notes = [60, 62, 64, 65, 67, 69, 71, 72]  # C4 to C5
            
            for note in notes:
                self.midi_handler.simulate_note_on(note, 80)
                time.sleep(0.2)
                self.midi_handler.simulate_note_off(note)
                time.sleep(0.1)
        
        # Run in separate thread to avoid blocking
        thread = Thread(target=run_sequence)
        thread.daemon = True
        thread.start()

# Main execution
async def main():
    """Main function for running the MIDI processor"""
    processor = MIDIProcessor()
    
    try:
        await processor.start()
        
        logger.info("MIDI Processor is running. Press Ctrl+C to stop.")
        
        # Keep running until interrupted
        while processor.is_running:
            await asyncio.sleep(1)
            
            # Print status every 30 seconds
            if int(time.time()) % 30 == 0:
                status = processor.get_status()
                logger.info(f"Status: {status['events_processed']} events processed, "
                          f"{status['websocket_clients']} clients connected")
    
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Error in main loop: {e}")
    finally:
        await processor.stop()

if __name__ == "__main__":
    asyncio.run(main())