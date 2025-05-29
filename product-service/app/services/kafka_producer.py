import json
import logging
from aiokafka import AIOKafkaProducer
from app.core.config import settings  

logger = logging.getLogger(__name__)

class KafkaProducer:
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self.producer = None

    async def start(self):
        self.producer = AIOKafkaProducer(
            bootstrap_servers=self.bootstrap_servers
        )
        await self.producer.start()
        logger.info(f"Kafka producer started with servers: {self.bootstrap_servers}")

    async def send(self, topic: str, value: dict):
        try:
            await self.producer.send_and_wait(topic, json.dumps(value).encode("utf-8"))
            logger.debug(f"Message sent to {topic}")
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            raise

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped.")

# ✅ Corrected: Provide the required argument
kafka_producer = KafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)

# FastAPI startup/shutdown events
async def start_kafka():
    await kafka_producer.start()

async def stop_kafka():
    await kafka_producer.stop()
