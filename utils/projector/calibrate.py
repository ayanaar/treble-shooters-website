import cv2
import numpy as np
import threading
import time
import os
import sys
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import webbrowser
from urllib.parse import parse_qs, urlparse

# Global state for communication between windows
class CalibrationState:
    def __init__(self):
        self.projector_command = {"action": "init"}
        self.last_command_id = 0
        self.camera_points = []
        self.projector_points = []
        self.homography_matrix = None
        self.is_calibrated = False

# Initialize global state
global_state = CalibrationState()

class WebcamHandler(BaseHTTPRequestHandler):
    """HTTP Handler for webcam streaming and calibration"""
    
    def _set_headers(self, content_type='text/html'):
        self.send_response(200)
        self.send_header('Content-type', content_type)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
        self.end_headers()
    
    def log_message(self, format, *args):
        # Suppress logging for cleaner output
        return
    
    def do_GET(self):
        global global_state
        
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        if path == '/':
            # Serve the main interface
            self._set_headers()
            self.wfile.write(self.get_html_interface().encode())
        
        elif path == '/projector.html':
            # Serve the projector interface
            self._set_headers()
            self.wfile.write(self.get_projector_html().encode())
        
        elif path == '/command':
            # Return the current command for the projector
            self._set_headers('application/json')
            # Add a unique ID to track command changes
            response = global_state.projector_command.copy()
            response['id'] = global_state.last_command_id
            self.wfile.write(json.dumps(response).encode())
    
    def do_POST(self):
        global global_state
        
        parsed_path = urlparse(self.path)
        path = parsed_path.path
        
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length).decode('utf-8')
        data = json.loads(post_data)
        
        if path == '/calibration-point':
            # Get the next calibration point
            point_index = data.get('index', 0)
            
            # Generate a calibration point
            points = generate_calibration_points()
            if point_index < len(points):
                point = points[point_index]
                response = {
                    'index': point_index,
                    'total': len(points),
                    'coordinates': point,
                    'success': True
                }
            else:
                response = {'success': False, 'message': 'No more points'}
            
            # Send command to show this point on projector
            if point_index < len(points):
                global_state.projector_command = {
                    'action': 'showCalibrationPoint',
                    'index': point_index,
                    'total': len(points),
                    'x': point[0],
                    'y': point[1]
                }
                global_state.last_command_id += 1
            
            self._set_headers('application/json')
            self.wfile.write(json.dumps(response).encode())
        
        elif path == '/collect-point':
            # Collect a point clicked in the camera view
            camera_x = data.get('x', 0)
            camera_y = data.get('y', 0)
            point_index = data.get('index', 0)
            
            # Get the corresponding projector point
            projector_points = generate_calibration_points()
            projector_point = projector_points[point_index]
            
            # Store the point pair
            global_state.camera_points.append((camera_x, camera_y))
            global_state.projector_points.append(projector_point)
            
            print(f"Collected point {point_index+1}: Camera ({camera_x}, {camera_y}) -> Projector {projector_point}")
            
            # Check if we've collected all points
            total_points = len(projector_points)
            at_end = (point_index >= total_points - 1)
            
            if at_end:
                # When all points collected, compute homography and switch to test mode
                compute_homography()
                print("All points collected, switching to test mode")
                global_state.projector_command = {
                    'action': 'calibrationComplete'
                }
                global_state.last_command_id += 1
                response = {'success': True, 'complete': True}
            else:
                # Move to next point
                next_index = point_index + 1
                if next_index < len(projector_points):
                    point = projector_points[next_index]
                    global_state.projector_command = {
                        'action': 'showCalibrationPoint',
                        'index': next_index,
                        'total': len(projector_points),
                        'x': point[0],
                        'y': point[1]
                    }
                    global_state.last_command_id += 1
                
                response = {'success': True, 'complete': False, 'next_index': next_index}
            
            self._set_headers('application/json')
            self.wfile.write(json.dumps(response).encode())
        
        elif path == '/test-point':
            # Process a test point click from camera view
            camera_x = data.get('x', 0)
            camera_y = data.get('y', 0)
            
            # Transform the point using homography if calibrated
            if global_state.is_calibrated:
                projector_x, projector_y = transform_point(camera_x, camera_y)
            else:
                # Fallback to simple scaling if not calibrated
                projector_x = int(camera_x * 1.5)
                projector_y = int(camera_y * 1.5)
            
            print(f"Test point: Camera ({camera_x}, {camera_y}) -> Projector ({projector_x}, {projector_y})")
            
            # Send command to highlight this point on projector
            global_state.projector_command = {
                'action': 'highlight',
                'x': projector_x,
                'y': projector_y
            }
            global_state.last_command_id += 1
            
            response = {
                'success': True,
                'projector_x': projector_x,
                'projector_y': projector_y
            }
            
            self._set_headers('application/json')
            self.wfile.write(json.dumps(response).encode())
        
        elif path == '/test-communication':
            # Simple endpoint to test server communication
            global_state.projector_command = {
                'action': 'test',
                'message': 'Test from server',
                'timestamp': time.time()
            }
            global_state.last_command_id += 1
            
            response = {'success': True}
            self._set_headers('application/json')
            self.wfile.write(json.dumps(response).encode())
        
        elif path == '/reset-calibration':
            # Reset calibration
            global_state.camera_points = []
            global_state.projector_points = []
            global_state.homography_matrix = None
            global_state.is_calibrated = False
            
            # Reset projector view
            global_state.projector_command = {
                'action': 'reset'
            }
            global_state.last_command_id += 1
            
            response = {'success': True}
            self._set_headers('application/json')
            self.wfile.write(json.dumps(response).encode())
    
    def get_html_interface(self):
        """Return the HTML for the main interface"""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Camera-Projector Calibration</title>
            <style>
                body {
                    font-family: Arial, sans-serif;
                    margin: 0;
                    padding: 20px;
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                }
                #container {
                    display: flex;
                    flex-direction: column;
                    align-items: center;
                    width: 100%;
                    max-width: 800px;
                }
                #videoContainer {
                    position: relative;
                    margin-bottom: 20px;
                    border: 1px solid #ccc;
                }
                #video {
                    width: 640px;
                    height: 480px;
                    background-color: #000;
                }
                #canvas {
                    position: absolute;
                    top: 0;
                    left: 0;
                }
                #instructions {
                    margin-bottom: 20px;
                    padding: 10px;
                    background-color: #f0f0f0;
                    border-radius: 5px;
                    width: 100%;
                }
                #status {
                    margin-top: 10px;
                    font-weight: bold;
                }
                #debug {
                    margin-top: 10px;
                    background-color: #f8f8f8;
                    padding: 10px;
                    border: 1px solid #ddd;
                    font-family: monospace;
                    max-height: 200px;
                    overflow-y: auto;
                    width: 100%;
                }
                button {
                    padding: 10px 15px;
                    margin: 5px;
                    background-color: #4CAF50;
                    color: white;
                    border: none;
                    border-radius: 4px;
                    cursor: pointer;
                }
                button:hover {
                    background-color: #45a049;
                }
                button:disabled {
                    background-color: #cccccc;
                    cursor: not-allowed;
                }
            </style>
        </head>
        <body>
            <div id="container">
                <h1>Camera-Projector Calibration</h1>
                
                <div id="instructions" style="text-align: center;">
                    <button id="openProjector">Open Projector View</button>
                </div>
                
                <div id="videoContainer">
                    <video id="video" autoplay playsinline></video>
                    <canvas id="canvas" width="640" height="480"></canvas>
                </div>
                
                <div id="status">Waiting for camera access...</div>
                
                <div>
                    <button id="startCalibration">Start Calibration</button>
                    <button id="testPoint">Test Communication</button>
                    <button id="resetCalibration">Reset</button>
                </div>
                
                <div id="debug"></div>
            </div>
            
            <script>
                let video = document.getElementById('video');
                let canvas = document.getElementById('canvas');
                let ctx = canvas.getContext('2d');
                let status = document.getElementById('status');
                let startBtn = document.getElementById('startCalibration');
                let testBtn = document.getElementById('testPoint');
                let resetBtn = document.getElementById('resetCalibration');
                let openProjectorBtn = document.getElementById('openProjector');
                let debugDiv = document.getElementById('debug');
                
                let collectedPoints = [];
                let currentPointIndex = 0;
                let mode = "idle";  // idle, collect, test
                let projectorWindow = null;
                
                // Debug function
                function debug(message) {
                    console.log(message);
                    debugDiv.innerHTML += message + "<br>";
                    debugDiv.scrollTop = debugDiv.scrollHeight;
                }
                
                // Open projector window
                openProjectorBtn.addEventListener('click', () => {
                    projectorWindow = window.open('/projector.html', 'projector', 'width=800,height=600');
                    debug("Opened projector window");
                });
                
                // Init webcam
                async function initCamera() {
                    try {
                        const stream = await navigator.mediaDevices.getUserMedia({ video: true });
                        video.srcObject = stream;
                        status.textContent = 'Camera ready. Click "Start Calibration" to begin.';
                        startBtn.disabled = false;
                        debug("Camera initialized successfully");
                    } catch (err) {
                        status.textContent = 'Error accessing camera: ' + err.message;
                        debug("Camera error: " + err.message);
                    }
                }
                
                // Start calibration
                startBtn.addEventListener('click', async () => {
                    mode = "collect";
                    collectedPoints = [];
                    currentPointIndex = 0;
                    status.textContent = 'Starting calibration...';
                    debug("Starting calibration");
                    
                    // Get first calibration point
                    await getCalibrationPoint(0);
                    
                    startBtn.disabled = true;
                });
                
                // Test communication
                testBtn.addEventListener('click', async () => {
                    debug("Testing server communication");
                    
                    try {
                        const response = await fetch('/test-communication', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({test: true})
                        });
                        
                        const data = await response.json();
                        debug("Test response: " + JSON.stringify(data));
                        status.textContent = 'Test command sent to projector';
                    } catch (err) {
                        debug("Error in test: " + err.message);
                    }
                });
                
                // Reset calibration
                resetBtn.addEventListener('click', async () => {
                    try {
                        const response = await fetch('/reset-calibration', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({reset: true})
                        });
                        
                        const data = await response.json();
                        if (data.success) {
                            mode = "idle";
                            collectedPoints = [];
                            currentPointIndex = 0;
                            status.textContent = 'Calibration reset. Click "Start Calibration" to begin.';
                            startBtn.disabled = false;
                            clearCanvas();
                            debug("Calibration reset");
                        }
                    } catch (err) {
                        debug("Error resetting calibration: " + err.message);
                    }
                });
                
                // Get calibration point from server
                async function getCalibrationPoint(index) {
                    try {
                        const response = await fetch('/calibration-point', {
                            method: 'POST',
                            headers: {
                                'Content-Type': 'application/json'
                            },
                            body: JSON.stringify({index: index})
                        });
                        
                        const data = await response.json();
                        debug("Got calibration point: " + JSON.stringify(data));
                        
                        if (data.success) {
                            status.textContent = `Click on calibration point ${data.index + 1}/${data.total} in the camera view`;
                            return true;
                        } else {
                            debug("Failed to get calibration point: " + data.message);
                            return false;
                        }
                    } catch (err) {
                        debug("Error getting calibration point: " + err.message);
                        return false;
                    }
                }
                
                // Handle clicks on the video/canvas
                canvas.addEventListener('click', async (e) => {
                    const rect = canvas.getBoundingClientRect();
                    const x = Math.round((e.clientX - rect.left) * (canvas.width / rect.width));
                    const y = Math.round((e.clientY - rect.top) * (canvas.height / rect.height));
                    
                    debug(`Canvas clicked at (${x}, ${y})`);
                    
                    if (mode === "collect") {
                        // Send the point to the server
                        try {
                            const response = await fetch('/collect-point', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({
                                    x: x, 
                                    y: y,
                                    index: currentPointIndex
                                })
                            });
                            
                            const data = await response.json();
                            debug("Server response: " + JSON.stringify(data));
                            
                            // Draw the point
                            drawPoint(x, y, collectedPoints.length + 1);
                            collectedPoints.push({x, y});
                            
                            if (data.complete) {
                                // We've switched to test mode
                                mode = "test";
                                status.textContent = 'Calibration complete! Click anywhere to test.';
                                debug("Switched to test mode");
                            } else {
                                // Move to next point
                                currentPointIndex = data.next_index;
                            }
                        } catch (err) {
                            debug("Error sending point to server: " + err.message);
                        }
                    } else if (mode === "test") {
                        // Test mode - send the point to get transformed coordinates
                        try {
                            const response = await fetch('/test-point', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/json'
                                },
                                body: JSON.stringify({x, y})
                            });
                            
                            const data = await response.json();
                            debug("Test point response: " + JSON.stringify(data));
                            
                            if (data.success) {
                                status.textContent = `Camera (${x},${y}) -> Projector (${data.projector_x},${data.projector_y})`;
                                
                                // Draw test point on canvas
                                clearCanvas();
                                drawTestPoint(x, y);
                            }
                        } catch (err) {
                            debug("Error testing point: " + err.message);
                        }
                    }
                });
                
                // Draw a calibration point on the canvas
                function drawPoint(x, y, index) {
                    ctx.beginPath();
                    ctx.arc(x, y, 5, 0, 2 * Math.PI);
                    ctx.fillStyle = 'green';
                    ctx.fill();
                    
                    ctx.fillStyle = 'white';
                    ctx.font = '12px Arial';
                    ctx.fillText(index.toString(), x + 10, y);
                }
                
                // Draw a test point on the canvas
                function drawTestPoint(x, y) {
                    ctx.beginPath();
                    ctx.arc(x, y, 8, 0, 2 * Math.PI);
                    ctx.fillStyle = 'red';
                    ctx.fill();
                }
                
                // Clear the canvas
                function clearCanvas() {
                    ctx.clearRect(0, 0, canvas.width, canvas.height);
                }
                
                // Start the app
                startBtn.disabled = true;
                debug("Application initialized. Please open the projector view and then start calibration.");
                initCamera();
            </script>
        </body>
        </html>
        '''
    
    def get_projector_html(self):
        """Return the HTML for the projector interface"""
        return '''
        <!DOCTYPE html>
        <html>
        <head>
            <title>Projector View</title>
            <style>
                body {
                    margin: 0;
                    padding: 0;
                    overflow: hidden;
                    background-color: black;
                    color: white;
                }
                #projectorCanvas {
                    position: absolute;
                    top: 0;
                    left: 0;
                    width: 100%;
                    height: 100%;
                }
                #instructions {
                    position: absolute;
                    bottom: 20px;
                    left: 20px;
                    background-color: rgba(0,0,0,0.7);
                    padding: 10px;
                    border-radius: 5px;
                    font-family: Arial, sans-serif;
                }
                #debug {
                    position: absolute;
                    top: 10px;
                    right: 10px;
                    background-color: rgba(0,0,0,0.7);
                    color: #00ff00;
                    padding: 10px;
                    border-radius: 5px;
                    font-family: monospace;
                    font-size: 12px;
                    max-height: 200px;
                    max-width: 400px;
                    overflow-y: auto;
                    z-index: 1000;
                    cursor: move;
                }
                .hidden {
                    display: none !important;
                }
                #debugControls {
                    position: absolute;
                    top: 5px;
                    left: 5px;
                    z-index: 1001;
                    display: flex;
                    gap: 5px;
                }
                .control-button {
                    background-color: rgba(60, 60, 60, 0.7);
                    color: white;
                    border: none;
                    border-radius: 3px;
                    padding: 5px 10px;
                    cursor: pointer;
                }
                .control-button:hover {
                    background-color: rgba(100, 100, 100, 0.7);
                }
            </style>
        </head>
        <body>
            <canvas id="projectorCanvas"></canvas>
            <div id="instructions">Press F11 for fullscreen mode. Press 'D' to toggle debug panel visibility.</div>
            <div id="debugControls">
                <button id="toggleDebug" class="control-button">Toggle Debug</button>
                <button id="clearDebug" class="control-button">Clear Debug</button>
            </div>
            <div id="debug">Debug panel - drag to move, press 'D' to hide/show</div>
            
            <script>
                let canvas = document.getElementById('projectorCanvas');
                let ctx = canvas.getContext('2d');
                let instructionsDiv = document.getElementById('instructions');
                let debugDiv = document.getElementById('debug');
                let toggleDebugBtn = document.getElementById('toggleDebug');
                let clearDebugBtn = document.getElementById('clearDebug');
                
                let lastCommandId = -1;
                let pollInterval = 500; // Poll every 500ms
                
                // Make debug panel draggable
                makeDraggable(debugDiv);
                
                // Debug function
                function debug(message) {
                    console.log(message);
                    debugDiv.innerHTML += message + "<br>";
                    debugDiv.scrollTop = debugDiv.scrollHeight;
                }
                
                // Function to make an element draggable
                function makeDraggable(element) {
                    let pos1 = 0, pos2 = 0, pos3 = 0, pos4 = 0;
                    
                    element.onmousedown = dragMouseDown;
                    
                    function dragMouseDown(e) {
                        e = e || window.event;
                        e.preventDefault();
                        // get the mouse cursor position at startup
                        pos3 = e.clientX;
                        pos4 = e.clientY;
                        document.onmouseup = closeDragElement;
                        // call a function whenever the cursor moves
                        document.onmousemove = elementDrag;
                    }
                    
                    function elementDrag(e) {
                        e = e || window.event;
                        e.preventDefault();
                        // calculate the new cursor position
                        pos1 = pos3 - e.clientX;
                        pos2 = pos4 - e.clientY;
                        pos3 = e.clientX;
                        pos4 = e.clientY;
                        // set the element's new position
                        element.style.top = (element.offsetTop - pos2) + "px";
                        element.style.left = (element.offsetLeft - pos1) + "px";
                    }
                    
                    function closeDragElement() {
                        // stop moving when mouse button is released
                        document.onmouseup = null;
                        document.onmousemove = null;
                    }
                }
                
                // Toggle debug panel visibility
                function toggleDebugPanel() {
                    debugDiv.classList.toggle('hidden');
                }
                
                // Clear debug panel
                function clearDebugPanel() {
                    debugDiv.innerHTML = "Debug panel cleared";
                }
                
                // Add toggle button handler
                toggleDebugBtn.addEventListener('click', toggleDebugPanel);
                
                // Add clear button handler
                clearDebugBtn.addEventListener('click', clearDebugPanel);
                
                // Add keyboard shortcut for toggling debug panel
                document.addEventListener('keydown', function(e) {
                    if (e.key === 'd' || e.key === 'D') {
                        toggleDebugPanel();
                    }
                });
                
                debug("Projector view loaded");
                
                // Resize canvas to fill window
                function resizeCanvas() {
                    canvas.width = window.innerWidth;
                    canvas.height = window.innerHeight;
                    debug(`Canvas resized to ${canvas.width}x${canvas.height}`);
                    // After resize, display a test pattern
                    displayStartPattern();
                }
                
                // Initialize
                resizeCanvas();
                window.addEventListener('resize', resizeCanvas);
                
                // Display a test pattern to show the projector is working
                function displayStartPattern() {
                    debug("Displaying start pattern");
                    
                    // Clear canvas
                    ctx.fillStyle = 'black';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                    
                    // Draw border
                    ctx.strokeStyle = 'white';
                    ctx.lineWidth = 4;
                    ctx.strokeRect(10, 10, canvas.width - 20, canvas.height - 20);
                    
                    // Draw text
                    ctx.fillStyle = 'white';
                    ctx.font = '30px Arial';
                    ctx.textAlign = 'center';
                    ctx.fillText('Projector View Ready', canvas.width/2, canvas.height/2);
                    ctx.font = '20px Arial';
                    ctx.fillText('Press F11 for fullscreen', canvas.width/2, canvas.height/2 + 40);
                    ctx.fillText('Press D to hide/show debug panel', canvas.width/2, canvas.height/2 + 80);
                    
                    // Draw crosshair at center
                    const centerX = canvas.width/2;
                    const centerY = canvas.height/2;
                    const size = 50;
                    
                    ctx.beginPath();
                    ctx.moveTo(centerX - size, centerY);
                    ctx.lineTo(centerX + size, centerY);
                    ctx.moveTo(centerX, centerY - size);
                    ctx.lineTo(centerX, centerY + size);
                    ctx.strokeStyle = 'red';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                }
                
                // Clear canvas
                function clearCanvas() {
                    ctx.fillStyle = 'black';
                    ctx.fillRect(0, 0, canvas.width, canvas.height);
                }
                
                // Draw a calibration point
                function drawCalibrationPoint(x, y, index, total) {
                    debug(`Drawing calibration point ${index+1}/${total} at (${x}, ${y})`);
                    clearCanvas();
                    
                    // Scale from 0-1000 to actual canvas size
                    const scaledX = (x / 1000) * canvas.width;
                    const scaledY = (y / 1000) * canvas.height;
                    
                    // Draw target
                    const radius = 10;
                    const crossSize = 20;
                    
                    ctx.beginPath();
                    ctx.arc(scaledX, scaledY, radius, 0, 2 * Math.PI);
                    ctx.fillStyle = 'red';
                    ctx.fill();
                    
                    ctx.beginPath();
                    ctx.moveTo(scaledX - crossSize, scaledY);
                    ctx.lineTo(scaledX + crossSize, scaledY);
                    ctx.moveTo(scaledX, scaledY - crossSize);
                    ctx.lineTo(scaledX, scaledY + crossSize);
                    ctx.strokeStyle = 'white';
                    ctx.lineWidth = 2;
                    ctx.stroke();
                    
                    // Draw label
                    ctx.fillStyle = 'white';
                    ctx.font = '16px Arial';
                    ctx.fillText(`Point ${index + 1}/${total}`, scaledX + 25, scaledY + 25);
                    
                    // Update instructions
                    instructionsDiv.textContent = `Calibration Point ${index + 1}/${total} - Press 'D' to toggle debug panel`;
                }
                
                // Highlight a point
                function highlightPoint(x, y) {
                    debug(`Highlighting point at (${x}, ${y})`);
                    clearCanvas();
                    
                    // Scale from 0-1000 to actual canvas size
                    const scaledX = (x / 1000) * canvas.width;
                    const scaledY = (y / 1000) * canvas.height;
                    
                    // Draw highlight
                    const radius = 20;
                    
                    ctx.beginPath();
                    ctx.arc(scaledX, scaledY, radius, 0, 2 * Math.PI);
                    ctx.fillStyle = 'green';
                    ctx.fill();
                    
                    // Update instructions
                    instructionsDiv.textContent = `Highlighted point at (${scaledX.toFixed(0)}, ${scaledY.toFixed(0)}) - Press 'D' to toggle debug panel`;
                }
                
                // Show calibration complete
                function showCalibrationComplete() {
                    debug("Calibration complete");
                    clearCanvas();
                    
                    ctx.fillStyle = 'white';
                    ctx.font = '30px Arial';
                    ctx.textAlign = 'center';
                    ctx.fillText('Calibration Complete!', canvas.width/2, canvas.height/2);
                    ctx.font = '20px Arial';
                    ctx.fillText('Click anywhere in the camera view to test', canvas.width/2, canvas.height/2 + 40);
                    
                    // Update instructions
                    instructionsDiv.textContent = 'Ready for testing. Click in the camera view. Press D to toggle debug panel.';
                }
                
                // Poll for commands from the server
                async function pollForCommands() {
                    try {
                        const response = await fetch('/command');
                        const data = await response.json();
                        
                        // Only process if this is a new command
                        if (data.id > lastCommandId) {
                            debug("New command received: " + JSON.stringify(data));
                            lastCommandId = data.id;
                            
                            // Process the command
                            switch(data.action) {
                                case 'showCalibrationPoint':
                                    drawCalibrationPoint(data.x, data.y, data.index, data.total);
                                    break;
                                case 'highlight':
                                    highlightPoint(data.x, data.y);
                                    break;
                                case 'calibrationComplete':
                                    showCalibrationComplete();
                                    break;
                                case 'test':
                                    debug("Test message received: " + data.message);
                                    // Draw something to show we received the message
                                    ctx.fillStyle = 'blue';
                                    ctx.fillRect(100, 100, 200, 200);
                                    ctx.fillStyle = 'white';
                                    ctx.font = '20px Arial';
                                    ctx.fillText('Test message received', 200, 200);
                                    break;
                                case 'reset':
                                    clearCanvas();
                                    displayStartPattern();
                                    instructionsDiv.textContent = 'Press F11 for fullscreen mode. Press D to toggle debug panel.';
                                    break;
                                default:
                                    if (data.action !== 'init') {
                                        debug("Unknown action: " + data.action);
                                    }
                            }
                        }
                    } catch (err) {
                        debug("Error polling for commands: " + err.message);
                    }
                    
                    // Poll again after interval
                    setTimeout(pollForCommands, pollInterval);
                }
                
                // Initial pattern
                displayStartPattern();
                
                // Also add a click handler for testing
                canvas.addEventListener('click', (e) => {
                    debug(`Canvas clicked at (${e.clientX}, ${e.clientY})`);
                    
                    // Convert to 0-1000 scale
                    const x = Math.round((e.clientX / canvas.width) * 1000);
                    const y = Math.round((e.clientY / canvas.height) * 1000);
                    
                    highlightPoint(x, y);
                });
                
                // Start polling for commands
                pollForCommands();
            </script>
        </body>
        </html>
        '''

def generate_calibration_points(num_points=9):
    """Generate a grid of calibration points (in relative coordinates 0-1000)"""
    points = []
    rows = int(np.sqrt(num_points))
    cols = int(np.ceil(num_points / rows))
    
    padding = 100  # 10% padding from edges
    
    step_x = (1000 - 2 * padding) / (cols - 1) if cols > 1 else 0
    step_y = (1000 - 2 * padding) / (rows - 1) if rows > 1 else 0
    
    for i in range(rows):
        for j in range(cols):
            if len(points) < num_points:
                x = padding + j * step_x
                y = padding + i * step_y
                points.append((int(x), int(y)))
    
    return points

def compute_homography():
    """Compute the homography matrix from collected points"""
    global global_state
    
    if len(global_state.camera_points) >= 4 and len(global_state.projector_points) >= 4:
        # Convert points to numpy arrays
        src_points = np.array(global_state.camera_points, dtype=np.float32)
        dst_points = np.array(global_state.projector_points, dtype=np.float32)
        
        # Compute homography matrix that maps camera points to projector points
        H, status = cv2.findHomography(src_points, dst_points)
        
        if H is not None:
            global_state.homography_matrix = H
            global_state.is_calibrated = True
            print("Homography computed successfully:")
            print(H)
            return True
    
    print("Failed to compute homography")
    return False

def transform_point(camera_x, camera_y):
    """Transform a camera point to projector coordinates using homography"""
    global global_state
    
    if not global_state.is_calibrated:
        # Fallback to simple scaling if not calibrated
        return int(camera_x * 1.5), int(camera_y * 1.5)
    
    # Apply homography transformation
    point = np.array([[[camera_x, camera_y]]], dtype=np.float32)
    transformed = cv2.perspectiveTransform(point, global_state.homography_matrix)
    proj_x, proj_y = transformed[0][0]
    
    return int(proj_x), int(proj_y)

def run_server(port=5000):
    """Run the web server for calibration"""
    # Create server
    server = HTTPServer(('', port), WebcamHandler)
    print(f"Starting server at http://localhost:{port}")
    print("Press Ctrl+C to stop the server")
    
    # Open browser automatically
    webbrowser.open(f"http://localhost:{port}")
    
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("Server stopped by user")
        server.server_close()

# Run the server when script is executed
if __name__ == "__main__":
    run_server()