"""
System configuration service using SQLAlchemy ORM
"""
from sqlalchemy.orm import Session
from api.models.database import SystemConfig, get_db

class ConfigService:
    """Service for managing system configuration using SQLAlchemy ORM"""

    def __init__(self, db: Session):
        self.db = db

    def get(self, key: str, default=None):
        """Get config value from database using SQLAlchemy ORM"""
        config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
        return config.value if config else default

    def set(self, key: str, value: str):
        """Set config value in database using SQLAlchemy ORM"""
        config = self.db.query(SystemConfig).filter(SystemConfig.key == key).first()
        if config:
            config.value = value
        else:
            config = SystemConfig(key=key, value=value)
            self.db.add(config)
        self.db.commit()
        self.db.refresh(config)
        return config

    def refresh_cache(self):
        """Clear any cached values (for compatibility)"""
        # In ORM-based approach, we don't need caching at this level
        pass

def get_config_service(db: Session = None) -> ConfigService:
    """Get config service instance"""
    if db is None:
        db = next(get_db())
    return ConfigService(db)