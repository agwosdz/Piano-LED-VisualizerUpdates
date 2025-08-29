#!/usr/bin/env python3
"""
Basic tests for Piano LED Visualizer components
"""

import pytest
import asyncio
import json
import time
from unittest.mock import Mock, patch, MagicMock

# Import components to test
from midi_processor import MIDIEvent, MIDIInputHandler, WebSocketManager, MIDIProcessor
from led_controller import LEDCommand, LEDConfig, ColorManager, LEDAnimator, LEDController

class TestMIDIEvent:
    """Test MIDI Event data structure"""
    
    def test_midi_event_creation(self):
        """Test creating MIDI events"""
        event = MIDIEvent(
            type='note_on',
            note=60,
            velocity=64,
            timestamp=time.time()
        )
        
        assert event.type == 'note_on'
        assert event.note == 60
        assert event.velocity == 64
        assert isinstance(event.timestamp, float)
    
    def test_midi_event_to_dict(self):
        """Test converting MIDI event to dictionary"""
        timestamp = time.time()
        event = MIDIEvent(
            type='note_off',
            note=72,
            velocity=0,
            timestamp=timestamp
        )
        
        event_dict = event.to_dict()
        
        assert event_dict['type'] == 'note_off'
        assert event_dict['note'] == 72
        assert event_dict['velocity'] == 0
        assert event_dict['timestamp'] == timestamp

class TestLEDCommand:
    """Test LED Command data structure"""
    
    def test_led_command_creation(self):
        """Test creating LED commands"""
        command = LEDCommand(
            led_index=10,
            color=(255, 128, 0),
            brightness=0.8,
            fade_time=0.5
        )
        
        assert command.led_index == 10
        assert command.color == (255, 128, 0)
        assert command.brightness == 0.8
        assert command.fade_time == 0.5
    
    def test_led_command_to_dict(self):
        """Test converting LED command to dictionary"""
        command = LEDCommand(
            led_index=5,
            color=(0, 255, 255),
            brightness=1.0,
            fade_time=0.2
        )
        
        command_dict = command.to_dict()
        
        assert command_dict['led_index'] == 5
        assert command_dict['color'] == (0, 255, 255)
        assert command_dict['brightness'] == 1.0
        assert command_dict['fade_time'] == 0.2

class TestLEDConfig:
    """Test LED Configuration"""
    
    def test_led_config_creation(self):
        """Test creating LED configuration"""
        config = LEDConfig(
            num_leds=88,
            pin=18,
            brightness=0.7
        )
        
        assert config.num_leds == 88
        assert config.pin == 18
        assert config.brightness == 0.7
    
    def test_led_config_validation(self):
        """Test LED configuration validation"""
        # Valid config
        config = LEDConfig(num_leds=88, pin=18, brightness=0.5)
        assert config.is_valid()
        
        # Invalid configs
        invalid_config1 = LEDConfig(num_leds=0, pin=18, brightness=0.5)
        assert not invalid_config1.is_valid()
        
        invalid_config2 = LEDConfig(num_leds=88, pin=18, brightness=1.5)
        assert not invalid_config2.is_valid()

class TestColorManager:
    """Test Color Manager"""
    
    def test_color_manager_creation(self):
        """Test creating color manager"""
        manager = ColorManager()
        
        assert manager.current_scheme == 'velocity'
        assert len(manager.get_available_schemes()) > 0
    
    def test_color_schemes(self):
        """Test different color schemes"""
        manager = ColorManager()
        
        # Test velocity scheme
        manager.set_scheme('velocity')
        color = manager.get_color(60, 64)
        assert isinstance(color, tuple)
        assert len(color) == 3
        assert all(0 <= c <= 255 for c in color)
        
        # Test rainbow scheme
        manager.set_scheme('rainbow')
        color = manager.get_color(60, 64)
        assert isinstance(color, tuple)
        assert len(color) == 3
        
        # Test note-based scheme
        manager.set_scheme('note_based')
        color = manager.get_color(60, 64)
        assert isinstance(color, tuple)
        assert len(color) == 3

class TestLEDAnimator:
    """Test LED Animator"""
    
    def test_led_animator_creation(self):
        """Test creating LED animator"""
        animator = LEDAnimator()
        
        assert len(animator.active_animations) == 0
    
    def test_fade_animation(self):
        """Test fade animation"""
        animator = LEDAnimator()
        
        # Start fade animation
        animator.start_fade_out(led_index=10, start_color=(255, 0, 0), fade_time=1.0)
        
        assert len(animator.active_animations) == 1
        assert 10 in animator.active_animations
        
        # Update animation
        current_colors = animator.update()
        assert isinstance(current_colors, dict)
        
        # Clear animations
        animator.clear_animation(10)
        assert len(animator.active_animations) == 0

@patch('led_controller.neopixel')  # Mock the neopixel library
class TestLEDController:
    """Test LED Controller"""
    
    def test_led_controller_creation(self, mock_neopixel):
        """Test creating LED controller"""
        config = LEDConfig(num_leds=88, pin=18, brightness=0.8)
        controller = LEDController(config)
        
        assert controller.config == config
        assert not controller.is_initialized
    
    def test_led_controller_initialization(self, mock_neopixel):
        """Test LED controller initialization"""
        # Mock the neopixel.NeoPixel class
        mock_strip = Mock()
        mock_neopixel.NeoPixel.return_value = mock_strip
        
        config = LEDConfig(num_leds=88, pin=18, brightness=0.8)
        controller = LEDController(config)
        
        # Initialize should succeed with mocked hardware
        result = controller.initialize()
        assert result is True
        assert controller.is_initialized
    
    def test_note_on_off(self, mock_neopixel):
        """Test note on/off functionality"""
        mock_strip = Mock()
        mock_neopixel.NeoPixel.return_value = mock_strip
        
        config = LEDConfig(num_leds=88, pin=18, brightness=0.8)
        controller = LEDController(config)
        controller.initialize()
        
        # Test note on
        controller.note_on(60, 64)
        assert 60 in controller.active_notes
        
        # Test note off
        controller.note_off(60)
        assert 60 not in controller.active_notes

class TestMIDIInputHandler:
    """Test MIDI Input Handler"""
    
    @patch('midi_processor.rtmidi')
    def test_midi_handler_creation(self, mock_rtmidi):
        """Test creating MIDI input handler"""
        handler = MIDIInputHandler()
        
        assert not handler.is_connected
        assert handler.connected_port is None
    
    @patch('midi_processor.rtmidi')
    def test_midi_port_listing(self, mock_rtmidi):
        """Test listing MIDI ports"""
        # Mock rtmidi
        mock_midi_in = Mock()
        mock_midi_in.get_ports.return_value = ['Port 1', 'Port 2', 'Port 3']
        mock_rtmidi.MidiIn.return_value = mock_midi_in
        
        handler = MIDIInputHandler()
        ports = handler.get_available_ports()
        
        assert len(ports) == 3
        assert 'Port 1' in ports

class TestWebSocketManager:
    """Test WebSocket Manager"""
    
    def test_websocket_manager_creation(self):
        """Test creating WebSocket manager"""
        manager = WebSocketManager('localhost', 8765)
        
        assert manager.host == 'localhost'
        assert manager.port == 8765
        assert not manager.is_running
    
    @pytest.mark.asyncio
    async def test_websocket_message_handling(self):
        """Test WebSocket message handling"""
        manager = WebSocketManager('localhost', 8765)
        
        # Test message creation
        event = MIDIEvent('note_on', 60, 64, time.time())
        message = manager.create_message(event)
        
        assert isinstance(message, str)
        data = json.loads(message)
        assert data['type'] == 'note_on'
        assert data['note'] == 60

class TestMIDIProcessor:
    """Test MIDI Processor integration"""
    
    @patch('midi_processor.rtmidi')
    def test_midi_processor_creation(self, mock_rtmidi):
        """Test creating MIDI processor"""
        processor = MIDIProcessor('localhost', 8765)
        
        assert processor.websocket_manager.host == 'localhost'
        assert processor.websocket_manager.port == 8765
    
    @patch('midi_processor.rtmidi')
    def test_midi_processor_status(self, mock_rtmidi):
        """Test MIDI processor status"""
        processor = MIDIProcessor('localhost', 8765)
        status = processor.get_status()
        
        assert 'midi_connected' in status
        assert 'websocket_clients' in status
        assert 'uptime' in status

class TestIntegration:
    """Integration tests"""
    
    def test_midi_to_led_flow(self):
        """Test the flow from MIDI event to LED command"""
        # Create MIDI event
        midi_event = MIDIEvent('note_on', 60, 64, time.time())
        
        # Create color manager
        color_manager = ColorManager()
        color_manager.set_scheme('velocity')
        
        # Get color for note
        color = color_manager.get_color(midi_event.note, midi_event.velocity)
        
        # Create LED command
        led_command = LEDCommand(
            led_index=midi_event.note - 21,  # Piano note to LED mapping
            color=color,
            brightness=0.8,
            fade_time=0.1
        )
        
        assert led_command.led_index == 39  # 60 - 21
        assert isinstance(led_command.color, tuple)
        assert len(led_command.color) == 3
    
    def test_performance_timing(self):
        """Test performance timing requirements"""
        start_time = time.time()
        
        # Simulate processing 100 MIDI events
        color_manager = ColorManager()
        for i in range(100):
            note = 21 + (i % 88)  # Cycle through piano keys
            velocity = 64
            color = color_manager.get_color(note, velocity)
            
            # Verify color is valid
            assert isinstance(color, tuple)
            assert len(color) == 3
        
        end_time = time.time()
        processing_time = end_time - start_time
        
        # Should process 100 events in less than 100ms (1ms per event)
        assert processing_time < 0.1, f"Processing took {processing_time:.3f}s, should be < 0.1s"

if __name__ == '__main__':
    # Run tests
    pytest.main([__file__, '-v'])