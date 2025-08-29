/**
 * Piano 3D WebGL Renderer
 * Renders a 3D piano keyboard with real-time lighting effects
 */

class Piano3DRenderer {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.gl = null;
        this.program = null;
        this.keys = [];
        this.keyStates = new Map(); // Track key press states
        this.frameCount = 0;
        this.lastFrameTime = 0;
        this.fps = 0;
        
        // Piano constants
        this.TOTAL_KEYS = 88;
        this.WHITE_KEYS = 52;
        this.BLACK_KEYS = 36;
        this.KEY_WIDTH = 0.023; // meters
        this.KEY_LENGTH = 0.15; // meters
        this.BLACK_KEY_WIDTH = 0.013;
        this.BLACK_KEY_LENGTH = 0.095;
        this.KEY_HEIGHT = 0.02;
        
        // Camera settings
        this.camera = {
            position: [0, 0.3, 0.5],
            target: [0, 0, 0],
            up: [0, 1, 0],
            fov: 45,
            near: 0.1,
            far: 10.0
        };
        
        // Don't auto-initialize - wait for explicit call
        // this.init();
    }
    
    init() {
        this.setupWebGL();
        this.createShaders();
        this.createPianoGeometry();
        this.setupMatrices();
        this.startRenderLoop();
    }
    
    setupWebGL() {
        this.gl = this.canvas.getContext('webgl') || this.canvas.getContext('experimental-webgl');
        
        if (!this.gl) {
            throw new Error('WebGL not supported');
        }
        
        // Set canvas size
        this.canvas.width = this.canvas.clientWidth;
        this.canvas.height = this.canvas.clientHeight;
        
        this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
        this.gl.enable(this.gl.DEPTH_TEST);
        this.gl.enable(this.gl.CULL_FACE);
        this.gl.clearColor(0.1, 0.1, 0.15, 1.0);
    }
    
    createShaders() {
        const vertexShaderSource = `
            attribute vec3 a_position;
            attribute vec3 a_normal;
            attribute vec3 a_color;
            
            uniform mat4 u_modelViewMatrix;
            uniform mat4 u_projectionMatrix;
            uniform mat4 u_normalMatrix;
            
            varying vec3 v_normal;
            varying vec3 v_color;
            varying vec3 v_position;
            
            void main() {
                gl_Position = u_projectionMatrix * u_modelViewMatrix * vec4(a_position, 1.0);
                v_normal = normalize((u_normalMatrix * vec4(a_normal, 0.0)).xyz);
                v_color = a_color;
                v_position = (u_modelViewMatrix * vec4(a_position, 1.0)).xyz;
            }
        `;
        
        const fragmentShaderSource = `
            precision mediump float;
            
            varying vec3 v_normal;
            varying vec3 v_color;
            varying vec3 v_position;
            
            uniform vec3 u_lightDirection;
            uniform vec3 u_lightColor;
            uniform float u_ambientStrength;
            
            void main() {
                // Ambient lighting
                vec3 ambient = u_ambientStrength * u_lightColor;
                
                // Diffuse lighting
                float diff = max(dot(v_normal, normalize(-u_lightDirection)), 0.0);
                vec3 diffuse = diff * u_lightColor;
                
                // Combine lighting with key color
                vec3 result = (ambient + diffuse) * v_color;
                gl_FragColor = vec4(result, 1.0);
            }
        `;
        
        const vertexShader = this.compileShader(vertexShaderSource, this.gl.VERTEX_SHADER);
        const fragmentShader = this.compileShader(fragmentShaderSource, this.gl.FRAGMENT_SHADER);
        
        this.program = this.gl.createProgram();
        this.gl.attachShader(this.program, vertexShader);
        this.gl.attachShader(this.program, fragmentShader);
        this.gl.linkProgram(this.program);
        
        if (!this.gl.getProgramParameter(this.program, this.gl.LINK_STATUS)) {
            throw new Error('Shader program failed to link: ' + this.gl.getProgramInfoLog(this.program));
        }
        
        // Get attribute and uniform locations
        this.attributes = {
            position: this.gl.getAttribLocation(this.program, 'a_position'),
            normal: this.gl.getAttribLocation(this.program, 'a_normal'),
            color: this.gl.getAttribLocation(this.program, 'a_color')
        };
        
        this.uniforms = {
            modelViewMatrix: this.gl.getUniformLocation(this.program, 'u_modelViewMatrix'),
            projectionMatrix: this.gl.getUniformLocation(this.program, 'u_projectionMatrix'),
            normalMatrix: this.gl.getUniformLocation(this.program, 'u_normalMatrix'),
            lightDirection: this.gl.getUniformLocation(this.program, 'u_lightDirection'),
            lightColor: this.gl.getUniformLocation(this.program, 'u_lightColor'),
            ambientStrength: this.gl.getUniformLocation(this.program, 'u_ambientStrength')
        };
    }
    
    compileShader(source, type) {
        const shader = this.gl.createShader(type);
        this.gl.shaderSource(shader, source);
        this.gl.compileShader(shader);
        
        if (!this.gl.getShaderParameter(shader, this.gl.COMPILE_STATUS)) {
            throw new Error('Shader compilation error: ' + this.gl.getShaderInfoLog(shader));
        }
        
        return shader;
    }
    
    createPianoGeometry() {
        this.keys = [];
        
        // Create white keys first
        let whiteKeyIndex = 0;
        for (let i = 0; i < this.TOTAL_KEYS; i++) {
            const midiNote = i + 21; // Piano starts at A0 (MIDI note 21)
            const isBlackKey = this.isBlackKey(midiNote);
            
            if (!isBlackKey) {
                const key = this.createWhiteKey(whiteKeyIndex, midiNote);
                this.keys.push(key);
                whiteKeyIndex++;
            }
        }
        
        // Create black keys
        let whiteKeyPos = 0;
        for (let i = 0; i < this.TOTAL_KEYS; i++) {
            const midiNote = i + 21;
            const isBlackKey = this.isBlackKey(midiNote);
            
            if (isBlackKey) {
                const key = this.createBlackKey(whiteKeyPos, midiNote);
                this.keys.push(key);
            }
            
            if (!isBlackKey) {
                whiteKeyPos++;
            }
        }
        
        // Initialize key states
        this.keys.forEach(key => {
            this.keyStates.set(key.midiNote, {
                pressed: false,
                velocity: 0,
                pressTime: 0,
                releaseTime: 0
            });
        });
    }
    
    isBlackKey(midiNote) {
        const noteInOctave = midiNote % 12;
        return [1, 3, 6, 8, 10].includes(noteInOctave);
    }
    
    createWhiteKey(index, midiNote) {
        const x = (index - this.WHITE_KEYS / 2) * this.KEY_WIDTH;
        const y = 0;
        const z = 0;
        
        const geometry = this.createKeyGeometry(
            x, y, z,
            this.KEY_WIDTH, this.KEY_HEIGHT, this.KEY_LENGTH,
            [0.95, 0.95, 0.95] // White color
        );
        
        return {
            midiNote,
            isBlack: false,
            geometry,
            position: [x, y, z],
            baseColor: [0.95, 0.95, 0.95]
        };
    }
    
    createBlackKey(whiteKeyIndex, midiNote) {
        // Position black key between white keys
        const noteInOctave = midiNote % 12;
        let offset = 0;
        
        // Adjust positioning based on black key position in octave
        switch (noteInOctave) {
            case 1: offset = 0.6; break; // C#
            case 3: offset = -0.4; break; // D#
            case 6: offset = 0.5; break; // F#
            case 8: offset = 0; break; // G#
            case 10: offset = -0.5; break; // A#
        }
        
        const x = (whiteKeyIndex - this.WHITE_KEYS / 2) * this.KEY_WIDTH + offset * this.KEY_WIDTH;
        const y = this.KEY_HEIGHT / 2;
        const z = -this.BLACK_KEY_LENGTH / 2 + this.KEY_LENGTH / 2;
        
        const geometry = this.createKeyGeometry(
            x, y, z,
            this.BLACK_KEY_WIDTH, this.KEY_HEIGHT, this.BLACK_KEY_LENGTH,
            [0.1, 0.1, 0.1] // Black color
        );
        
        return {
            midiNote,
            isBlack: true,
            geometry,
            position: [x, y, z],
            baseColor: [0.1, 0.1, 0.1]
        };
    }
    
    createKeyGeometry(x, y, z, width, height, length, color) {
        const vertices = [];
        const normals = [];
        const colors = [];
        const indices = [];
        
        // Create box geometry
        const hw = width / 2;
        const hh = height / 2;
        const hl = length / 2;
        
        // Define vertices for a box
        const boxVertices = [
            // Front face
            [-hw, -hh,  hl], [ hw, -hh,  hl], [ hw,  hh,  hl], [-hw,  hh,  hl],
            // Back face
            [-hw, -hh, -hl], [-hw,  hh, -hl], [ hw,  hh, -hl], [ hw, -hh, -hl],
            // Top face
            [-hw,  hh, -hl], [-hw,  hh,  hl], [ hw,  hh,  hl], [ hw,  hh, -hl],
            // Bottom face
            [-hw, -hh, -hl], [ hw, -hh, -hl], [ hw, -hh,  hl], [-hw, -hh,  hl],
            // Right face
            [ hw, -hh, -hl], [ hw,  hh, -hl], [ hw,  hh,  hl], [ hw, -hh,  hl],
            // Left face
            [-hw, -hh, -hl], [-hw, -hh,  hl], [-hw,  hh,  hl], [-hw,  hh, -hl]
        ];
        
        const boxNormals = [
            [0, 0, 1], [0, 0, 1], [0, 0, 1], [0, 0, 1],     // Front
            [0, 0, -1], [0, 0, -1], [0, 0, -1], [0, 0, -1], // Back
            [0, 1, 0], [0, 1, 0], [0, 1, 0], [0, 1, 0],     // Top
            [0, -1, 0], [0, -1, 0], [0, -1, 0], [0, -1, 0], // Bottom
            [1, 0, 0], [1, 0, 0], [1, 0, 0], [1, 0, 0],     // Right
            [-1, 0, 0], [-1, 0, 0], [-1, 0, 0], [-1, 0, 0]  // Left
        ];
        
        const boxIndices = [
            0, 1, 2, 0, 2, 3,       // Front
            4, 5, 6, 4, 6, 7,       // Back
            8, 9, 10, 8, 10, 11,    // Top
            12, 13, 14, 12, 14, 15, // Bottom
            16, 17, 18, 16, 18, 19, // Right
            20, 21, 22, 20, 22, 23  // Left
        ];
        
        // Transform vertices and add to arrays
        boxVertices.forEach(vertex => {
            vertices.push(vertex[0] + x, vertex[1] + y, vertex[2] + z);
            colors.push(...color);
        });
        
        normals.push(...boxNormals.flat());
        indices.push(...boxIndices);
        
        // Create WebGL buffers
        const vertexBuffer = this.gl.createBuffer();
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, vertexBuffer);
        this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array(vertices), this.gl.STATIC_DRAW);
        
        const normalBuffer = this.gl.createBuffer();
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, normalBuffer);
        this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array(normals), this.gl.STATIC_DRAW);
        
        const colorBuffer = this.gl.createBuffer();
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, colorBuffer);
        this.gl.bufferData(this.gl.ARRAY_BUFFER, new Float32Array(colors), this.gl.DYNAMIC_DRAW);
        
        const indexBuffer = this.gl.createBuffer();
        this.gl.bindBuffer(this.gl.ELEMENT_ARRAY_BUFFER, indexBuffer);
        this.gl.bufferData(this.gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), this.gl.STATIC_DRAW);
        
        return {
            vertexBuffer,
            normalBuffer,
            colorBuffer,
            indexBuffer,
            indexCount: indices.length,
            vertices: new Float32Array(vertices),
            colors: new Float32Array(colors)
        };
    }
    
    setupMatrices() {
        // Projection matrix
        this.projectionMatrix = this.createPerspectiveMatrix(
            this.camera.fov * Math.PI / 180,
            this.canvas.width / this.canvas.height,
            this.camera.near,
            this.camera.far
        );
        
        // View matrix
        this.viewMatrix = this.createLookAtMatrix(
            this.camera.position,
            this.camera.target,
            this.camera.up
        );
    }
    
    createPerspectiveMatrix(fov, aspect, near, far) {
        const f = Math.tan(Math.PI * 0.5 - 0.5 * fov);
        const rangeInv = 1.0 / (near - far);
        
        return [
            f / aspect, 0, 0, 0,
            0, f, 0, 0,
            0, 0, (near + far) * rangeInv, -1,
            0, 0, near * far * rangeInv * 2, 0
        ];
    }
    
    createLookAtMatrix(eye, target, up) {
        const zAxis = this.normalize(this.subtract(eye, target));
        const xAxis = this.normalize(this.cross(up, zAxis));
        const yAxis = this.normalize(this.cross(zAxis, xAxis));
        
        return [
            xAxis[0], xAxis[1], xAxis[2], 0,
            yAxis[0], yAxis[1], yAxis[2], 0,
            zAxis[0], zAxis[1], zAxis[2], 0,
            eye[0], eye[1], eye[2], 1
        ];
    }
    
    // Vector math utilities
    subtract(a, b) {
        return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
    }
    
    cross(a, b) {
        return [
            a[1] * b[2] - a[2] * b[1],
            a[2] * b[0] - a[0] * b[2],
            a[0] * b[1] - a[1] * b[0]
        ];
    }
    
    normalize(v) {
        const length = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
        return length > 0 ? [v[0] / length, v[1] / length, v[2] / length] : [0, 0, 0];
    }
    
    startRenderLoop() {
        const render = (currentTime) => {
            this.updateFPS(currentTime);
            this.render();
            requestAnimationFrame(render);
        };
        requestAnimationFrame(render);
    }
    
    updateFPS(currentTime) {
        this.frameCount++;
        if (currentTime - this.lastFrameTime >= 1000) {
            this.fps = this.frameCount;
            this.frameCount = 0;
            this.lastFrameTime = currentTime;
        }
    }
    
    render() {
        this.gl.clear(this.gl.COLOR_BUFFER_BIT | this.gl.DEPTH_BUFFER_BIT);
        this.gl.useProgram(this.program);
        
        // Set uniforms
        this.gl.uniformMatrix4fv(this.uniforms.projectionMatrix, false, this.projectionMatrix);
        this.gl.uniformMatrix4fv(this.uniforms.modelViewMatrix, false, this.viewMatrix);
        this.gl.uniformMatrix4fv(this.uniforms.normalMatrix, false, this.viewMatrix); // Simplified
        this.gl.uniform3fv(this.uniforms.lightDirection, [0.5, -1.0, 0.5]);
        this.gl.uniform3fv(this.uniforms.lightColor, [1.0, 1.0, 1.0]);
        this.gl.uniform1f(this.uniforms.ambientStrength, 0.3);
        
        // Render all keys
        this.keys.forEach(key => {
            this.renderKey(key);
        });
    }
    
    renderKey(key) {
        const geometry = key.geometry;
        
        // Update key color based on state
        const keyState = this.keyStates.get(key.midiNote);
        const colors = new Float32Array(geometry.colors.length);
        
        for (let i = 0; i < colors.length; i += 3) {
            if (keyState.pressed) {
                // Highlight pressed key with velocity-based intensity
                const intensity = 0.3 + (keyState.velocity / 127) * 0.7;
                colors[i] = key.baseColor[0] + intensity * 0.5;     // R
                colors[i + 1] = key.baseColor[1] + intensity * 0.3; // G
                colors[i + 2] = key.baseColor[2] + intensity * 0.1; // B
            } else {
                colors[i] = key.baseColor[0];     // R
                colors[i + 1] = key.baseColor[1]; // G
                colors[i + 2] = key.baseColor[2]; // B
            }
        }
        
        // Update color buffer
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, geometry.colorBuffer);
        this.gl.bufferSubData(this.gl.ARRAY_BUFFER, 0, colors);
        
        // Bind vertex buffer
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, geometry.vertexBuffer);
        this.gl.enableVertexAttribArray(this.attributes.position);
        this.gl.vertexAttribPointer(this.attributes.position, 3, this.gl.FLOAT, false, 0, 0);
        
        // Bind normal buffer
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, geometry.normalBuffer);
        this.gl.enableVertexAttribArray(this.attributes.normal);
        this.gl.vertexAttribPointer(this.attributes.normal, 3, this.gl.FLOAT, false, 0, 0);
        
        // Bind color buffer
        this.gl.bindBuffer(this.gl.ARRAY_BUFFER, geometry.colorBuffer);
        this.gl.enableVertexAttribArray(this.attributes.color);
        this.gl.vertexAttribPointer(this.attributes.color, 3, this.gl.FLOAT, false, 0, 0);
        
        // Bind index buffer and draw
        this.gl.bindBuffer(this.gl.ELEMENT_ARRAY_BUFFER, geometry.indexBuffer);
        this.gl.drawElements(this.gl.TRIANGLES, geometry.indexCount, this.gl.UNSIGNED_SHORT, 0);
    }
    
    // Public API for MIDI events
    onNoteOn(midiNote, velocity) {
        const keyState = this.keyStates.get(midiNote);
        if (keyState) {
            keyState.pressed = true;
            keyState.velocity = velocity;
            keyState.pressTime = performance.now();
        }
    }
    
    onNoteOff(midiNote) {
        const keyState = this.keyStates.get(midiNote);
        if (keyState) {
            keyState.pressed = false;
            keyState.velocity = 0;
            keyState.releaseTime = performance.now();
        }
    }
    
    getFPS() {
        return this.fps;
    }
    
    resize() {
        this.canvas.width = this.canvas.clientWidth;
        this.canvas.height = this.canvas.clientHeight;
        this.gl.viewport(0, 0, this.canvas.width, this.canvas.height);
        this.setupMatrices();
    }
}

// Make available globally for browser use
if (typeof window !== 'undefined') {
    window.Piano3DRenderer = Piano3DRenderer;
}

// Export for use in other modules (Node.js)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = Piano3DRenderer;
}