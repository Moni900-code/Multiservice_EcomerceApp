import json
import logging
from aiokafka import AIOKafkaProducer
from app.core.config import settings  

logger = logging.getLogger(__name__)

class KafkaProducer:
    def __init__(self):
        self.producer = None

    async def start(self):
        self.producer = AIOKafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
        await self.producer.start()
        logger.info("Kafka producer started successfully")

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped gracefully")

    async def send(self, topic: str, value: dict):
        if not self.producer:
            raise RuntimeError("Kafka producer not started")
        try:
            message_bytes = json.dumps(value).encode("utf-8")
            await self.producer.send_and_wait(topic, message_bytes)
            logger.info(f"Sent message to topic {topic}: {value}")
        except Exception as e:
            logger.error(f"Failed to send message to topic {topic}: {e}")
            raise

# Create singleton KafkaProducer instance
kafka_producer = KafkaProducer()

# Helper async functions for FastAPI startup/shutdown event handlers
async def start_kafka():
    await kafka_producer.start()

async def stop_kafka():
    await kafka_producer.stop()