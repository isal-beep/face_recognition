import os
from datetime import timedelta


class Config:
    """Production configuration"""
    
    # Security
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'attendance-system-production-secret-key-change-in-production'
    
    # Database (Railway compatible)
    MYSQL_USER = os.getenv("MYSQLUSER")
    MYSQL_PASSWORD = os.getenv("MYSQLPASSWORD")
    MYSQL_HOST = os.getenv("MYSQLHOST")
    MYSQL_PORT = os.getenv("MYSQLPORT", "3306")
    MYSQL_DB = os.getenv("MYSQLDATABASE")

    if not MYSQL_HOST:
        raise RuntimeError("MySQL environment variables not set (Railway)")

    SQLALCHEMY_DATABASE_URI = (
        f"mysql+mysqlconnector://{MYSQL_USER}:{MYSQL_PASSWORD}"
        f"@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}"
    )

    
    # Face Recognition Settings
    FACE_RECOGNITION_THRESHOLD = 0.6  # Minimum similarity score
    LIVENESS_THRESHOLD = 0.15  # Eye Aspect Ratio threshold
    MIN_FACE_CONFIDENCE = 0.5  # Minimum face detection confidence
    
   
    # GPS Geofencing - UPDATE INI!
    COMPANY_LATITUDE = -6.519753439536491    # Latitude Kinilai Parfum Refill
    COMPANY_LONGITUDE = 106.83235256551652   # Longitude Kinilai Parfum Refill
    GPS_RADIUS_METERS = 100                  # 100 meter radius (bisa disesuaikan)
    
    # Upload Settings
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max file size
    UPLOAD_FOLDER = 'static/uploads'
    ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
    
    # Paths
    PROFILE_UPLOAD_PATH = 'static/uploads/profiles'
    LEAVE_UPLOAD_PATH = 'static/uploads/leaves'
    
    # Session Settings
    PERMANENT_SESSION_LIFETIME = timedelta(hours=8)
    SESSION_COOKIE_SECURE = False  # Set True in production with HTTPS
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    
    # Security Headers (Flask-Talisman would be better for production)
    SECURITY_HEADERS = {
        'X-Content-Type-Options': 'nosniff',
        'X-Frame-Options': 'SAMEORIGIN',
        'X-XSS-Protection': '1; mode=block'
    }
    
    # CORS Settings (if API needed)
    CORS_ORIGINS = ['http://localhost:5000', 'http://127.0.0.1:5000']
    
    # Face Engine Settings
    FACE_CACHE_FILE = 'face_cache.pkl'
    DATASET_DIR = 'dataset'
    
    # Shift Defaults
    DEFAULT_SHIFT_TOLERANCE = 5  # minutes
    DEFAULT_SHIFT_START = '08:00'
    DEFAULT_SHIFT_END = '17:00'
    
    # Reporting
    REPORT_EXPORT_TYPES = ['json', 'excel', 'csv']
    MAX_REPORT_DAYS = 365  # Max days for report generation
    
    # Pagination
    ITEMS_PER_PAGE = 20
    
    # Logging
    LOG_LEVEL = 'INFO'
    LOG_FILE = 'attendance_system.log'
    
    # Performance
    FACE_PROCESSING_TIMEOUT = 5  # seconds
    DATABASE_QUERY_TIMEOUT = 30  # seconds
    
    @staticmethod
    def init_app(app):
        """Initialize application with configuration"""
        # Ensure upload directories exist
        os.makedirs(Config.UPLOAD_FOLDER, exist_ok=True)
        os.makedirs(Config.PROFILE_UPLOAD_PATH, exist_ok=True)
        os.makedirs(Config.LEAVE_UPLOAD_PATH, exist_ok=True)
        os.makedirs(Config.DATASET_DIR, exist_ok=True)
        
        # Set secure headers
        @app.after_request
        def add_security_headers(response):
            for header, value in Config.SECURITY_HEADERS.items():
                response.headers[header] = value
            return response
        
        # Configure logging
        import logging
        from logging.handlers import RotatingFileHandler
        
        # Create formatter
        formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )
        
        # File handler with rotation
        file_handler = RotatingFileHandler(
            Config.LOG_FILE,
            maxBytes=10485760,  # 10MB
            backupCount=10
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Configure app logger
        app.logger.addHandler(file_handler)
        app.logger.addHandler(console_handler)
        app.logger.setLevel(getattr(logging, Config.LOG_LEVEL))
        
        # Disable werkzeug logging if not in debug
        if not app.debug:
            logging.getLogger('werkzeug').setLevel(logging.WARNING)
        
        app.logger.info('Application initialized with production configuration')


class DevelopmentConfig(Config):
    """Development configuration"""
    
    DEBUG = True
    LOG_LEVEL = 'DEBUG'
    
    # Allow larger files for development
    MAX_CONTENT_LENGTH = 32 * 1024 * 1024  # 32MB
    
    # Show SQL queries in debug mode
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 5,
        'pool_recycle': 300,
        'pool_pre_ping': True,
        'max_overflow': 10,
        'echo': True  # Show SQL queries in console
    }


class TestingConfig(Config):
    """Testing configuration"""
    
    TESTING = True
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    WTF_CSRF_ENABLED = False
    
    # Test-specific settings
    FACE_RECOGNITION_THRESHOLD = 0.4  # Lower threshold for testing
    GPS_RADIUS_METERS = 1000  # Larger radius for testing


class ProductionConfig(Config):
    """Production configuration"""
    
    DEBUG = False
    
    # Production security
    SESSION_COOKIE_SECURE = True  # Requires HTTPS
    REMEMBER_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Strict'
    
    # Production database
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 20,
        'pool_recycle': 3600,
        'pool_pre_ping': True,
        'max_overflow': 30,
        'echo': False
    }
    
    # Production logging
    LOG_LEVEL = 'WARNING'
    
    @staticmethod
    def init_app(app):
        Config.init_app(app)
        
        # Production-specific initializations
        import logging
        from logging.handlers import SMTPHandler
        
        # Email error notifications (optional)
        if os.environ.get('MAIL_SERVER'):
            credentials = None
            secure = None
            
            if os.environ.get('MAIL_USERNAME'):
                credentials = (os.environ['MAIL_USERNAME'], 
                             os.environ['MAIL_PASSWORD'])
            if os.environ.get('MAIL_USE_TLS'):
                secure = ()
            
            mail_handler = SMTPHandler(
                mailhost=(os.environ.get('MAIL_SERVER'), 
                         os.environ.get('MAIL_PORT', 25)),
                fromaddr=os.environ.get('MAIL_FROM'),
                toaddrs=[os.environ.get('ADMIN_EMAIL')],
                subject='Attendance System Error',
                credentials=credentials,
                secure=secure
            )
            mail_handler.setLevel(logging.ERROR)
            app.logger.addHandler(mail_handler)


# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'testing': TestingConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}


def get_config(config_name=None):
    """
    Get configuration based on environment
    
    Args:
        config_name: Configuration name (development, testing, production)
        
    Returns:
        Configuration class
    """
    if config_name is None:
        config_name = os.environ.get('FLASK_ENV', 'default')
    
    return config.get(config_name, config['default'])


# Helper functions
def allowed_file(filename):
    """
    Check if file extension is allowed
    
    Args:
        filename: Name of the file
        
    Returns:
        True if allowed, False otherwise
    """
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_EXTENSIONS


def get_upload_path(file_type='profile'):
    """
    Get upload path based on file type
    
    Args:
        file_type: 'profile' or 'leave'
        
    Returns:
        Upload directory path
    """
    if file_type == 'profile':
        return Config.PROFILE_UPLOAD_PATH
    elif file_type == 'leave':
        return Config.LEAVE_UPLOAD_PATH
    else:
        return Config.UPLOAD_FOLDER


def generate_filename(employee_id, original_filename, file_type='profile'):
    """
    Generate secure filename for upload
    
    Args:
        employee_id: Employee ID
        original_filename: Original filename
        file_type: 'profile' or 'leave'
        
    Returns:
        Secure filename
    """
    import uuid
    from werkzeug.utils import secure_filename
    
    # Get file extension
    ext = os.path.splitext(original_filename)[1]
    
    # Generate unique filename
    if file_type == 'profile':
        filename = f"profile_{employee_id}_{uuid.uuid4().hex[:8]}{ext}"
    elif file_type == 'leave':
        filename = f"leave_{employee_id}_{uuid.uuid4().hex[:8]}{ext}"
    else:
        filename = f"{uuid.uuid4().hex}{ext}"
    
    return secure_filename(filename)


# Export configurations
__all__ = [
    'Config', 
    'DevelopmentConfig', 
    'TestingConfig', 
    'ProductionConfig',
    'config',
    'get_config',
    'allowed_file',
    'get_upload_path',
    'generate_filename'
]