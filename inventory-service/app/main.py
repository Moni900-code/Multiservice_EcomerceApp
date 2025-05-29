from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging
import asyncio

from app.api.routes import inventory
from app.core.config import settings
from app.services.kafka_producer import start_kafka, stop_kafka
from app.services.inventory_kafka_service import kafka_service
from app.db.postgresql import init_db

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Inventory Service API",
    version="1.0.0",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(inventory.router, prefix=settings.API_PREFIX)

async def consume_kafka():
    await kafka_service.start_consumer()
    await kafka_service.consume()

@app.on_event("startup")
async def startup_event():
    logger.info("Starting inventory service...")
    await init_db()
    await start_kafka()
    # Start Kafka consumer in the background
    asyncio.create_task(consume_kafka())

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down inventory service...")
    await stop_kafka()
    await kafka_service.stop()

@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "inventory-service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8002, reload=True)