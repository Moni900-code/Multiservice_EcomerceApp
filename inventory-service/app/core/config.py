import os
from typing import Optional, Dict, Any

from pydantic import BaseSettings, AnyHttpUrl, validator, PostgresDsn


class Settings(BaseSettings):
    # API settings
    API_PREFIX: str = "/api/v1"
    DEBUG: bool = False
    PROJECT_NAME: str = "Inventory Service"
    PORT: int = 8002
    
    # Database settings
    DATABASE_URL: PostgresDsn
    
    # Service URLs
    PRODUCT_SERVICE_URL: AnyHttpUrl
    
    # Retry Configuration
    MAX_RETRIES: int = 3
    RETRY_DELAY: int = 1  # seconds
    
    # JWT Auth settings (for testing/development)
    SECRET_KEY: str = "development-secret-key"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    
    # Inventory settings
    LOW_STOCK_THRESHOLD: int = 5
    ENABLE_NOTIFICATIONS: bool = True
    NOTIFICATION_URL: Optional[AnyHttpUrl] = None

    # ✅ Kafka settings
    KAFKA_BOOTSTRAP_SERVERS: str  # e.g., "kafka:9092"
    KAFKA_PRODUCER_TOPIC: str      # e.g., "product_created"
    KAFKA_CONSUMER_TOPIC: str  # e.g., "stock_updated"
    PRODUCT_SERVICE_URL: str = "http://product-service:8000/api/v1"
    INVENTORY_SERVICE_URL: str = "http://inventory-service:8002/api/v1"   
     
    # Validate URLs are properly formatted
    @validator("PRODUCT_SERVICE_URL", "NOTIFICATION_URL", pre=True)
    def validate_service_urls(cls, v):
        if isinstance(v, str) and not v.startswith(("http://", "https://")):
            return f"http://{v}"
        return v
    
    class Config:
        env_file = ".env"
        case_sensitive = True


# Create global settings object
settings = Settings()