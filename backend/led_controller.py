#!/usr/bin/env python3
"""
LED Controller for Piano LED Visualizer
Handles LED strip control and synchronization with MIDI events
"""

import time
import logging
import asyncio
import json
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass
from threading import Thread, Lock
import colorsys

try:
    import RPi.GPIO as GPIO
    import board
    import neopixel
    RASPBERRY_PI = True
except ImportError:
    RASPBERRY_PI = False
    logging.warning("Raspberry Pi libraries not available - LED output will be simulated")

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class LEDCommand:
    """LED command data structure"""
    led_index: int
    color: Tuple[int, int, int]  # RGB values (0-255)
    brightness: float = 1.0  # 0.0 to 1.0
    fade_time: float = 0.0  # seconds
    timestamp: float = 0.0

@dataclass
class LEDConfig:
    """LED strip configuration"""
    num_leds: int = 88  # Standard piano has 88 keys
    pin: int = 18  # GPIO pin for LED data
    brightness: float = 0.8  # Global brightness (0.0 to 1.0)
    auto_write: bool = False
    pixel_order: str = "GRB"  # Color order for LED strip
    
class ColorManager:
    """Manages color schemes and mappings for piano keys"""
    
    def __init__(self):
        self.color_schemes = {
            'rainbow': self._rainbow_scheme,
            'velocity': self._velocity_scheme,
            'note_based': self._note_based_scheme,
            'white_keys': self._white_keys_scheme,
            'fire': self._fire_scheme,
            'ocean': self._ocean_scheme
        }
        self.current_scheme = 'velocity'
        
    def _rainbow_scheme(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """Rainbow color scheme based on note position"""
        # Map note (21-108) to hue (0-1)
        hue = (note - 21) / 87
        saturation = 1.0
        value = velocity / 127.0
        
        rgb = colorsys.hsv_to_rgb(hue, saturation, value)
        return tuple(int(c * 255) for c in rgb)
    
    def _velocity_scheme(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """Color based on velocity (soft blue to bright red)"""
        # Interpolate between blue (low velocity) and red (high velocity)
        velocity_norm = velocity / 127.0
        
        if velocity_norm < 0.5:
            # Blue to cyan
            factor = velocity_norm * 2
            r = 0
            g = int(factor * 255)
            b = 255
        else:
            # Cyan to red
            factor = (velocity_norm - 0.5) * 2
            r = int(factor * 255)
            g = int((1 - factor) * 255)
            b = int((1 - factor) * 255)
        
        return (r, g, b)
    
    def _note_based_scheme(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """Color based on note (C=red, D=orange, E=yellow, etc.)"""
        note_colors = {
            0: (255, 0, 0),    # C - Red
            1: (255, 127, 0),  # C# - Red-Orange
            2: (255, 165, 0),  # D - Orange
            3: (255, 215, 0),  # D# - Gold
            4: (255, 255, 0),  # E - Yellow
            5: (127, 255, 0),  # F - Yellow-Green
            6: (0, 255, 0),    # F# - Green
            7: (0, 255, 127),  # G - Green-Cyan
            8: (0, 255, 255),  # G# - Cyan
            9: (0, 127, 255),  # A - Light Blue
            10: (0, 0, 255),   # A# - Blue
            11: (127, 0, 255)  # B - Blue-Purple
        }
        
        note_class = note % 12
        base_color = note_colors[note_class]
        
        # Scale by velocity
        velocity_factor = velocity / 127.0
        return tuple(int(c * velocity_factor) for c in base_color)
    
    def _white_keys_scheme(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """White for white keys, blue for black keys"""
        # Black keys in each octave: C#, D#, F#, G#, A#
        black_keys = {1, 3, 6, 8, 10}
        note_class = note % 12
        
        velocity_factor = velocity / 127.0
        
        if note_class in black_keys:
            # Black keys - blue
            return (0, 0, int(255 * velocity_factor))
        else:
            # White keys - white
            intensity = int(255 * velocity_factor)
            return (intensity, intensity, intensity)
    
    def _fire_scheme(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """Fire-like colors (red, orange, yellow)"""
        velocity_norm = velocity / 127.0
        
        if velocity_norm < 0.3:
            # Dark red
            return (int(139 * velocity_norm / 0.3), 0, 0)
        elif velocity_norm < 0.7:
            # Red to orange
            factor = (velocity_norm - 0.3) / 0.4
            return (255, int(165 * factor), 0)
        else:
            # Orange to yellow
            factor = (velocity_norm - 0.7) / 0.3
            return (255, int(165 + 90 * factor), int(255 * factor))
    
    def _ocean_scheme(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """Ocean-like colors (blue, cyan, white)"""
        velocity_norm = velocity / 127.0
        
        if velocity_norm < 0.4:
            # Dark blue
            intensity = velocity_norm / 0.4
            return (0, 0, int(139 * intensity))
        elif velocity_norm < 0.8:
            # Blue to cyan
            factor = (velocity_norm - 0.4) / 0.4
            return (0, int(255 * factor), 255)
        else:
            # Cyan to white
            factor = (velocity_norm - 0.8) / 0.2
            blue_green = int(255 - 55 * factor)
            return (int(255 * factor), blue_green, blue_green)
    
    def get_color(self, note: int, velocity: int) -> Tuple[int, int, int]:
        """Get color for note using current scheme"""
        if self.current_scheme in self.color_schemes:
            return self.color_schemes[self.current_scheme](note, velocity)
        else:
            return self._velocity_scheme(note, velocity)
    
    def set_scheme(self, scheme_name: str) -> bool:
        """Set current color scheme"""
        if scheme_name in self.color_schemes:
            self.current_scheme = scheme_name
            logger.info(f"Color scheme changed to: {scheme_name}")
            return True
        return False
    
    def get_available_schemes(self) -> List[str]:
        """Get list of available color schemes"""
        return list(self.color_schemes.keys())

class LEDAnimator:
    """Handles LED animations and transitions"""
    
    def __init__(self):
        self.active_animations = {}  # note -> animation_data
        self.animation_thread = None
        self.is_running = False
        self._lock = Lock()
        
    def start(self):
        """Start animation thread"""
        if not self.is_running:
            self.is_running = True
            self.animation_thread = Thread(target=self._animation_loop, daemon=True)
            self.animation_thread.start()
    
    def stop(self):
        """Stop animation thread"""
        self.is_running = False
        if self.animation_thread:
            self.animation_thread.join(timeout=1.0)
    
    def add_fade_out(self, note: int, led_index: int, initial_color: Tuple[int, int, int], 
                     fade_time: float = 0.5):
        """Add fade-out animation for a note"""
        with self._lock:
            self.active_animations[note] = {
                'type': 'fade_out',
                'led_index': led_index,
                'start_color': initial_color,
                'start_time': time.time(),
                'duration': fade_time
            }
    
    def remove_animation(self, note: int):
        """Remove animation for a note"""
        with self._lock:
            if note in self.active_animations:
                del self.active_animations[note]
    
    def get_current_colors(self) -> Dict[int, Tuple[int, int, int]]:
        """Get current colors for all animated LEDs"""
        current_colors = {}
        current_time = time.time()
        
        with self._lock:
            animations_to_remove = []
            
            for note, anim_data in self.active_animations.items():
                if anim_data['type'] == 'fade_out':
                    elapsed = current_time - anim_data['start_time']
                    progress = elapsed / anim_data['duration']
                    
                    if progress >= 1.0:
                        # Animation complete
                        animations_to_remove.append(note)
                        current_colors[anim_data['led_index']] = (0, 0, 0)
                    else:
                        # Calculate faded color
                        factor = 1.0 - progress
                        start_color = anim_data['start_color']
                        faded_color = tuple(int(c * factor) for c in start_color)
                        current_colors[anim_data['led_index']] = faded_color
            
            # Remove completed animations
            for note in animations_to_remove:
                del self.active_animations[note]
        
        return current_colors
    
    def _animation_loop(self):
        """Main animation loop"""
        while self.is_running:
            time.sleep(0.016)  # ~60 FPS
            # Animation updates are handled by get_current_colors()

class LEDController:
    """Main LED controller class"""
    
    def __init__(self, config: LEDConfig = None):
        self.config = config or LEDConfig()
        self.pixels = None
        self.is_initialized = False
        self.color_manager = ColorManager()
        self.animator = LEDAnimator()
        self.note_to_led_map = self._create_note_to_led_mapping()
        self.current_led_state = [(0, 0, 0)] * self.config.num_leds
        self._lock = Lock()
        
        # Performance tracking
        self.stats = {
            'commands_processed': 0,
            'last_update_time': 0,
            'update_frequency': 0
        }
    
    def _create_note_to_led_mapping(self) -> Dict[int, int]:
        """Create mapping from MIDI note numbers to LED indices"""
        # Standard piano: A0 (21) to C8 (108) = 88 keys
        # Map linearly to LED indices 0-87
        mapping = {}
        for i, note in enumerate(range(21, 109)):  # MIDI notes 21-108
            if i < self.config.num_leds:
                mapping[note] = i
        return mapping
    
    def initialize(self) -> bool:
        """Initialize LED controller"""
        try:
            if RASPBERRY_PI:
                # Initialize NeoPixel strip
                self.pixels = neopixel.NeoPixel(
                    getattr(board, f'D{self.config.pin}'),
                    self.config.num_leds,
                    brightness=self.config.brightness,
                    auto_write=self.config.auto_write,
                    pixel_order=getattr(neopixel, self.config.pixel_order)
                )
                logger.info(f"Initialized NeoPixel strip: {self.config.num_leds} LEDs on pin {self.config.pin}")
            else:
                logger.info("Running in simulation mode - LED output will be logged")
            
            # Start animator
            self.animator.start()
            
            # Clear all LEDs
            self.clear_all()
            
            self.is_initialized = True
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize LED controller: {e}")
            return False
    
    def shutdown(self):
        """Shutdown LED controller"""
        self.animator.stop()
        self.clear_all()
        
        if RASPBERRY_PI and self.pixels:
            self.pixels.deinit()
        
        self.is_initialized = False
        logger.info("LED controller shutdown")
    
    def note_on(self, note: int, velocity: int) -> bool:
        """Handle note on event"""
        if not self.is_initialized:
            return False
        
        if note not in self.note_to_led_map:
            return False
        
        led_index = self.note_to_led_map[note]
        color = self.color_manager.get_color(note, velocity)
        
        # Remove any existing animation for this note
        self.animator.remove_animation(note)
        
        # Set LED color immediately
        self._set_led_color(led_index, color)
        
        self.stats['commands_processed'] += 1
        logger.debug(f"Note ON: {note} -> LED {led_index} -> Color {color}")
        
        return True
    
    def note_off(self, note: int, fade_time: float = 0.5) -> bool:
        """Handle note off event"""
        if not self.is_initialized:
            return False
        
        if note not in self.note_to_led_map:
            return False
        
        led_index = self.note_to_led_map[note]
        current_color = self.current_led_state[led_index]
        
        if fade_time > 0:
            # Start fade-out animation
            self.animator.add_fade_out(note, led_index, current_color, fade_time)
        else:
            # Turn off immediately
            self._set_led_color(led_index, (0, 0, 0))
        
        self.stats['commands_processed'] += 1
        logger.debug(f"Note OFF: {note} -> LED {led_index} (fade: {fade_time}s)")
        
        return True
    
    def _set_led_color(self, led_index: int, color: Tuple[int, int, int]):
        """Set color for specific LED"""
        if led_index < 0 or led_index >= self.config.num_leds:
            return
        
        with self._lock:
            self.current_led_state[led_index] = color
            
            if RASPBERRY_PI and self.pixels:
                self.pixels[led_index] = color
                if self.config.auto_write:
                    self.pixels.show()
            else:
                # Simulation mode - log color changes
                if any(c > 0 for c in color):
                    logger.debug(f"LED {led_index}: RGB{color}")
    
    def update_display(self):
        """Update LED display with current state and animations"""
        if not self.is_initialized:
            return
        
        # Get animated colors
        animated_colors = self.animator.get_current_colors()
        
        # Update LEDs with animated colors
        with self._lock:
            for led_index, color in animated_colors.items():
                if led_index < self.config.num_leds:
                    self.current_led_state[led_index] = color
                    
                    if RASPBERRY_PI and self.pixels:
                        self.pixels[led_index] = color
            
            # Show all changes at once
            if RASPBERRY_PI and self.pixels and not self.config.auto_write:
                self.pixels.show()
        
        # Update performance stats
        current_time = time.time()
        if self.stats['last_update_time'] > 0:
            time_diff = current_time - self.stats['last_update_time']
            if time_diff > 0:
                self.stats['update_frequency'] = 1.0 / time_diff
        
        self.stats['last_update_time'] = current_time
    
    def clear_all(self):
        """Clear all LEDs"""
        with self._lock:
            for i in range(self.config.num_leds):
                self.current_led_state[i] = (0, 0, 0)
                
                if RASPBERRY_PI and self.pixels:
                    self.pixels[i] = (0, 0, 0)
            
            if RASPBERRY_PI and self.pixels:
                self.pixels.show()
        
        logger.info("All LEDs cleared")
    
    def set_brightness(self, brightness: float):
        """Set global brightness (0.0 to 1.0)"""
        brightness = max(0.0, min(1.0, brightness))
        self.config.brightness = brightness
        
        if RASPBERRY_PI and self.pixels:
            self.pixels.brightness = brightness
        
        logger.info(f"Brightness set to {brightness:.2f}")
    
    def set_color_scheme(self, scheme_name: str) -> bool:
        """Set color scheme"""
        return self.color_manager.set_scheme(scheme_name)
    
    def test_sequence(self):
        """Run a test sequence"""
        logger.info("Starting LED test sequence")
        
        def run_test():
            # Test each LED with rainbow colors
            for i in range(self.config.num_leds):
                hue = i / self.config.num_leds
                rgb = colorsys.hsv_to_rgb(hue, 1.0, 1.0)
                color = tuple(int(c * 255) for c in rgb)
                
                self._set_led_color(i, color)
                time.sleep(0.05)
            
            time.sleep(1.0)
            
            # Clear all
            self.clear_all()
        
        # Run in separate thread
        test_thread = Thread(target=run_test, daemon=True)
        test_thread.start()
    
    def get_status(self) -> Dict:
        """Get controller status"""
        return {
            'is_initialized': self.is_initialized,
            'num_leds': self.config.num_leds,
            'brightness': self.config.brightness,
            'color_scheme': self.color_manager.current_scheme,
            'available_schemes': self.color_manager.get_available_schemes(),
            'raspberry_pi_mode': RASPBERRY_PI,
            'stats': self.stats.copy(),
            'active_animations': len(self.animator.active_animations)
        }

# Main execution for testing
if __name__ == "__main__":
    # Test the LED controller
    config = LEDConfig(num_leds=88, brightness=0.5)
    controller = LEDController(config)
    
    if controller.initialize():
        logger.info("LED Controller initialized successfully")
        
        # Run test sequence
        controller.test_sequence()
        
        # Simulate some note events
        time.sleep(2)
        
        # Test note events
        controller.note_on(60, 80)  # Middle C
        time.sleep(0.5)
        controller.note_on(64, 100)  # E
        time.sleep(0.5)
        controller.note_on(67, 120)  # G
        time.sleep(1.0)
        
        controller.note_off(60)
        controller.note_off(64)
        controller.note_off(67)
        
        time.sleep(2)
        
        # Test different color schemes
        for scheme in controller.color_manager.get_available_schemes():
            logger.info(f"Testing color scheme: {scheme}")
            controller.set_color_scheme(scheme)
            
            controller.note_on(60, 80)
            time.sleep(0.3)
            controller.note_off(60)
            time.sleep(0.7)
        
        time.sleep(2)
        controller.shutdown()
    else:
        logger.error("Failed to initialize LED Controller")