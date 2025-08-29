/**
 * Piano Visualizer Main Controller
 * Integrates 3D piano renderer with MIDI WebSocket for real-time visualization
 */

class PianoVisualizer {
    constructor(canvasId, options = {}) {
        this.canvasId = canvasId;
        this.options = {
            enablePerformanceMonitoring: true,
            targetFPS: 60,
            maxLatency: 100, // milliseconds
            fadeOutTime: 500, // milliseconds
            enableVelocityMapping: true,
            enableSmoothTransitions: true,
            ...options
        };
        
        this.renderer = null;
        this.midiSocket = null;
        this.isInitialized = false;
        this.performanceMonitor = {
            frameDrops: 0,
            averageLatency: 0,
            lastFrameTime: 0,
            fpsHistory: []
        };
        
        // Key animation state management
        this.keyAnimations = new Map();
        this.animationFrameId = null;
        
        this.init();
    }
    
    async init() {
        try {
            await this.initializeRenderer();
            await this.initializeMIDIConnection();
            this.setupEventHandlers();
            this.startPerformanceMonitoring();
            this.startAnimationLoop();
            
            this.isInitialized = true;
            console.log('Piano Visualizer initialized successfully');
            
            // Emit initialization complete event
            this.emit('initialized');
            
        } catch (error) {
            console.error('Failed to initialize Piano Visualizer:', error);
            this.emit('error', error);
        }
    }
    
    async initializeRenderer() {
        try {
            this.renderer = new Piano3DRenderer(this.canvasId);
            
            // Explicitly initialize the renderer
            this.renderer.init();
            
            // Setup window resize handler
            window.addEventListener('resize', () => {
                this.renderer.resize();
            });
            
            console.log('3D Piano Renderer initialized');
        } catch (error) {
            throw new Error(`Failed to initialize 3D renderer: ${error.message}`);
        }
    }
    
    async initializeMIDIConnection() {
        try {
            this.midiSocket = new MIDIWebSocket();
            
            // Setup MIDI event handlers
            this.midiSocket.on('note_on', (event) => {
                this.handleNoteOn(event);
            });
            
            this.midiSocket.on('note_off', (event) => {
                this.handleNoteOff(event);
            });
            
            this.midiSocket.on('connected', () => {
                console.log('MIDI WebSocket connected');
                this.emit('midi_connected');
            });
            
            this.midiSocket.on('disconnected', () => {
                console.log('MIDI WebSocket disconnected');
                this.emit('midi_disconnected');
            });
            
            this.midiSocket.on('error', (error) => {
                console.error('MIDI WebSocket error:', error);
                this.emit('midi_error', error);
            });
            
            console.log('MIDI WebSocket connection initialized');
        } catch (error) {
            throw new Error(`Failed to initialize MIDI connection: ${error.message}`);
        }
    }
    
    setupEventHandlers() {
        // Handle canvas context loss
        const canvas = document.getElementById(this.canvasId);
        canvas.addEventListener('webglcontextlost', (event) => {
            event.preventDefault();
            console.warn('WebGL context lost');
            this.emit('context_lost');
        });
        
        canvas.addEventListener('webglcontextrestored', () => {
            console.log('WebGL context restored');
            this.initializeRenderer();
            this.emit('context_restored');
        });
    }
    
    handleNoteOn(midiEvent) {
        const { note, velocity, timestamp } = midiEvent;
        const currentTime = performance.now();
        const latency = currentTime - timestamp;
        
        // Track latency for performance monitoring
        this.updateLatencyStats(latency);
        
        // Check if latency exceeds threshold
        if (latency > this.options.maxLatency) {
            console.warn(`High latency detected: ${latency.toFixed(2)}ms`);
            this.emit('high_latency', { latency, event: midiEvent });
        }
        
        // Update renderer
        if (this.renderer) {
            this.renderer.onNoteOn(note, velocity);
        }
        
        // Setup fade-out animation if enabled
        if (this.options.enableSmoothTransitions) {
            this.setupKeyFadeOut(note, currentTime);
        }
        
        // Emit event for external listeners
        this.emit('note_on', { note, velocity, latency });
    }
    
    handleNoteOff(midiEvent) {
        const { note, timestamp } = midiEvent;
        const currentTime = performance.now();
        const latency = currentTime - timestamp;
        
        // Update renderer immediately or start fade-out
        if (this.renderer) {
            if (this.options.enableSmoothTransitions) {
                this.startKeyFadeOut(note, currentTime);
            } else {
                this.renderer.onNoteOff(note);
            }
        }
        
        // Emit event for external listeners
        this.emit('note_off', { note, latency });
    }
    
    setupKeyFadeOut(note, startTime) {
        // Cancel any existing fade-out for this key
        if (this.keyAnimations.has(note)) {
            clearTimeout(this.keyAnimations.get(note).timeoutId);
        }
        
        // Store animation state
        this.keyAnimations.set(note, {
            startTime,
            fadeStartTime: null,
            timeoutId: null
        });
    }
    
    startKeyFadeOut(note, fadeStartTime) {
        const animation = this.keyAnimations.get(note);
        if (!animation) return;
        
        animation.fadeStartTime = fadeStartTime;
        
        // Set timeout to complete fade-out
        animation.timeoutId = setTimeout(() => {
            if (this.renderer) {
                this.renderer.onNoteOff(note);
            }
            this.keyAnimations.delete(note);
        }, this.options.fadeOutTime);
    }
    
    startAnimationLoop() {
        const animate = (currentTime) => {
            // Update performance monitoring
            this.updatePerformanceStats(currentTime);
            
            // Process key animations
            this.processKeyAnimations(currentTime);
            
            // Continue animation loop
            this.animationFrameId = requestAnimationFrame(animate);
        };
        
        this.animationFrameId = requestAnimationFrame(animate);
    }
    
    processKeyAnimations(currentTime) {
        // Handle smooth fade-out transitions
        if (this.options.enableSmoothTransitions) {
            for (const [note, animation] of this.keyAnimations.entries()) {
                if (animation.fadeStartTime) {
                    const fadeProgress = (currentTime - animation.fadeStartTime) / this.options.fadeOutTime;
                    
                    if (fadeProgress >= 1.0) {
                        // Fade complete
                        if (this.renderer) {
                            this.renderer.onNoteOff(note);
                        }
                        this.keyAnimations.delete(note);
                    }
                    // Note: Actual fade rendering is handled in the renderer
                }
            }
        }
    }
    
    startPerformanceMonitoring() {
        if (!this.options.enablePerformanceMonitoring) return;
        
        setInterval(() => {
            this.updatePerformanceReport();
        }, 1000); // Update every second
    }
    
    updatePerformanceStats(currentTime) {
        if (this.performanceMonitor.lastFrameTime > 0) {
            const frameDelta = currentTime - this.performanceMonitor.lastFrameTime;
            const fps = 1000 / frameDelta;
            
            this.performanceMonitor.fpsHistory.push(fps);
            if (this.performanceMonitor.fpsHistory.length > 60) {
                this.performanceMonitor.fpsHistory.shift();
            }
            
            // Detect frame drops
            if (fps < this.options.targetFPS * 0.8) {
                this.performanceMonitor.frameDrops++;
            }
        }
        
        this.performanceMonitor.lastFrameTime = currentTime;
    }
    
    updateLatencyStats(latency) {
        // Simple moving average
        this.performanceMonitor.averageLatency = 
            (this.performanceMonitor.averageLatency * 0.9) + (latency * 0.1);
    }
    
    updatePerformanceReport() {
        const fps = this.renderer ? this.renderer.getFPS() : 0;
        const latencyStats = this.midiSocket ? this.midiSocket.getLatencyStats() : {};
        
        const report = {
            fps,
            averageLatency: this.performanceMonitor.averageLatency,
            frameDrops: this.performanceMonitor.frameDrops,
            latencyStats,
            connectionState: this.midiSocket ? this.midiSocket.getConnectionState() : null
        };
        
        this.emit('performance_update', report);
        
        // Log warnings for performance issues
        if (fps < this.options.targetFPS * 0.7) {
            console.warn(`Low FPS detected: ${fps.toFixed(1)} (target: ${this.options.targetFPS})`);
        }
        
        if (this.performanceMonitor.averageLatency > this.options.maxLatency) {
            console.warn(`High average latency: ${this.performanceMonitor.averageLatency.toFixed(2)}ms`);
        }
    }
    
    // Public API methods
    getPerformanceStats() {
        return {
            fps: this.renderer ? this.renderer.getFPS() : 0,
            averageLatency: this.performanceMonitor.averageLatency,
            frameDrops: this.performanceMonitor.frameDrops,
            latencyStats: this.midiSocket ? this.midiSocket.getLatencyStats() : {},
            connectionState: this.midiSocket ? this.midiSocket.getConnectionState() : null
        };
    }
    
    isConnected() {
        return this.midiSocket && this.midiSocket.getConnectionState().connected;
    }
    
    reconnect() {
        if (this.midiSocket) {
            this.midiSocket.disconnect();
            setTimeout(() => {
                this.initializeMIDIConnection();
            }, 1000);
        }
    }
    
    // Test methods for development
    simulateNoteOn(note, velocity = 64) {
        this.handleNoteOn({
            note,
            velocity,
            timestamp: performance.now(),
            type: 'note_on',
            channel: 0
        });
    }
    
    simulateNoteOff(note) {
        this.handleNoteOff({
            note,
            timestamp: performance.now(),
            type: 'note_off',
            channel: 0
        });
    }
    
    // Event system
    on(event, callback) {
        if (!this.listeners) {
            this.listeners = new Map();
        }
        
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        
        this.listeners.get(event).push(callback);
    }
    
    emit(event, data) {
        if (this.listeners && this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in event listener for '${event}':`, error);
                }
            });
        }
    }
    
    // Cleanup
    destroy() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
        }
        
        if (this.midiSocket) {
            this.midiSocket.disconnect();
        }
        
        // Clear all animations
        this.keyAnimations.clear();
        
        console.log('Piano Visualizer destroyed');
    }
}

// Make available globally for browser use
if (typeof window !== 'undefined') {
    window.PianoVisualizer = PianoVisualizer;
}

// Export for use in other modules (Node.js)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = PianoVisualizer;
}