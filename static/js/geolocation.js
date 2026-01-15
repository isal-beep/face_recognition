// geolocation.js - Production-ready geolocation management for attendance system

class GeolocationManager {
    constructor(config = {}) {
        // Configuration
        this.config = {
            radiusMeters: config.radiusMeters || 50,
            highAccuracy: config.highAccuracy !== false,
            timeout: config.timeout || 10000,
            maximumAge: config.maximumAge || 0,
            enableWatch: config.enableWatch !== false,
            watchInterval: config.watchInterval || 30000,
            requireMovement: config.requireMovement !== false,
            companyLat: config.companyLat || -6.2088, // Default: Jakarta
            companyLon: config.companyLon || 106.8456,
            debug: config.debug || false
        };
        
        // State
        this.currentPosition = null;
        this.lastValidPosition = null;
        this.watchId = null;
        this.isGeolocationSupported = false;
        this.isPermissionGranted = false;
        this.isPositioningActive = false;
        this.positionHistory = [];
        this.maxHistorySize = 10;
        
        // Callbacks
        this.onPositionUpdate = null;
        this.onError = null;
        this.onPermissionChange = null;
        this.onWithinRadius = null;
        this.onOutsideRadius = null;
        
        // DOM Elements cache
        this.elements = {};
        
        // Initialize
        this.init();
    }
    
    init() {
        this.log('GeolocationManager initializing...');
        
        // Cache DOM elements
        this.cacheElements();
        
        // Check geolocation support
        this.checkGeolocationSupport();
        
        // Load saved preferences
        this.loadPreferences();
        
        // Set up event listeners
        this.setupEventListeners();
        
        // Initialize UI
        this.updateUI();
    }
    
    cacheElements() {
        // Try to find common GPS status elements
        this.elements = {
            gpsStatus: document.getElementById('gpsStatus'),
            gpsIndicator: document.getElementById('gpsIndicator'),
            gpsAccuracy: document.getElementById('gpsAccuracy'),
            gpsDistance: document.getElementById('gpsDistance'),
            gpsLatitude: document.getElementById('gpsLatitude'),
            gpsLongitude: document.getElementById('gpsLongitude')
        };
    }
    
    checkGeolocationSupport() {
        this.isGeolocationSupported = 'geolocation' in navigator;
        
        if (!this.isGeolocationSupported) {
            this.log('Geolocation is not supported by this browser');
            this.showError('GPS tidak didukung oleh browser ini');
            this.updateGPSStatus('not-supported');
            return false;
        }
        
        this.log('Geolocation is supported');
        return true;
    }
    
    async getCurrentPosition(options = {}) {
        return new Promise((resolve, reject) => {
            if (!this.isGeolocationSupported) {
                reject(new Error('Geolocation not supported'));
                return;
            }
            
            const defaultOptions = {
                enableHighAccuracy: this.config.highAccuracy,
                timeout: this.config.timeout,
                maximumAge: this.config.maximumAge
            };
            
            const mergedOptions = { ...defaultOptions, ...options };
            
            this.log('Requesting current position...', mergedOptions);
            this.updateGPSStatus('requesting');
            
            navigator.geolocation.getCurrentPosition(
                (position) => {
                    this.handlePositionSuccess(position);
                    resolve(position);
                },
                (error) => {
                    this.handlePositionError(error);
                    reject(error);
                },
                mergedOptions
            );
        });
    }
    
    startWatching(options = {}) {
        if (!this.isGeolocationSupported) {
            this.log('Cannot start watching: Geolocation not supported');
            return null;
        }
        
        if (this.watchId) {
            this.log('Already watching position');
            return this.watchId;
        }
        
        const defaultOptions = {
            enableHighAccuracy: this.config.highAccuracy,
            timeout: this.config.timeout,
            maximumAge: this.config.maximumAge
        };
        
        const watchOptions = { ...defaultOptions, ...options };
        
        this.log('Starting position watch...', watchOptions);
        this.isPositioningActive = true;
        this.updateGPSStatus('active');
        
        this.watchId = navigator.geolocation.watchPosition(
            (position) => this.handlePositionSuccess(position),
            (error) => this.handlePositionError(error),
            watchOptions
        );
        
        return this.watchId;
    }
    
    stopWatching() {
        if (this.watchId) {
            navigator.geolocation.clearWatch(this.watchId);
            this.watchId = null;
            this.isPositioningActive = false;
            this.log('Position watching stopped');
            this.updateGPSStatus('inactive');
        }
    }
    
    handlePositionSuccess(position) {
        this.log('Position acquired:', position);
        
        // Store position
        this.currentPosition = this.normalizePosition(position);
        this.lastValidPosition = this.currentPosition;
        
        // Add to history
        this.addToHistory(this.currentPosition);
        
        // Check if within company radius
        const distance = this.calculateDistance(
            this.currentPosition.coords.latitude,
            this.currentPosition.coords.longitude,
            this.config.companyLat,
            this.config.companyLon
        );
        
        const isWithinRadius = distance <= this.config.radiusMeters;
        
        // Update position data
        this.currentPosition.distance = distance;
        this.currentPosition.isWithinRadius = isWithinRadius;
        this.currentPosition.accuracyStatus = this.getAccuracyStatus(
            this.currentPosition.coords.accuracy
        );
        
        // Update UI
        this.updateUI();
        
        // Call callbacks
        if (this.onPositionUpdate) {
            this.onPositionUpdate(this.currentPosition);
        }
        
        if (isWithinRadius && this.onWithinRadius) {
            this.onWithinRadius(this.currentPosition);
        } else if (!isWithinRadius && this.onOutsideRadius) {
            this.onOutsideRadius(this.currentPosition);
        }
        
        // Update permission status
        this.isPermissionGranted = true;
        if (this.onPermissionChange) {
            this.onPermissionChange(true);
        }
        
        return this.currentPosition;
    }
    
    handlePositionError(error) {
        this.log('Position error:', error);
        
        let errorMessage = 'Gagal mendapatkan lokasi';
        let errorType = 'unknown';
        
        switch(error.code) {
            case error.PERMISSION_DENIED:
                errorMessage = 'Izin lokasi ditolak. Aktifkan GPS di pengaturan browser.';
                errorType = 'permission-denied';
                this.isPermissionGranted = false;
                if (this.onPermissionChange) {
                    this.onPermissionChange(false);
                }
                break;
                
            case error.POSITION_UNAVAILABLE:
                errorMessage = 'Informasi lokasi tidak tersedia';
                errorType = 'position-unavailable';
                break;
                
            case error.TIMEOUT:
                errorMessage = 'Permintaan lokasi timeout';
                errorType = 'timeout';
                break;
        }
        
        // Update UI with error
        this.updateGPSStatus('error', errorMessage);
        
        // Call error callback
        if (this.onError) {
            this.onError({
                code: error.code,
                message: errorMessage,
                type: errorType,
                timestamp: new Date().toISOString()
            });
        }
        
        // Show error to user if not already shown
        this.showError(errorMessage, errorType);
    }
    
    normalizePosition(position) {
        return {
            coords: {
                latitude: position.coords.latitude,
                longitude: position.coords.longitude,
                accuracy: position.coords.accuracy,
                altitude: position.coords.altitude,
                altitudeAccuracy: position.coords.altitudeAccuracy,
                heading: position.coords.heading,
                speed: position.coords.speed
            },
            timestamp: position.timestamp || new Date().getTime(),
            source: 'geolocation'
        };
    }
    
    addToHistory(position) {
        this.positionHistory.unshift(position);
        
        // Limit history size
        if (this.positionHistory.length > this.maxHistorySize) {
            this.positionHistory.pop();
        }
    }
    
    calculateDistance(lat1, lon1, lat2, lon2) {
        // Haversine formula
        const R = 6371000; // Earth's radius in meters
        
        const toRad = (degrees) => degrees * (Math.PI / 180);
        
        const φ1 = toRad(lat1);
        const φ2 = toRad(lat2);
        const Δφ = toRad(lat2 - lat1);
        const Δλ = toRad(lon2 - lon1);
        
        const a = Math.sin(Δφ/2) * Math.sin(Δφ/2) +
                  Math.cos(φ1) * Math.cos(φ2) *
                  Math.sin(Δλ/2) * Math.sin(Δλ/2);
        
        const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
        
        const distance = R * c;
        
        this.log(`Distance calculated: ${distance.toFixed(2)}m`);
        return distance;
    }
    
    isWithinCompanyRadius(lat, lon) {
        if (!lat || !lon) {
            return this.currentPosition ? this.currentPosition.isWithinRadius : false;
        }
        
        const distance = this.calculateDistance(
            lat,
            lon,
            this.config.companyLat,
            this.config.companyLon
        );
        
        return distance <= this.config.radiusMeters;
    }
    
    getAccuracyStatus(accuracy) {
        if (accuracy <= 10) return 'excellent';
        if (accuracy <= 25) return 'good';
        if (accuracy <= 50) return 'fair';
        if (accuracy <= 100) return 'poor';
        return 'very-poor';
    }
    
    updateUI() {
        if (!this.currentPosition) return;
        
        const position = this.currentPosition;
        const distance = position.distance || this.calculateDistance(
            position.coords.latitude,
            position.coords.longitude,
            this.config.companyLat,
            this.config.companyLon
        );
        
        const isWithinRadius = distance <= this.config.radiusMeters;
        const accuracyStatus = this.getAccuracyStatus(position.coords.accuracy);
        
        // Update GPS status element
        if (this.elements.gpsStatus) {
            const statusClass = isWithinRadius ? 'text-green-600' : 'text-red-600';
            const statusIcon = isWithinRadius ? 'fa-check-circle' : 'fa-times-circle';
            const statusText = isWithinRadius ? 'Dalam Radius' : 'Di Luar Radius';
            
            this.elements.gpsStatus.innerHTML = `
                <i class="fas ${statusIcon} mr-2 ${statusClass}"></i>
                <span class="text-sm ${statusClass}">GPS: ${statusText}</span>
            `;
        }
        
        // Update GPS indicator
        if (this.elements.gpsIndicator) {
            const indicatorClass = isWithinRadius ? 'bg-green-500' : 'bg-red-500';
            this.elements.gpsIndicator.className = `status-dot ${indicatorClass}`;
        }
        
        // Update accuracy display
        if (this.elements.gpsAccuracy) {
            const accuracyColors = {
                'excellent': 'text-green-600',
                'good': 'text-green-500',
                'fair': 'text-yellow-500',
                'poor': 'text-orange-500',
                'very-poor': 'text-red-500'
            };
            
            const color = accuracyColors[accuracyStatus] || 'text-gray-500';
            this.elements.gpsAccuracy.innerHTML = `
                <span class="text-xs ${color}">
                    Akurasi: ${position.coords.accuracy.toFixed(1)}m
                </span>
            `;
        }
        
        // Update distance display
        if (this.elements.gpsDistance) {
            const distanceColor = isWithinRadius ? 'text-green-600' : 'text-red-600';
            this.elements.gpsDistance.innerHTML = `
                <span class="text-sm font-medium ${distanceColor}">
                    ${distance.toFixed(0)}m dari lokasi perusahaan
                </span>
            `;
        }
        
        // Update coordinates display
        if (this.elements.gpsLatitude) {
            this.elements.gpsLatitude.textContent = position.coords.latitude.toFixed(6);
        }
        
        if (this.elements.gpsLongitude) {
            this.elements.gpsLongitude.textContent = position.coords.longitude.toFixed(6);
        }
    }
    
    updateGPSStatus(status, message = '') {
        const statusConfig = {
            'active': {
                icon: 'fa-map-marker-alt text-green-500',
                text: 'GPS: Aktif',
                color: 'text-green-600'
            },
            'inactive': {
                icon: 'fa-map-marker-alt text-gray-400',
                text: 'GPS: Nonaktif',
                color: 'text-gray-600'
            },
            'requesting': {
                icon: 'fa-spinner fa-spin text-yellow-500',
                text: 'GPS: Meminta lokasi...',
                color: 'text-yellow-600'
            },
            'error': {
                icon: 'fa-exclamation-circle text-red-500',
                text: message || 'GPS: Error',
                color: 'text-red-600'
            },
            'not-supported': {
                icon: 'fa-times-circle text-red-500',
                text: 'GPS: Tidak didukung',
                color: 'text-red-600'
            }
        };
        
        const config = statusConfig[status] || statusConfig.inactive;
        
        // Update common GPS status element
        if (this.elements.gpsStatus) {
            this.elements.gpsStatus.innerHTML = `
                <i class="fas ${config.icon} mr-2"></i>
                <span class="text-sm ${config.color}">${config.text}</span>
            `;
        }
        
        // Also update any element with id 'gpsStatus' that we might have missed
        const allGpsStatusElements = document.querySelectorAll('[id*="gps"][id*="status"], [id*="gpsStatus"]');
        allGpsStatusElements.forEach(element => {
            if (element !== this.elements.gpsStatus) {
                element.innerHTML = `
                    <i class="fas ${config.icon} mr-2"></i>
                    <span class="text-sm ${config.color}">${config.text}</span>
                `;
            }
        });
    }
    
    async requestPermission() {
        if (!this.isGeolocationSupported) {
            this.showError('Browser tidak mendukung geolocation');
            return false;
        }
        
        try {
            // Try to get position which will trigger permission request
            const position = await this.getCurrentPosition();
            return !!position;
        } catch (error) {
            this.log('Permission request failed:', error);
            
            // Show instructions based on platform
            this.showPermissionInstructions();
            return false;
        }
    }
    
    showPermissionInstructions() {
        const isMobile = /Android|webOS|iPhone|iPad|iPod|BlackBerry|IEMobile|Opera Mini/i.test(navigator.userAgent);
        
        let instructions = '';
        
        if (isMobile) {
            instructions = `
                <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <h4 class="font-bold text-yellow-800 mb-2">Cara Aktifkan GPS di Mobile:</h4>
                    <ul class="text-sm text-yellow-700 space-y-1">
                        <li>1. Buka <strong>Pengaturan</strong> di ponsel Anda</li>
                        <li>2. Pilih <strong>Lokasi/GPS</strong></li>
                        <li>3. Aktifkan <strong>Lokasi</strong></li>
                        <li>4. Kembali ke browser dan refresh halaman</li>
                    </ul>
                </div>
            `;
        } else {
            instructions = `
                <div class="p-4 bg-yellow-50 border border-yellow-200 rounded-lg">
                    <h4 class="font-bold text-yellow-800 mb-2">Cara Izinkan Akses Lokasi di Browser:</h4>
                    <ul class="text-sm text-yellow-700 space-y-1">
                        <li>1. Klik ikon <strong>gembok/gambar</strong> di address bar</li>
                        <li>2. Cari opsi <strong>"Lokasi"</strong> atau <strong>"Location"</strong></li>
                        <li>3. Pilih <strong>"Izinkan"</strong> atau <strong>"Allow"</strong></li>
                        <li>4. Refresh halaman ini</li>
                    </ul>
                </div>
            `;
        }
        
        this.showModal('GPS Tidak Aktif', instructions);
    }
    
    setupEventListeners() {
        // Page visibility change
        document.addEventListener('visibilitychange', () => {
            if (document.hidden) {
                this.onPageHidden();
            } else {
                this.onPageVisible();
            }
        });
        
        // Online/offline status
        window.addEventListener('online', () => this.onConnectionRestored());
        window.addEventListener('offline', () => this.onConnectionLost());
        
        // Window focus/blur
        window.addEventListener('focus', () => this.onWindowFocus());
        window.addEventListener('blur', () => this.onWindowBlur());
    }
    
    onPageHidden() {
        this.log('Page hidden, optimizing GPS usage');
        // Stop high-frequency updates to save battery
        if (this.watchId && this.config.enableWatch) {
            this.stopWatching();
        }
    }
    
    onPageVisible() {
        this.log('Page visible, restoring GPS');
        // Restore GPS monitoring
        if (this.config.enableWatch && this.isPermissionGranted) {
            setTimeout(() => this.startWatching(), 1000);
        }
    }
    
    onConnectionLost() {
        this.log('Connection lost');
        this.updateGPSStatus('error', 'Koneksi internet terputus');
    }
    
    onConnectionRestored() {
        this.log('Connection restored');
        if (this.isPermissionGranted) {
            this.updateGPSStatus('active');
            if (this.config.enableWatch) {
                this.startWatching();
            }
        }
    }
    
    onWindowFocus() {
        this.log('Window focused');
        // Refresh position when window gains focus
        if (this.isPermissionGranted && !this.watchId) {
            this.getCurrentPosition();
        }
    }
    
    onWindowBlur() {
        this.log('Window blurred');
        // Reduce GPS usage when window loses focus
    }
    
    getPositionForAttendance() {
        if (!this.currentPosition) {
            return {
                latitude: null,
                longitude: null,
                accuracy: null,
                timestamp: null,
                isWithinRadius: false,
                isValid: false
            };
        }
        
        return {
            latitude: this.currentPosition.coords.latitude,
            longitude: this.currentPosition.coords.longitude,
            accuracy: this.currentPosition.coords.accuracy,
            timestamp: this.currentPosition.timestamp,
            isWithinRadius: this.currentPosition.isWithinRadius,
            isValid: this.validatePositionForAttendance(this.currentPosition)
        };
    }
    
    validatePositionForAttendance(position) {
        if (!position || !position.coords) return false;
        
        const coords = position.coords;
        
        // Check if coordinates are valid numbers
        if (typeof coords.latitude !== 'number' || 
            typeof coords.longitude !== 'number' ||
            isNaN(coords.latitude) || 
            isNaN(coords.longitude)) {
            return false;
        }
        
        // Check if within valid range
        if (coords.latitude < -90 || coords.latitude > 90 ||
            coords.longitude < -180 || coords.longitude > 180) {
            return false;
        }
        
        // Check accuracy (if available)
        if (coords.accuracy && coords.accuracy > 100) {
            this.log(`Accuracy too low: ${coords.accuracy}m`);
            return false;
        }
        
        // Check if within company radius
        if (!this.isWithinCompanyRadius(coords.latitude, coords.longitude)) {
            return false;
        }
        
        // Check timestamp (not too old)
        const positionAge = Date.now() - position.timestamp;
        if (positionAge > 5 * 60 * 1000) { // 5 minutes
            this.log(`Position too old: ${positionAge}ms`);
            return false;
        }
        
        return true;
    }
    
    getLastValidPosition() {
        return this.lastValidPosition;
    }
    
    getPositionHistory() {
        return [...this.positionHistory];
    }
    
    clearPositionHistory() {
        this.positionHistory = [];
    }
    
    setCompanyLocation(latitude, longitude) {
        if (typeof latitude !== 'number' || typeof longitude !== 'number' ||
            latitude < -90 || latitude > 90 || longitude < -180 || longitude > 180) {
            throw new Error('Invalid coordinates');
        }
        
        this.config.companyLat = latitude;
        this.config.companyLon = longitude;
        
        // Save to preferences
        this.savePreferences();
        
        this.log(`Company location updated to: ${latitude}, ${longitude}`);
        
        // Recalculate current position status
        if (this.currentPosition) {
            this.handlePositionSuccess({
                coords: this.currentPosition.coords,
                timestamp: this.currentPosition.timestamp
            });
        }
    }
    
    setRadius(radiusMeters) {
        if (typeof radiusMeters !== 'number' || radiusMeters <= 0) {
            throw new Error('Invalid radius');
        }
        
        this.config.radiusMeters = radiusMeters;
        this.savePreferences();
        
        this.log(`Radius updated to: ${radiusMeters}m`);
        
        // Recalculate current position status
        if (this.currentPosition) {
            this.handlePositionSuccess({
                coords: this.currentPosition.coords,
                timestamp: this.currentPosition.timestamp
            });
        }
    }
    
    loadPreferences() {
        try {
            const preferences = localStorage.getItem('geolocation_preferences');
            if (preferences) {
                const saved = JSON.parse(preferences);
                
                if (saved.companyLat && saved.companyLon) {
                    this.config.companyLat = saved.companyLat;
                    this.config.companyLon = saved.companyLon;
                }
                
                if (saved.radiusMeters) {
                    this.config.radiusMeters = saved.radiusMeters;
                }
                
                this.log('Preferences loaded from localStorage');
            }
        } catch (error) {
            this.log('Error loading preferences:', error);
        }
    }
    
    savePreferences() {
        try {
            const preferences = {
                companyLat: this.config.companyLat,
                companyLon: this.config.companyLon,
                radiusMeters: this.config.radiusMeters,
                savedAt: new Date().toISOString()
            };
            
            localStorage.setItem('geolocation_preferences', JSON.stringify(preferences));
            this.log('Preferences saved to localStorage');
        } catch (error) {
            this.log('Error saving preferences:', error);
        }
    }
    
    showError(message, type = 'error') {
        this.log(`Error [${type}]: ${message}`);
        
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
        
        // Auto remove
        setTimeout(() => {
            toast.style.opacity = '0';
            toast.style.transform = 'translateY(-20px)';
            setTimeout(() => toast.remove(), 300);
        }, 5000);
    }
    
    showModal(title, content) {
        // Remove existing modal
        const existingModal = document.getElementById('geolocation-modal');
        if (existingModal) existingModal.remove();
        
        // Create modal
        const modal = document.createElement('div');
        modal.id = 'geolocation-modal';
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
                <div class="p-6 border-b">
                    <h3 class="text-xl font-bold text-gray-800">${title}</h3>
                </div>
                <div class="p-6">${content}</div>
                <div class="p-6 border-t flex justify-end">
                    <button onclick="document.getElementById('geolocation-modal').remove()" 
                            class="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium">
                        Tutup
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
    }
    
    log(...args) {
        if (this.config.debug) {
            console.log('[GeolocationManager]', ...args);
        }
    }
    
    // Public API methods
    setOnPositionUpdate(callback) {
        this.onPositionUpdate = callback;
    }
    
    setOnError(callback) {
        this.onError = callback;
    }
    
    setOnPermissionChange(callback) {
        this.onPermissionChange = callback;
    }
    
    setOnWithinRadius(callback) {
        this.onWithinRadius = callback;
    }
    
    setOnOutsideRadius(callback) {
        this.onOutsideRadius = callback;
    }
    
    getCurrentPositionData() {
        return this.currentPosition ? { ...this.currentPosition } : null;
    }
    
    getConfig() {
        return { ...this.config };
    }
    
    getStatus() {
        return {
            isSupported: this.isGeolocationSupported,
            isPermissionGranted: this.isPermissionGranted,
            isPositioningActive: this.isPositioningActive,
            hasValidPosition: !!this.currentPosition,
            isWithinRadius: this.currentPosition ? this.currentPosition.isWithinRadius : false,
            watchId: this.watchId,
            positionHistorySize: this.positionHistory.length
        };
    }
    
    reset() {
        this.stopWatching();
        this.currentPosition = null;
        this.lastValidPosition = null;
        this.positionHistory = [];
        this.isPermissionGranted = false;
        this.isPositioningActive = false;
        this.updateGPSStatus('inactive');
    }
    
    destroy() {
        this.stopWatching();
        
        // Remove event listeners
        document.removeEventListener('visibilitychange', this.onPageHidden);
        document.removeEventListener('visibilitychange', this.onPageVisible);
        window.removeEventListener('online', this.onConnectionRestored);
        window.removeEventListener('offline', this.onConnectionLost);
        window.removeEventListener('focus', this.onWindowFocus);
        window.removeEventListener('blur', this.onWindowBlur);
        
        // Clear references
        this.elements = {};
        this.onPositionUpdate = null;
        this.onError = null;
        this.onPermissionChange = null;
        this.onWithinRadius = null;
        this.onOutsideRadius = null;
    }
}

// Export for browser
if (typeof window !== 'undefined') {
    window.GeolocationManager = GeolocationManager;
}

// Auto-initialize if on attendance page
document.addEventListener('DOMContentLoaded', () => {
    // Check if we're on a page that needs geolocation
    const needsGeolocation = document.getElementById('absen') || 
                            document.querySelector('[data-requires-geolocation]') ||
                            window.location.pathname.includes('absen');
    
    if (needsGeolocation && 'geolocation' in navigator) {
        // Create global instance
        window.geolocationManager = new GeolocationManager({
            radiusMeters: 50,
            highAccuracy: true,
            timeout: 10000,
            enableWatch: true,
            debug: false
        });
        
        // Start watching position
        setTimeout(() => {
            window.geolocationManager.startWatching();
        }, 1000);
        
        // Add GPS status element if not present
        if (!document.getElementById('gpsStatus')) {
            const statusElement = document.createElement('div');
            statusElement.id = 'gpsStatus';
            statusElement.className = 'flex items-center';
            statusElement.innerHTML = `
                <i class="fas fa-map-marker-alt text-gray-400 mr-2"></i>
                <span class="text-sm text-gray-600">GPS: Loading...</span>
            `;
            
            // Try to find a good place to insert it
            const cameraStatus = document.getElementById('cameraStatus');
            if (cameraStatus && cameraStatus.parentElement) {
                cameraStatus.parentElement.insertBefore(statusElement, cameraStatus.nextSibling);
            } else {
                document.body.appendChild(statusElement);
            }
        }
    }
});

// Helper functions for common patterns
const GeolocationHelper = {
    // Initialize geolocation for attendance
    initForAttendance: function(config = {}) {
        const defaultConfig = {
            radiusMeters: 50,
            highAccuracy: true,
            timeout: 10000,
            enableWatch: true,
            onPositionUpdate: null,
            onError: null,
            onWithinRadius: null,
            onOutsideRadius: null
        };
        
        const mergedConfig = { ...defaultConfig, ...config };
        
        if (!window.geolocationManager) {
            window.geolocationManager = new GeolocationManager(mergedConfig);
        }
        
        // Set up callbacks
        if (mergedConfig.onPositionUpdate) {
            window.geolocationManager.setOnPositionUpdate(mergedConfig.onPositionUpdate);
        }
        
        if (mergedConfig.onError) {
            window.geolocationManager.setOnError(mergedConfig.onError);
        }
        
        if (mergedConfig.onWithinRadius) {
            window.geolocationManager.setOnWithinRadius(mergedConfig.onWithinRadius);
        }
        
        if (mergedConfig.onOutsideRadius) {
            window.geolocationManager.setOnOutsideRadius(mergedConfig.onOutsideRadius);
        }
        
        // Start watching
        setTimeout(() => {
            window.geolocationManager.startWatching();
        }, 1000);
        
        return window.geolocationManager;
    },
    
    // Get position for form submission
    getPositionForForm: function() {
        if (!window.geolocationManager) {
            return { latitude: null, longitude: null };
        }
        
        const position = window.geolocationManager.getPositionForAttendance();
        
        if (position.isValid) {
            return {
                latitude: position.latitude,
                longitude: position.longitude,
                accuracy: position.accuracy
            };
        } else {
            throw new Error('Lokasi tidak valid untuk absensi');
        }
    },
    
    // Check if within radius
    checkWithinRadius: function() {
        if (!window.geolocationManager) {
            return false;
        }
        
        const status = window.geolocationManager.getStatus();
        return status.isWithinRadius && status.hasValidPosition;
    },
    
    // Request permission with UI feedback
    requestPermissionWithUI: async function() {
        if (!window.geolocationManager) {
            return false;
        }
        
        const modal = document.createElement('div');
        modal.className = 'fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50';
        modal.innerHTML = `
            <div class="bg-white rounded-xl shadow-xl w-full max-w-md mx-4">
                <div class="p-6 border-b">
                    <h3 class="text-xl font-bold text-gray-800">Izin Lokasi Diperlukan</h3>
                </div>
                <div class="p-6">
                    <p class="text-gray-700 mb-4">Sistem absensi memerlukan akses lokasi untuk memverifikasi kehadiran Anda di lokasi perusahaan.</p>
                    <div class="bg-blue-50 p-4 rounded-lg mb-4">
                        <p class="text-sm text-blue-700">
                            <i class="fas fa-info-circle mr-2"></i>
                            Lokasi Anda hanya digunakan untuk verifikasi absensi dan tidak disimpan.
                        </p>
                    </div>
                </div>
                <div class="p-6 border-t flex justify-end space-x-3">
                    <button id="cancelPermission" class="px-6 py-2 bg-gray-200 hover:bg-gray-300 text-gray-800 rounded-lg font-medium">
                        Nanti
                    </button>
                    <button id="grantPermission" class="px-6 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium">
                        Izinkan Lokasi
                    </button>
                </div>
            </div>
        `;
        
        document.body.appendChild(modal);
        
        return new Promise((resolve) => {
            document.getElementById('cancelPermission').addEventListener('click', () => {
                modal.remove();
                resolve(false);
            });
            
            document.getElementById('grantPermission').addEventListener('click', async () => {
                modal.remove();
                try {
                    const granted = await window.geolocationManager.requestPermission();
                    resolve(granted);
                } catch (error) {
                    resolve(false);
                }
            });
        });
    },
    
    // Show distance indicator
    createDistanceIndicator: function() {
        const indicator = document.createElement('div');
        indicator.id = 'distance-indicator';
        indicator.className = 'fixed bottom-4 right-4 bg-white rounded-lg shadow-lg p-4 border z-40';
        indicator.innerHTML = `
            <div class="flex items-center mb-2">
                <i class="fas fa-map-marker-alt text-blue-600 mr-2"></i>
                <span class="font-medium text-gray-800">Jarak ke Kantor</span>
            </div>
            <div id="distance-value" class="text-2xl font-bold text-gray-800">-- m</div>
            <div id="distance-status" class="text-sm mt-1">Mengukur...</div>
        `;
        
        document.body.appendChild(indicator);
        
        // Update function
        const updateIndicator = () => {
            if (window.geolocationManager) {
                const position = window.geolocationManager.getCurrentPositionData();
                if (position && position.distance) {
                    const distanceElement = document.getElementById('distance-value');
                    const statusElement = document.getElementById('distance-status');
                    
                    if (distanceElement) {
                        distanceElement.textContent = `${position.distance.toFixed(0)} m`;
                    }
                    
                    if (statusElement) {
                        if (position.isWithinRadius) {
                            statusElement.textContent = '✅ Dalam radius absensi';
                            statusElement.className = 'text-sm mt-1 text-green-600';
                        } else {
                            statusElement.textContent = '❌ Di luar radius absensi';
                            statusElement.className = 'text-sm mt-1 text-red-600';
                        }
                    }
                }
            }
        };
        
        // Update every 5 seconds
        setInterval(updateIndicator, 5000);
        updateIndicator();
        
        return indicator;
    }
};

// Export helper
if (typeof window !== 'undefined') {
    window.GeolocationHelper = GeolocationHelper;
}