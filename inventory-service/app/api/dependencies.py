from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgresql import get_db

from app.core.config import settings
from app.services.kafka_producer import KafkaProducer
from app.services.kafka_producer import kafka_producer

# OAuth2 configuration - in a microservice architecture, 
# actual token validation would typically happen at the gateway level
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token", auto_error=False)


async def get_current_user(token: str = Depends(oauth2_scheme)):
    """
    This is a stub dependency for authentication.
    
    In a real microservice architecture, the API gateway would validate
    the token and pass user details in request headers. This stub is included
    to maintain the API contract while allowing tests without actual auth.
    """
    if token is None:
        # This allows endpoints to be called without auth during development/testing
        # In production, the gateway should block unauthenticated requests
        return {"sub": "test-user", "is_admin": True}
    
    # In production, this function would verify the token signature
    # and decode the payload to get user information
    return {"sub": "authenticated-user", "is_admin": True}


def is_admin(current_user=Depends(get_current_user)):
    """Check if the current user is an admin."""
    if not current_user.get("is_admin", False):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions"
        )
    return current_user


# Database dependency
async def get_db() -> AsyncSession:
    return await get_db()




# Kafka producer dependency
async def get_kafka_producer() -> KafkaProducer:
    return kafka_producer