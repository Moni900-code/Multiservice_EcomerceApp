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
            bootstrap_servers=self.bootstrap_servers,  # ✅ Use the instance variable
        )
        await self.producer.start()
        logger.info("Kafka producer started")

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped")

    async def send(self, topic: str, value: dict):
        if self.producer is None:
            logger.error("Producer not started")
            return
        try:
            message_bytes = json.dumps(value).encode("utf-8")
            await self.producer.send_and_wait(topic, message_bytes)
            logger.info(f"Sent message to topic {topic}: {value}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

# ✅ Fix: Pass bootstrap_servers explicitly
kafka_producer = KafkaProducer(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)
