from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import inventory
from app.core.config import settings
from app.db.postgresql import initialize_db, close_db_connection

# Kafka services
from app.services.kafka_producer import kafka_producer
from app.services.kafka_consumer import kafka_consumer

import asyncio
import logging

logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Inventory Service API",
    version="1.0.0",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

# Set up CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For production, restrict to specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Set up API routes
app.include_router(inventory.router, prefix=settings.API_PREFIX)


# Register startup and shutdown events
@app.on_event("startup")
async def on_startup():
    await initialize_db()

    #  Start Kafka Producer
    await kafka_producer.start()
    logger.info(" Kafka producer started")

    #  Start Kafka Consumer in background
    asyncio.create_task(kafka_consumer.start())
    logger.info(" Kafka consumer started")

@app.on_event("shutdown")
async def on_shutdown():
    await close_db_connection()

    #  Stop Kafka Producer & Consumer
    await kafka_producer.stop()
    await kafka_consumer.stop()
    logger.info(" Kafka producer and consumer stopped")


# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "inventory-service"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=settings.PORT, reload=True)
