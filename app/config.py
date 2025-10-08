import os
from dotenv import load_dotenv

load_dotenv()  # Load environment variables from .env

class Config:
    
    FLASK_ENV = os.getenv('FLASK_ENV', 'development')
    
    # Get both connection strings
    _production_url = os.getenv('DATABASE_URL')  # Connection Pooler (port 6543)
    _development_url = os.getenv('SQLALCHEMY_DATABASE_URI')  # Direct Connection (port 5432)
    
    # Select database URL based on environment
    if FLASK_ENV == 'production':
        # Production: Use DATABASE_URL (pooler, port 6543)
        if not _production_url:
            raise ValueError(
                "Production mode requires DATABASE_URL to be set!\n"
                "Set in .env: DATABASE_URL=postgresql://...@host:6543/postgres"
            )
        SQLALCHEMY_DATABASE_URI = _production_url
        _connection_type = "🚀 PRODUCTION - Connection Pooler (port 6543)"
    else:
        # Development: Use SQLALCHEMY_DATABASE_URI (direct, port 5432) if available,
        # otherwise fall back to DATABASE_URL
        SQLALCHEMY_DATABASE_URI = _development_url or _production_url
        
        if not SQLALCHEMY_DATABASE_URI:
            raise ValueError(
                "Database URL not configured! Please set in your .env file:\n"
                "  For Development: SQLALCHEMY_DATABASE_URI=postgresql://...@host:5432/postgres\n"
                "  For Production:  DATABASE_URL=postgresql://...@host:6543/postgres\n"
                "\nSee .env.example for details."
            )
        
        if _development_url:
            _connection_type = "🔧 DEVELOPMENT - Direct Connection (port 5432)"
        else:
            _connection_type = "⚠️  DEVELOPMENT - Using pooler (port 6543)"
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Production-ready connection pool settings
    # These settings work with both direct connections and PgBouncer
    SQLALCHEMY_ENGINE_OPTIONS = {
        # Pool size settings
        'pool_size': 10,             # Number of permanent connections (safe for production)
        'max_overflow': 10,          # Additional temporary connections during load spikes
        'pool_timeout': 30,          # Wait time (seconds) for connection from pool
        
        # Connection lifecycle
        'pool_recycle': 3600,        # Recycle connections after 1 hour (prevents stale connections)
        'pool_pre_ping': True,       # Test connection health before using (critical for production)
        
        # Additional production settings
        'connect_args': {
            'connect_timeout': 10,   # Connection timeout (seconds)
            'application_name': 'AMS_Server',  # Identify app in pg_stat_activity
        }
    }
    
    # Enable SQL query logging in debug mode (disable in production)
    SQLALCHEMY_ECHO = os.getenv('FLASK_ENV') == 'development'