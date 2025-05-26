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
            bootstrap_servers=self.bootstrap_servers,
            value_serializer=lambda v: json.dumps(v).encode('utf-8')
        )
        await self.producer.start()
        logger.info(f"Kafka producer started with servers: {self.bootstrap_servers}")

    async def send(self, topic: str, value: dict):
        try:
            await self.producer.send_and_wait(topic, value)
            logger.debug(f"Message sent to {topic}")
        except Exception as e:
            logger.error(f"Failed to send message: {str(e)}")
            raise

        
# Create singleton KafkaProducer instance
kafka_producer = KafkaProducer()

# Helper async functions for FastAPI startup/shutdown event handlers
async def start_kafka():
    await kafka_producer.start()

async def stop_kafka():
    await kafka_producer.stop()