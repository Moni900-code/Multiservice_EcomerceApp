from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import logging

from app.services.kafka_producer import start_kafka, stop_kafka
from app.api.routes import products
from app.core.config import settings
from app.db.mongodb import connect_to_mongo, close_mongo_connection

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="Product Service API",
    version="1.0.0",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
    docs_url=f"{settings.API_PREFIX}/docs",
    redoc_url=f"{settings.API_PREFIX}/redoc",
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Use specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include router
app.include_router(products.router, prefix=settings.API_PREFIX)

# Startup and shutdown events
@app.on_event("startup")
async def startup_event():
    logger.info("Starting product service...")
    await connect_to_mongo()
    await start_kafka()

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Shutting down product service...")
    await close_mongo_connection()
    await stop_kafka()

# Health check endpoint
@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "product-service"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)