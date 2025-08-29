#!/usr/bin/env python3
"""
Flask Web Server for Piano LED Visualizer
Integrates MIDI processing, LED control, and WebSocket communication
"""

import asyncio
import json
import logging
import os
import threading
import time
from typing import Dict, Any

from flask import Flask, render_template, jsonify, request, send_from_directory
from flask_cors import CORS
from flask_socketio import SocketIO, emit

# Import our custom modules
from midi_processor import MIDIProcessor, MIDIEvent
from led_controller import LEDController, LEDConfig

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Flask app configuration
app = Flask(__name__, static_folder='../webinterface', static_url_path='/static')
app.config['SECRET_KEY'] = 'piano-led-visualizer-secret-key'
CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# Global components
midi_processor = None
led_controller = None
app_status = {
    'initialized': False,
    'midi_connected': False,
    'led_initialized': False,
    'websocket_clients': 0,
    'start_time': time.time()
}

# Configuration
CONFIG = {
    'midi': {
        'websocket_host': 'localhost',
        'websocket_port': 8765
    },
    'led': {
        'num_leds': 88,
        'pin': 18,
        'brightness': 0.8,
        'default_scheme': 'velocity'
    },
    'web': {
        'host': '0.0.0.0',
        'port': 5000,
        'debug': False
    }
}

def load_config():
    """Load configuration from file if available"""
    config_file = os.path.join(os.path.dirname(__file__), 'config.json')
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r') as f:
                file_config = json.load(f)
                CONFIG.update(file_config)
                logger.info(f"Configuration loaded from {config_file}")
        except Exception as e:
            logger.error(f"Error loading config file: {e}")

async def initialize_components():
    """Initialize MIDI processor and LED controller"""
    global midi_processor, led_controller, app_status
    
    try:
        # Initialize LED controller
        led_config = LEDConfig(
            num_leds=CONFIG['led']['num_leds'],
            pin=CONFIG['led']['pin'],
            brightness=CONFIG['led']['brightness']
        )
        
        led_controller = LEDController(led_config)
        if led_controller.initialize():
            led_controller.set_color_scheme(CONFIG['led']['default_scheme'])
            app_status['led_initialized'] = True
            logger.info("LED controller initialized")
        else:
            logger.error("Failed to initialize LED controller")
        
        # Initialize MIDI processor
        midi_processor = MIDIProcessor(
            websocket_host=CONFIG['midi']['websocket_host'],
            websocket_port=CONFIG['midi']['websocket_port']
        )
        
        # Set up MIDI event handlers
        midi_processor.midi_handler.set_event_callback(handle_midi_event)
        
        # Start MIDI processor
        await midi_processor.start()
        app_status['midi_connected'] = midi_processor.midi_handler.is_connected
        app_status['initialized'] = True
        
        logger.info("All components initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing components: {e}")
        app_status['initialized'] = False

def handle_midi_event(event: MIDIEvent):
    """Handle MIDI events and update LEDs"""
    try:
        if led_controller and led_controller.is_initialized:
            if event.type == 'note_on' and event.note is not None:
                led_controller.note_on(event.note, event.velocity or 64)
            elif event.type == 'note_off' and event.note is not None:
                led_controller.note_off(event.note)
        
        # Emit to web clients via SocketIO
        socketio.emit('midi_event', {
            'type': event.type,
            'note': event.note,
            'velocity': event.velocity,
            'timestamp': event.timestamp
        })
        
    except Exception as e:
        logger.error(f"Error handling MIDI event: {e}")

# Web Routes
@app.route('/')
def index():
    """Main page"""
    return send_from_directory('../webinterface', 'index.html')

@app.route('/piano-3d.html')
def piano_3d_direct():
    """Serve 3D piano visualization directly"""
    return send_from_directory('../webinterface/enhanced', 'piano-3d.html')

@app.route('/js/<path:filename>')
def serve_js(filename):
    """Serve JavaScript files"""
    return send_from_directory('../webinterface/enhanced/js', filename)

@app.route('/3d')
def piano_3d():
    """3D Piano visualization page"""
    return send_from_directory('../webinterface/enhanced', 'piano-3d.html')

@app.route('/api/status')
def get_status():
    """Get system status"""
    status = app_status.copy()
    
    if midi_processor:
        midi_status = midi_processor.get_status()
        status.update({
            'midi_processor': midi_status,
            'midi_connected': midi_status['midi_connected'],
            'websocket_clients': midi_status['websocket_clients']
        })
    
    if led_controller:
        led_status = led_controller.get_status()
        status.update({
            'led_controller': led_status,
            'led_initialized': led_status['is_initialized']
        })
    
    status['uptime'] = time.time() - status['start_time']
    
    return jsonify(status)

@app.route('/api/midi/ports')
def get_midi_ports():
    """Get available MIDI ports"""
    if midi_processor:
        ports = midi_processor.midi_handler.get_available_ports()
        return jsonify({'ports': ports})
    return jsonify({'ports': []})

@app.route('/api/midi/connect', methods=['POST'])
def connect_midi():
    """Connect to MIDI port"""
    data = request.get_json()
    port_name = data.get('port_name')
    
    if midi_processor:
        success = midi_processor.midi_handler.connect(port_name)
        app_status['midi_connected'] = success
        return jsonify({'success': success, 'port': port_name})
    
    return jsonify({'success': False, 'error': 'MIDI processor not initialized'})

@app.route('/api/midi/disconnect', methods=['POST'])
def disconnect_midi():
    """Disconnect from MIDI port"""
    if midi_processor:
        midi_processor.midi_handler.disconnect()
        app_status['midi_connected'] = False
        return jsonify({'success': True})
    
    return jsonify({'success': False, 'error': 'MIDI processor not initialized'})

@app.route('/api/midi/test', methods=['POST'])
def test_midi():
    """Test MIDI with a sequence"""
    if midi_processor:
        midi_processor.simulate_test_sequence()
        return jsonify({'success': True, 'message': 'Test sequence started'})
    
    return jsonify({'success': False, 'error': 'MIDI processor not initialized'})

@app.route('/api/led/brightness', methods=['POST'])
def set_led_brightness():
    """Set LED brightness"""
    data = request.get_json()
    brightness = data.get('brightness', 0.8)
    
    if led_controller:
        led_controller.set_brightness(float(brightness))
        return jsonify({'success': True, 'brightness': brightness})
    
    return jsonify({'success': False, 'error': 'LED controller not initialized'})

@app.route('/api/led/color-scheme', methods=['POST'])
def set_color_scheme():
    """Set LED color scheme"""
    data = request.get_json()
    scheme = data.get('scheme')
    
    if led_controller:
        success = led_controller.set_color_scheme(scheme)
        return jsonify({'success': success, 'scheme': scheme})
    
    return jsonify({'success': False, 'error': 'LED controller not initialized'})

@app.route('/api/led/schemes')
def get_color_schemes():
    """Get available color schemes"""
    if led_controller:
        schemes = led_controller.color_manager.get_available_schemes()
        current = led_controller.color_manager.current_scheme
        return jsonify({'schemes': schemes, 'current': current})
    
    return jsonify({'schemes': [], 'current': None})

@app.route('/api/led/test', methods=['POST'])
def test_leds():
    """Test LED strip"""
    if led_controller:
        led_controller.test_sequence()
        return jsonify({'success': True, 'message': 'LED test sequence started'})
    
    return jsonify({'success': False, 'error': 'LED controller not initialized'})

@app.route('/api/led/clear', methods=['POST'])
def clear_leds():
    """Clear all LEDs"""
    if led_controller:
        led_controller.clear_all()
        return jsonify({'success': True, 'message': 'All LEDs cleared'})
    
    return jsonify({'success': False, 'error': 'LED controller not initialized'})

@app.route('/api/simulate/note', methods=['POST'])
def simulate_note():
    """Simulate a MIDI note for testing"""
    data = request.get_json()
    note = data.get('note', 60)
    velocity = data.get('velocity', 64)
    duration = data.get('duration', 0.5)
    
    if midi_processor:
        # Simulate note on
        midi_processor.midi_handler.simulate_note_on(note, velocity)
        
        # Schedule note off
        def note_off_delayed():
            time.sleep(duration)
            midi_processor.midi_handler.simulate_note_off(note)
        
        threading.Thread(target=note_off_delayed, daemon=True).start()
        
        return jsonify({
            'success': True, 
            'note': note, 
            'velocity': velocity, 
            'duration': duration
        })
    
    return jsonify({'success': False, 'error': 'MIDI processor not initialized'})

# Static file serving
@app.route('/webinterface/<path:filename>')
def serve_webinterface(filename):
    """Serve web interface files"""
    return send_from_directory('../webinterface', filename)

@app.route('/webinterface/enhanced/<path:filename>')
def serve_enhanced(filename):
    """Serve enhanced web interface files"""
    return send_from_directory('../webinterface/enhanced', filename)

@app.route('/webinterface/enhanced/js/<path:filename>')
def serve_enhanced_js(filename):
    """Serve enhanced JavaScript files"""
    return send_from_directory('../webinterface/enhanced/js', filename)

# SocketIO Events
@socketio.on('connect')
def handle_connect():
    """Handle client connection"""
    app_status['websocket_clients'] += 1
    logger.info(f"Client connected. Total clients: {app_status['websocket_clients']}")
    
    # Send current status to new client
    emit('status_update', get_status().get_json())

@socketio.on('disconnect')
def handle_disconnect():
    """Handle client disconnection"""
    app_status['websocket_clients'] = max(0, app_status['websocket_clients'] - 1)
    logger.info(f"Client disconnected. Total clients: {app_status['websocket_clients']}")

@socketio.on('request_status')
def handle_status_request():
    """Handle status request from client"""
    emit('status_update', get_status().get_json())

@socketio.on('simulate_note')
def handle_simulate_note(data):
    """Handle note simulation request from client"""
    note = data.get('note', 60)
    velocity = data.get('velocity', 64)
    
    if midi_processor:
        midi_processor.midi_handler.simulate_note_on(note, velocity)
        
        # Auto note-off after 500ms
        def auto_note_off():
            time.sleep(0.5)
            midi_processor.midi_handler.simulate_note_off(note)
        
        threading.Thread(target=auto_note_off, daemon=True).start()

# Background tasks
def led_update_loop():
    """Background loop to update LED display"""
    while True:
        try:
            if led_controller and led_controller.is_initialized:
                led_controller.update_display()
            time.sleep(0.016)  # ~60 FPS
        except Exception as e:
            logger.error(f"Error in LED update loop: {e}")
            time.sleep(1.0)

def status_broadcast_loop():
    """Background loop to broadcast status updates"""
    while True:
        try:
            if app_status['websocket_clients'] > 0:
                status = get_status().get_json()
                socketio.emit('status_update', status)
            time.sleep(5.0)  # Broadcast every 5 seconds
        except Exception as e:
            logger.error(f"Error in status broadcast loop: {e}")
            time.sleep(5.0)

# Startup and shutdown
def startup():
    """Application startup"""
    logger.info("Starting Piano LED Visualizer server...")
    
    # Load configuration
    load_config()
    
    # Initialize components in a separate thread
    def init_components():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(initialize_components())
    
    init_thread = threading.Thread(target=init_components, daemon=True)
    init_thread.start()
    
    # Start background tasks
    led_thread = threading.Thread(target=led_update_loop, daemon=True)
    led_thread.start()
    
    status_thread = threading.Thread(target=status_broadcast_loop, daemon=True)
    status_thread.start()
    
    logger.info(f"Server starting on {CONFIG['web']['host']}:{CONFIG['web']['port']}")

def shutdown():
    """Application shutdown"""
    logger.info("Shutting down Piano LED Visualizer server...")
    
    if led_controller:
        led_controller.shutdown()
    
    if midi_processor:
        # Note: This needs to be run in an async context
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(midi_processor.stop())
        except Exception as e:
            logger.error(f"Error stopping MIDI processor: {e}")

# Error handlers
@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Not found'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Internal server error'}), 500

if __name__ == '__main__':
    try:
        startup()
        
        # Run the Flask-SocketIO server
        socketio.run(
            app,
            host=CONFIG['web']['host'],
            port=CONFIG['web']['port'],
            debug=CONFIG['web']['debug'],
            use_reloader=False  # Disable reloader to avoid double initialization
        )
        
    except KeyboardInterrupt:
        logger.info("Received interrupt signal")
    except Exception as e:
        logger.error(f"Error running server: {e}")
    finally:
        shutdown()