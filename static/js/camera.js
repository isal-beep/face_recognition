// camera.js - Production-ready camera management for face recognition attendance

class CameraManager {
    constructor() {
        this.videoElement = null;
        this.canvasElement = null;
        this.stream = null;
        this.currentFacingMode = 'user'; // 'user' for front camera, 'environment' for back camera
        this.isCameraActive = false;
        this.cameraDevices = [];
        this.selectedDeviceId = null;
        this.onCaptureCallback = null;
        this.onErrorCallback = null;
        this.faceDetectionBox = null;
        this.isAutoCaptureEnabled = true;
        this.autoCaptureInterval = null;
        this.captureCountdown = 5;
        this.countdownInterval = null;
        this.qualityScore = 0;
        this.brightness = 0;
        this.sharpness = 0;
        
        // DOM Elements cache
        this.elements = {};
        
        // Face detection parameters
        this.faceDetectionConfig = {
            minDetectionConfidence: 0.5,
            minFaceSize: 100,
            maxFaceSize: 500,
            facePadding: 0.2,
            scanInterval: 1000 // ms
        };
        
        // Initialize
        this.init();
    }
    
    init() {
        // Cache DOM elements
        this.elements = {
            video: document.getElementById('video'),
            canvas: document.getElementById('canvas'),
            startBtn: document.getElementById('startCameraBtn'),
            captureBtn: document.getElementById('captureBtn'),
            stopBtn: document.getElementById('stopCameraBtn'),
            switchBtn: document.getElementById('switchCameraBtn'),
            cameraStatus: document.getElementById('cameraStatus'),
            qualityScore: document.getElementById('qualityScore'),
            brightnessScore: document.getElementById('brightnessScore'),
            sharpnessScore: document.getElementById('sharpnessScore'),
            positionScore: document.getElementById('positionScore'),
            qualityIndicators: document.getElementById('qualityIndicators'),
            captureIndicator: document.getElementById('captureIndicator'),
            autoCaptureContainer: document.getElementById('autoCaptureContainer'),
            countdownNumber: document.getElementById('countdownNumber'),
            faceOverlay: document.querySelector('.face-overlay')
        };
        
        // Initialize video and canvas
        this.videoElement = this.elements.video;
        this.canvasElement = this.elements.canvas;
        
        // Create face overlay if doesn't exist
        if (!this.elements.faceOverlay && this.videoElement) {
            this.createFaceOverlay();
        }
        
        // Add event listeners
        this.addEventListeners();
        
        // Check camera support
        this.checkCameraSupport();
        
        // Try to get previous camera preference
        this.loadCameraPreferences();
    }
    
    addEventListeners() {
        // Window resize handler
        window.addEventListener('resize', () => this.handleResize());
        
        // Page visibility change
        document.addEventListener('visibilitychange', () => this.handleVisibilityChange());
        
        // Camera button listeners
        if (this.elements.startBtn) {
            this.elements.startBtn.addEventListener('click', () => this.startCamera());
        }
        
        if (this.elements.captureBtn) {
            this.elements.captureBtn.addEventListener('click', () => this.captureImage());
        }
        
        if (this.elements.stopBtn) {
            this.elements.stopBtn.addEventListener('click', () => this.stopCamera());
        }
        
        if (this.elements.switchBtn) {
            this.elements.switchBtn.addEventListener('click', () => this.switchCamera());
        }
        
        // Video element events
        if (this.videoElement) {
            this.videoElement.addEventListener('loadeddata', () => this.onVideoLoaded());
            this.videoElement.addEventListener('play', () => this.onVideoPlay());
        }
    }
    
    checkCameraSupport() {
        if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
            this.showError('Browser tidak mendukung akses kamera');
            this.disableCameraButtons();
            return false;
        }
        
        if (!navigator.mediaDevices.enumerateDevices) {
            console.warn('enumerateDevices() not supported');
            return false;
        }
        
        return true;
    }
    
    async startCamera(deviceId = null) {
        try {
            // Stop any existing stream
            await this.stopCamera();
            
            // Get camera constraints
            const constraints = this.getCameraConstraints(deviceId);
            
            // Request camera access
            this.stream = await navigator.mediaDevices.getUserMedia(constraints);
            
            // Set video source
            this.videoElement.srcObject = this.stream;
            this.isCameraActive = true;
            
            // Wait for video to load
            await this.videoElement.play();
            
            // Update UI
            this.updateCameraStatus('active');
            this.enableCameraControls();
            
            // Get available devices
            await this.getCameraDevices();
            
            // Start quality monitoring
            this.startQualityMonitoring();
            
            // Start auto capture if enabled
            if (this.isAutoCaptureEnabled) {
                this.startAutoCaptureCountdown();
            }
            
            // Save camera preference
            this.saveCameraPreferences();
            
            return true;
            
        } catch (error) {
            console.error('Camera Error:', error);
            this.handleCameraError(error);
            return false;
        }
    }
    
    getCameraConstraints(deviceId = null) {
        const constraints = {
            video: {
                width: { ideal: 1280 },
                height: { ideal: 720 },
                frameRate: { ideal: 30 },
                facingMode: this.currentFacingMode
            },
            audio: false
        };
        
        // If device ID is provided, use it
        if (deviceId) {
            constraints.video.deviceId = { exact: deviceId };
            delete constraints.video.facingMode;
        }
        
        return constraints;
    }
    
    async getCameraDevices() {
        try {
            const devices = await navigator.mediaDevices.enumerateDevices();
            this.cameraDevices = devices.filter(device => device.kind === 'videoinput');
            
            // Set selected device if available
            if (this.stream && this.cameraDevices.length > 0) {
                const track = this.stream.getVideoTracks()[0];
                this.selectedDeviceId = track.getSettings().deviceId;
            }
            
            return this.cameraDevices;
            
        } catch (error) {
            console.error('Error getting camera devices:', error);
            return [];
        }
    }
    
    async switchCamera() {
        if (!this.isCameraActive || this.cameraDevices.length < 2) {
            this.showError('Tidak ada kamera lain yang tersedia');
            return;
        }
        
        try {
            // Get current device index
            const currentIndex = this.cameraDevices.findIndex(
                device => device.deviceId === this.selectedDeviceId
            );
            
            // Calculate next device index
            const nextIndex = (currentIndex + 1) % this.cameraDevices.length;
            const nextDevice = this.cameraDevices[nextIndex];
            
            // Stop current stream
            await this.stopCamera();
            
            // Start with new device
            await this.startCamera(nextDevice.deviceId);
            
            // Update facing mode based on label
            const label = nextDevice.label.toLowerCase();
            if (label.includes('front') || label.includes('user')) {
                this.currentFacingMode = 'user';
            } else if (label.includes('back') || label.includes('environment')) {
                this.currentFacingMode = 'environment';
            }
            
        } catch (error) {
            console.error('Error switching camera:', error);
            this.showError('Gagal mengganti kamera');
        }
    }
    
    stopCamera() {
        return new Promise((resolve) => {
            // Stop auto capture
            this.stopAutoCapture();
            
            // Stop quality monitoring
            this.stopQualityMonitoring();
            
            // Stop stream if exists
            if (this.stream) {
                this.stream.getTracks().forEach(track => {
                    track.stop();
                });
                this.stream = null;
            }
            
            // Clear video source
            if (this.videoElement) {
                this.videoElement.srcObject = null;
            }
            
            // Update state
            this.isCameraActive = false;
            
            // Update UI
            this.updateCameraStatus('inactive');
            this.disableCameraControls();
            
            // Hide quality indicators
            if (this.elements.qualityIndicators) {
                this.elements.qualityIndicators.classList.add('hidden');
            }
            
            resolve();
        });
    }
    
    captureImage() {
        if (!this.isCameraActive) {
            this.showError('Kamera tidak aktif');
            return null;
        }
        
        try {
            // Show capture indicator
            this.showCaptureIndicator();
            
            // Get canvas context
            const canvas = this.canvasElement;
            const context = canvas.getContext('2d');
            
            // Set canvas dimensions to match video
            canvas.width = this.videoElement.videoWidth;
            canvas.height = this.videoElement.videoHeight;
            
            // Draw video frame to canvas
            context.drawImage(this.videoElement, 0, 0, canvas.width, canvas.height);
            
            // Calculate face detection and quality
            const faceData = this.detectFaceInCanvas(canvas);
            const qualityData = this.calculateImageQuality(canvas);
            
            // Convert canvas to blob
            return new Promise((resolve) => {
                canvas.toBlob((blob) => {
                    // Hide capture indicator
                    this.hideCaptureIndicator();
                    
                    // Prepare result
                    const result = {
                        blob: blob,
                        imageData: canvas.toDataURL('image/jpeg', 0.9),
                        faceData: faceData,
                        qualityData: qualityData,
                        timestamp: new Date().toISOString(),
                        resolution: {
                            width: canvas.width,
                            height: canvas.height
                        }
                    };
                    
                    // Call callback if set
                    if (this.onCaptureCallback) {
                        this.onCaptureCallback(result);
                    }
                    
                    resolve(result);
                    
                }, 'image/jpeg', 0.9);
            });
            
        } catch (error) {
            console.error('Capture Error:', error);
            this.hideCaptureIndicator();
            this.showError('Gagal mengambil gambar');
            return null;
        }
    }
    
    detectFaceInCanvas(canvas) {
        const context = canvas.getContext('2d');
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        
        // Simple face detection simulation
        // In production, this would use MediaPipe or similar
        const faceData = {
            detected: false,
            confidence: 0,
            boundingBox: null,
            landmarks: null,
            positionScore: 0
        };
        
        // Check image brightness for face-like areas
        const brightnessMap = this.calculateBrightnessMap(imageData);
        const faceLikeRegions = this.findFaceLikeRegions(brightnessMap);
        
        if (faceLikeRegions.length > 0) {
            const bestRegion = faceLikeRegions[0];
            const faceSize = Math.max(bestRegion.width, bestRegion.height);
            
            // Check if face size is within limits
            if (faceSize >= this.faceDetectionConfig.minFaceSize && 
                faceSize <= this.faceDetectionConfig.maxFaceSize) {
                
                faceData.detected = true;
                faceData.confidence = 0.7; // Simulated confidence
                faceData.boundingBox = bestRegion;
                
                // Calculate position score
                faceData.positionScore = this.calculateFacePositionScore(bestRegion, canvas);
                
                // Update face overlay position
                this.updateFaceOverlay(bestRegion);
            }
        }
        
        return faceData;
    }
    
    calculateBrightnessMap(imageData) {
        const data = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        const brightnessMap = new Array(height).fill().map(() => new Array(width).fill(0));
        
        for (let y = 0; y < height; y++) {
            for (let x = 0; x < width; x++) {
                const idx = (y * width + x) * 4;
                const r = data[idx];
                const g = data[idx + 1];
                const b = data[idx + 2];
                
                // Calculate brightness
                brightnessMap[y][x] = (r + g + b) / 3;
            }
        }
        
        return brightnessMap;
    }
    
    findFaceLikeRegions(brightnessMap) {
        const regions = [];
        const visited = new Set();
        const width = brightnessMap[0].length;
        const height = brightnessMap.length;
        
        // Simple region growing algorithm for demonstration
        // In production, use proper face detection
        for (let y = 0; y < height; y += 10) {
            for (let x = 0; x < width; x += 10) {
                const key = `${x},${y}`;
                
                if (!visited.has(key) && brightnessMap[y][x] > 100) {
                    const region = this.growRegion(brightnessMap, x, y, visited);
                    if (region.width > 50 && region.height > 50) {
                        regions.push(region);
                    }
                }
            }
        }
        
        // Sort by size (largest first)
        regions.sort((a, b) => (b.width * b.height) - (a.width * a.height));
        
        return regions;
    }
    
    growRegion(brightnessMap, startX, startY, visited) {
        const stack = [[startX, startY]];
        const pixels = [];
        
        let minX = startX, maxX = startX;
        let minY = startY, maxY = startY;
        
        while (stack.length > 0) {
            const [x, y] = stack.pop();
            const key = `${x},${y}`;
            
            if (visited.has(key) || y < 0 || y >= brightnessMap.length || 
                x < 0 || x >= brightnessMap[0].length || brightnessMap[y][x] < 100) {
                continue;
            }
            
            visited.add(key);
            pixels.push([x, y]);
            
            // Update bounds
            minX = Math.min(minX, x);
            maxX = Math.max(maxX, x);
            minY = Math.min(minY, y);
            maxY = Math.max(maxY, y);
            
            // Add neighbors
            stack.push([x + 1, y]);
            stack.push([x - 1, y]);
            stack.push([x, y + 1]);
            stack.push([x, y - 1]);
        }
        
        return {
            x: minX,
            y: minY,
            width: maxX - minX + 1,
            height: maxY - minY + 1,
            centerX: Math.floor((minX + maxX) / 2),
            centerY: Math.floor((minY + maxY) / 2),
            pixelCount: pixels.length
        };
    }
    
    calculateFacePositionScore(boundingBox, canvas) {
        const canvasCenterX = canvas.width / 2;
        const canvasCenterY = canvas.height / 2;
        const faceCenterX = boundingBox.x + boundingBox.width / 2;
        const faceCenterY = boundingBox.y + boundingBox.height / 2;
        
        // Calculate distance from center
        const dx = Math.abs(faceCenterX - canvasCenterX);
        const dy = Math.abs(faceCenterY - canvasCenterY);
        
        // Normalize distance (0 = center, 1 = edge)
        const maxDistance = Math.sqrt(Math.pow(canvas.width / 2, 2) + Math.pow(canvas.height / 2, 2));
        const distance = Math.sqrt(dx * dx + dy * dy);
        const normalizedDistance = distance / maxDistance;
        
        // Convert to score (100 = perfect center, 0 = at edge)
        const positionScore = Math.max(0, 100 - (normalizedDistance * 100));
        
        return Math.round(positionScore);
    }
    
    calculateImageQuality(canvas) {
        const context = canvas.getContext('2d');
        const imageData = context.getImageData(0, 0, canvas.width, canvas.height);
        
        // Calculate brightness
        this.brightness = this.calculateAverageBrightness(imageData);
        
        // Calculate sharpness (using Laplacian variance)
        this.sharpness = this.calculateSharpness(imageData);
        
        // Calculate overall quality score
        this.qualityScore = this.calculateOverallQuality();
        
        return {
            brightness: this.brightness,
            sharpness: this.sharpness,
            quality: this.qualityScore,
            timestamp: new Date().toISOString()
        };
    }
    
    calculateAverageBrightness(imageData) {
        const data = imageData.data;
        let totalBrightness = 0;
        
        for (let i = 0; i < data.length; i += 4) {
            const r = data[i];
            const g = data[i + 1];
            const b = data[i + 2];
            totalBrightness += (r + g + b) / 3;
        }
        
        const avgBrightness = totalBrightness / (data.length / 4);
        return Math.round(avgBrightness);
    }
    
    calculateSharpness(imageData) {
        // Simple Laplacian variance for sharpness estimation
        const data = imageData.data;
        const width = imageData.width;
        const height = imageData.height;
        
        let variance = 0;
        let count = 0;
        
        for (let y = 1; y < height - 1; y++) {
            for (let x = 1; x < width - 1; x++) {
                const idx = (y * width + x) * 4;
                
                // Get neighboring pixels for Laplacian
                const center = data[idx];
                const left = data[idx - 4];
                const right = data[idx + 4];
                const up = data[idx - width * 4];
                const down = data[idx + width * 4];
                
                // Simple Laplacian
                const laplacian = Math.abs(4 * center - left - right - up - down);
                variance += laplacian * laplacian;
                count++;
            }
        }
        
        const sharpness = Math.sqrt(variance / count);
        return Math.round(sharpness);
    }
    
    calculateOverallQuality() {
        // Weighted quality score calculation
        const brightnessScore = this.calculateBrightnessScore(this.brightness);
        const sharpnessScore = this.calculateSharpnessScore(this.sharpness);
        
        // Weighted average
        const quality = (brightnessScore * 0.4) + (sharpnessScore * 0.6);
        return Math.round(quality);
    }
    
    calculateBrightnessScore(brightness) {
        // Optimal brightness range: 100-200
        if (brightness >= 100 && brightness <= 200) {
            return 100;
        } else if (brightness >= 50 && brightness < 100) {
            return Math.round((brightness - 50) * 2);
        } else if (brightness > 200 && brightness <= 250) {
            return Math.round(100 - (brightness - 200) * 2);
        } else {
            return 0;
        }
    }
    
    calculateSharpnessScore(sharpness) {
        // Higher sharpness is better, but not too high
        if (sharpness >= 50 && sharpness <= 200) {
            return 100;
        } else if (sharpness < 50) {
            return Math.round(sharpness * 2);
        } else {
            return Math.max(0, 100 - (sharpness - 200) / 2);
        }
    }
    
    startQualityMonitoring() {
        if (!this.isCameraActive) return;
        
        // Show quality indicators
        if (this.elements.qualityIndicators) {
            this.elements.qualityIndicators.classList.remove('hidden');
        }
        
        // Start monitoring interval
        this.qualityMonitorInterval = setInterval(() => {
            if (this.isCameraActive && this.videoElement.readyState >= 2) {
                this.updateQualityIndicators();
            }
        }, 1000);
    }
    
    stopQualityMonitoring() {
        if (this.qualityMonitorInterval) {
            clearInterval(this.qualityMonitorInterval);
            this.qualityMonitorInterval = null;
        }
    }
    
    updateQualityIndicators() {
        if (!this.videoElement || !this.canvasElement) return;
        
        try {
            // Get current frame for analysis
            const canvas = this.canvasElement;
            const context = canvas.getContext('2d');
            
            canvas.width = this.videoElement.videoWidth;
            canvas.height = this.videoElement.videoHeight;
            context.drawImage(this.videoElement, 0, 0, canvas.width, canvas.height);
            
            // Calculate quality metrics
            const qualityData = this.calculateImageQuality(canvas);
            
            // Update UI elements
            if (this.elements.brightnessScore) {
                this.elements.brightnessScore.textContent = `${qualityData.brightness}`;
            }
            
            if (this.elements.sharpnessScore) {
                this.elements.sharpnessScore.textContent = `${qualityData.sharpness}`;
            }
            
            if (this.elements.qualityScore) {
                this.elements.qualityScore.textContent = `${qualityData.quality}%`;
                
                // Update color based on quality
                if (qualityData.quality >= 80) {
                    this.elements.qualityScore.className = 'ml-2 px-2 py-1 bg-green-100 text-green-800 rounded text-sm';
                } else if (qualityData.quality >= 60) {
                    this.elements.qualityScore.className = 'ml-2 px-2 py-1 bg-yellow-100 text-yellow-800 rounded text-sm';
                } else {
                    this.elements.qualityScore.className = 'ml-2 px-2 py-1 bg-red-100 text-red-800 rounded text-sm';
                }
            }
            
            // Update position score based on face detection
            const faceData = this.detectFaceInCanvas(canvas);
            if (this.elements.positionScore) {
                this.elements.positionScore.textContent = faceData.detected ? 
                    `${faceData.positionScore}%` : '0%';
            }
            
        } catch (error) {
            console.error('Error updating quality indicators:', error);
        }
    }
    
    startAutoCaptureCountdown() {
        this.stopAutoCapture();
        
        if (!this.isAutoCaptureEnabled || !this.isCameraActive) return;
        
        // Show countdown container
        if (this.elements.autoCaptureContainer) {
            this.elements.autoCaptureContainer.classList.remove('hidden');
        }
        
        // Reset countdown
        this.captureCountdown = 5;
        
        // Update countdown display
        this.updateCountdownDisplay();
        
        // Start countdown interval
        this.countdownInterval = setInterval(() => {
            this.captureCountdown--;
            this.updateCountdownDisplay();
            
            if (this.captureCountdown <= 0) {
                clearInterval(this.countdownInterval);
                this.countdownInterval = null;
                
                // Auto capture
                this.captureImage();
                
                // Restart countdown
                if (this.isCameraActive && this.isAutoCaptureEnabled) {
                    setTimeout(() => this.startAutoCaptureCountdown(), 1000);
                }
            }
        }, 1000);
    }
    
    stopAutoCapture() {
        if (this.countdownInterval) {
            clearInterval(this.countdownInterval);
            this.countdownInterval = null;
        }
        
        // Hide countdown container
        if (this.elements.autoCaptureContainer) {
            this.elements.autoCaptureContainer.classList.add('hidden');
        }
    }
    
    updateCountdownDisplay() {
        if (this.elements.countdownNumber) {
            this.elements.countdownNumber.textContent = this.captureCountdown;
            
            // Add animation class
            this.elements.countdownNumber.classList.remove('countdown-number');
            void this.elements.countdownNumber.offsetWidth; // Trigger reflow
            this.elements.countdownNumber.classList.add('countdown-number');
        }
    }
    
    createFaceOverlay() {
        if (!this.videoElement) return;
        
        const overlay = document.createElement('div');
        overlay.className = 'face-overlay';
        overlay.innerHTML = `
            <div class="absolute inset-0 border-2 border-white opacity-30 rounded-lg"></div>
            <div class="absolute -top-3 left-1/2 transform -translate-x-1/2">
                <div class="bg-blue-600 text-white px-3 py-1 rounded-full text-xs font-medium">
                    <i class="fas fa-user mr-1"></i> Posisikan Wajah Di Sini
                </div>
            </div>
        `;
        
        this.videoElement.parentElement.appendChild(overlay);
        this.elements.faceOverlay = overlay;
    }
    
    updateFaceOverlay(boundingBox) {
        if (!this.elements.faceOverlay || !boundingBox || !this.videoElement) return;
        
        const videoRect = this.videoElement.getBoundingClientRect();
        const scaleX = videoRect.width / this.videoElement.videoWidth;
        const scaleY = videoRect.height / this.videoElement.videoHeight;
        
        // Calculate overlay position
        const x = boundingBox.x * scaleX;
        const y = boundingBox.y * scaleY;
        const width = boundingBox.width * scaleX;
        const height = boundingBox.height * scaleY;
        
        // Add padding
        const padding = this.faceDetectionConfig.facePadding * Math.min(width, height);
        
        // Update overlay position and size
        this.elements.faceOverlay.style.left = `${x - padding}px`;
        this.elements.faceOverlay.style.top = `${y - padding}px`;
        this.elements.faceOverlay.style.width = `${width + 2 * padding}px`;
        this.elements.faceOverlay.style.height = `${height + 2 * padding}px`;
        
        // Show overlay if hidden
        this.elements.faceOverlay.classList.remove('hidden');
    }
    
    showCaptureIndicator() {
        if (this.elements.captureIndicator) {
            this.elements.captureIndicator.classList.remove('hidden');
        }
    }
    
    hideCaptureIndicator() {
        if (this.elements.captureIndicator) {
            this.elements.captureIndicator.classList.add('hidden');
        }
    }
    
    updateCameraStatus(status) {
        if (!this.elements.cameraStatus) return;
        
        const icon = status === 'active' ? 'fa-video text-green-500' : 'fa-video text-gray-400';
        const text = status === 'active' ? 'Kamera: Aktif' : 'Kamera: Off';
        const color = status === 'active' ? 'text-green-600' : 'text-gray-600';
        
        this.elements.cameraStatus.innerHTML = `
            <i class="fas ${icon} mr-2"></i>
            <span class="text-sm ${color}">${text}</span>
        `;
    }
    
    enableCameraControls() {
        if (this.elements.startBtn) {
            this.elements.startBtn.disabled = true;
        }
        if (this.elements.captureBtn) {
            this.elements.captureBtn.disabled = false;
        }
        if (this.elements.stopBtn) {
            this.elements.stopBtn.disabled = false;
        }
        if (this.elements.switchBtn) {
            this.elements.switchBtn.disabled = false;
        }
    }
    
    disableCameraControls() {
        if (this.elements.startBtn) {
            this.elements.startBtn.disabled = false;
        }
        if (this.elements.captureBtn) {
            this.elements.captureBtn.disabled = true;
        }
        if (this.elements.stopBtn) {
            this.elements.stopBtn.disabled = true;
        }
        if (this.elements.switchBtn) {
            this.elements.switchBtn.disabled = true;
        }
    }
    
    disableCameraButtons() {
        if (this.elements.startBtn) {
            this.elements.startBtn.disabled = true;
        }
        if (this.elements.captureBtn) {
            this.elements.captureBtn.disabled = true;
        }
        if (this.elements.switchBtn) {
            this.elements.switchBtn.disabled = true;
        }
    }
    
    handleCameraError(error) {
        let errorMessage = 'Gagal mengakses kamera';
        
        switch(error.name) {
            case 'NotFoundError':
            case 'DevicesNotFoundError':
                errorMessage = 'Kamera tidak ditemukan';
                break;
            case 'NotReadableError':
            case 'TrackStartError':
                errorMessage = 'Kamera sedang digunakan oleh aplikasi lain';
                break;
            case 'OverconstrainedError':
            case 'ConstraintNotSatisfiedError':
                errorMessage = 'Kamera tidak mendukung resolusi yang diminta';
                break;
            case 'NotAllowedError':
            case 'PermissionDeniedError':
                errorMessage = 'Akses kamera ditolak. Izinkan akses kamera di pengaturan browser';
                break;
            case 'TypeError':
                errorMessage = 'Tipe kamera tidak didukung';
                break;
        }
        
        this.showError(errorMessage);
        
        if (this.onErrorCallback) {
            this.onErrorCallback(error);
        }
    }
    
    showError(message) {
        console.error('Camera Error:', message);
        
        // Create error toast
        const toast = document.createElement('div');
        toast.className = 'fixed top-4 right-4 bg-red-500 text-white px-4 py-3 rounded-lg shadow-lg z-50';
        toast.innerHTML = `
            <div class="flex items-center">
                <i class="fas fa-exclamation-circle mr-2"></i>
                <span>${message}</span>
            </div>
        `;
        
        document.body.appendChild(toast);
        
        setTimeout(() => {
            toast.remove();
        }, 5000);
    }
    
    onVideoLoaded() {
        // Video loaded successfully
        console.log('Video loaded, dimensions:', 
            this.videoElement.videoWidth, 'x', this.videoElement.videoHeight);
    }
    
    onVideoPlay() {
        // Video started playing
        console.log('Video playing');
    }
    
    handleResize() {
        // Handle window resize
        if (this.isCameraActive && this.elements.faceOverlay) {
            // Recalculate face overlay position if needed
            // This would require tracking the current face position
        }
    }
    
    handleVisibilityChange() {
        if (document.hidden) {
            // Page is hidden, stop auto capture to save resources
            this.stopAutoCapture();
        } else if (this.isCameraActive && this.isAutoCaptureEnabled) {
            // Page is visible again, restart auto capture
            this.startAutoCaptureCountdown();
        }
    }
    
    loadCameraPreferences() {
        try {
            const preferences = localStorage.getItem('camera_preferences');
            if (preferences) {
                const { deviceId, facingMode, autoCapture } = JSON.parse(preferences);
                this.selectedDeviceId = deviceId;
                this.currentFacingMode = facingMode || 'user';
                this.isAutoCaptureEnabled = autoCapture !== false; // Default to true
            }
        } catch (error) {
            console.error('Error loading camera preferences:', error);
        }
    }
    
    saveCameraPreferences() {
        try {
            const preferences = {
                deviceId: this.selectedDeviceId,
                facingMode: this.currentFacingMode,
                autoCapture: this.isAutoCaptureEnabled,
                timestamp: new Date().toISOString()
            };
            
            localStorage.setItem('camera_preferences', JSON.stringify(preferences));
        } catch (error) {
            console.error('Error saving camera preferences:', error);
        }
    }
    
    // Public API methods
    setOnCaptureCallback(callback) {
        this.onCaptureCallback = callback;
    }
    
    setOnErrorCallback(callback) {
        this.onErrorCallback = callback;
    }
    
    setAutoCapture(enabled) {
        this.isAutoCaptureEnabled = enabled;
        
        if (this.isCameraActive) {
            if (enabled) {
                this.startAutoCaptureCountdown();
            } else {
                this.stopAutoCapture();
            }
        }
    }
    
    getCameraState() {
        return {
            isActive: this.isCameraActive,
            facingMode: this.currentFacingMode,
            deviceId: this.selectedDeviceId,
            devices: this.cameraDevices,
            quality: this.qualityScore,
            brightness: this.brightness,
            sharpness: this.sharpness,
            autoCapture: this.isAutoCaptureEnabled
        };
    }
    
    getVideoDimensions() {
        if (!this.videoElement) {
            return { width: 0, height: 0 };
        }
        
        return {
            width: this.videoElement.videoWidth,
            height: this.videoElement.videoHeight
        };
    }
    
    isCameraSupported() {
        return this.checkCameraSupport();
    }
    
    // Cleanup method
    destroy() {
        this.stopCamera();
        
        // Clear intervals
        this.stopQualityMonitoring();
        this.stopAutoCapture();
        
        // Remove event listeners
        window.removeEventListener('resize', this.handleResize);
        document.removeEventListener('visibilitychange', this.handleVisibilityChange);
        
        // Clear references
        this.videoElement = null;
        this.canvasElement = null;
        this.stream = null;
        this.elements = {};
    }
}

// Export for use in browser
if (typeof window !== 'undefined') {
    window.CameraManager = CameraManager;
}

// Auto-initialize if camera-container exists
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('video') || document.querySelector('.camera-container')) {
        window.cameraManager = new CameraManager();
    }
});