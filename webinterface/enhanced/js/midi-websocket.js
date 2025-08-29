/**
 * MIDI WebSocket Handler
 * Manages real-time MIDI event communication between backend and frontend
 */

class MIDIWebSocket {
    constructor(url = null) {
        this.url = url || `ws://${window.location.hostname}:8765`;
        this.socket = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 1000;
        this.isConnected = false;
        this.listeners = new Map();
        this.messageQueue = [];
        this.latencyTracker = {
            samples: [],
            maxSamples: 100
        };
        
        this.connect();
    }
    
    connect() {
        try {
            this.socket = new WebSocket(this.url);
            this.setupEventHandlers();
        } catch (error) {
            console.error('WebSocket connection failed:', error);
            this.scheduleReconnect();
        }
    }
    
    setupEventHandlers() {
        this.socket.onopen = (event) => {
            console.log('MIDI WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.flushMessageQueue();
            this.emit('connected', event);
        };
        
        this.socket.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                this.handleMessage(data);
            } catch (error) {
                console.error('Failed to parse WebSocket message:', error, event.data);
            }
        };
        
        this.socket.onclose = (event) => {
            console.log('MIDI WebSocket disconnected:', event.code, event.reason);
            this.isConnected = false;
            this.emit('disconnected', event);
            
            if (!event.wasClean && this.reconnectAttempts < this.maxReconnectAttempts) {
                this.scheduleReconnect();
            }
        };
        
        this.socket.onerror = (error) => {
            console.error('MIDI WebSocket error:', error);
            this.emit('error', error);
        };
    }
    
    handleMessage(data) {
        const receiveTime = performance.now();
        
        // Track latency if timestamp is provided
        if (data.timestamp) {
            const latency = receiveTime - data.timestamp;
            this.trackLatency(latency);
        }
        
        switch (data.type) {
            case 'midi_event':
                this.handleMIDIEvent(data, receiveTime);
                break;
            case 'system_status':
                this.emit('system_status', data.payload);
                break;
            case 'ping':
                this.sendPong(data.timestamp);
                break;
            case 'pong':
                this.handlePong(data.timestamp, receiveTime);
                break;
            default:
                console.warn('Unknown message type:', data.type);
        }
    }
    
    handleMIDIEvent(data, receiveTime) {
        const midiEvent = data.payload;
        
        // Validate MIDI event structure
        if (!this.isValidMIDIEvent(midiEvent)) {
            console.warn('Invalid MIDI event received:', midiEvent);
            return;
        }
        
        // Add receive timestamp for latency tracking
        midiEvent.receiveTime = receiveTime;
        
        // Emit specific MIDI event types
        switch (midiEvent.type) {
            case 'note_on':
                this.emit('note_on', midiEvent);
                break;
            case 'note_off':
                this.emit('note_off', midiEvent);
                break;
            case 'control_change':
                this.emit('control_change', midiEvent);
                break;
            case 'program_change':
                this.emit('program_change', midiEvent);
                break;
            case 'pitch_bend':
                this.emit('pitch_bend', midiEvent);
                break;
            default:
                this.emit('midi_event', midiEvent);
        }
    }
    
    isValidMIDIEvent(event) {
        return event &&
               typeof event.type === 'string' &&
               typeof event.timestamp === 'number' &&
               typeof event.channel === 'number' &&
               event.channel >= 0 && event.channel <= 15;
    }
    
    trackLatency(latency) {
        this.latencyTracker.samples.push(latency);
        
        if (this.latencyTracker.samples.length > this.latencyTracker.maxSamples) {
            this.latencyTracker.samples.shift();
        }
    }
    
    getAverageLatency() {
        const samples = this.latencyTracker.samples;
        if (samples.length === 0) return 0;
        
        const sum = samples.reduce((a, b) => a + b, 0);
        return sum / samples.length;
    }
    
    getLatencyStats() {
        const samples = this.latencyTracker.samples;
        if (samples.length === 0) {
            return { min: 0, max: 0, avg: 0, count: 0 };
        }
        
        const sorted = [...samples].sort((a, b) => a - b);
        return {
            min: sorted[0],
            max: sorted[sorted.length - 1],
            avg: this.getAverageLatency(),
            median: sorted[Math.floor(sorted.length / 2)],
            count: samples.length
        };
    }
    
    sendPong(timestamp) {
        this.send({
            type: 'pong',
            timestamp: timestamp,
            clientTime: performance.now()
        });
    }
    
    handlePong(originalTimestamp, receiveTime) {
        const roundTripTime = receiveTime - originalTimestamp;
        this.emit('ping_response', { roundTripTime, receiveTime });
    }
    
    send(data) {
        if (this.isConnected && this.socket.readyState === WebSocket.OPEN) {
            this.socket.send(JSON.stringify(data));
        } else {
            // Queue message for when connection is restored
            this.messageQueue.push(data);
        }
    }
    
    flushMessageQueue() {
        while (this.messageQueue.length > 0 && this.isConnected) {
            const message = this.messageQueue.shift();
            this.send(message);
        }
    }
    
    scheduleReconnect() {
        if (this.reconnectAttempts >= this.maxReconnectAttempts) {
            console.error('Max reconnection attempts reached');
            this.emit('max_reconnect_attempts');
            return;
        }
        
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1); // Exponential backoff
        
        console.log(`Attempting to reconnect in ${delay}ms (attempt ${this.reconnectAttempts}/${this.maxReconnectAttempts})`);
        
        setTimeout(() => {
            this.connect();
        }, delay);
    }
    
    // Event listener management
    on(event, callback) {
        if (!this.listeners.has(event)) {
            this.listeners.set(event, []);
        }
        this.listeners.get(event).push(callback);
    }
    
    off(event, callback) {
        if (this.listeners.has(event)) {
            const callbacks = this.listeners.get(event);
            const index = callbacks.indexOf(callback);
            if (index > -1) {
                callbacks.splice(index, 1);
            }
        }
    }
    
    emit(event, data) {
        if (this.listeners.has(event)) {
            this.listeners.get(event).forEach(callback => {
                try {
                    callback(data);
                } catch (error) {
                    console.error(`Error in event listener for '${event}':`, error);
                }
            });
        }
    }
    
    // Public API methods
    requestSystemStatus() {
        this.send({
            type: 'request_system_status',
            timestamp: performance.now()
        });
    }
    
    ping() {
        this.send({
            type: 'ping',
            timestamp: performance.now()
        });
    }
    
    disconnect() {
        if (this.socket) {
            this.socket.close(1000, 'Client disconnect');
        }
    }
    
    getConnectionState() {
        return {
            connected: this.isConnected,
            readyState: this.socket ? this.socket.readyState : WebSocket.CLOSED,
            reconnectAttempts: this.reconnectAttempts,
            queuedMessages: this.messageQueue.length,
            latencyStats: this.getLatencyStats()
        };
    }
}

// WebSocket ready states for reference
MIDIWebSocket.CONNECTING = 0;
MIDIWebSocket.OPEN = 1;
MIDIWebSocket.CLOSING = 2;
MIDIWebSocket.CLOSED = 3;

// Export for use in other modules
if (typeof module !== 'undefined' && module.exports) {
    module.exports = MIDIWebSocket;
}