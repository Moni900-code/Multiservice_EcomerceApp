import os
import json
import logging
from aiokafka import AIOKafkaProducer

logger = logging.getLogger(__name__)

class KafkaProducer:
    def __init__(self, bootstrap_servers: str):
        self.bootstrap_servers = bootstrap_servers
        self.producer = None

    async def start(self):
        self.producer = AIOKafkaProducer(bootstrap_servers=self.bootstrap_servers)
        await self.producer.start()
        logger.info("Kafka producer started successfully")

    async def stop(self):
        if self.producer:
            await self.producer.stop()
            logger.info("Kafka producer stopped gracefully")

    async def send(self, topic: str, message: dict):
        if not self.producer:
            raise RuntimeError("Kafka producer not started successfully")
        try:
            msg_bytes = json.dumps(message).encode('utf-8')
            await self.producer.send_and_wait(topic, msg_bytes)
            logger.info(f"Sent message to topic {topic}: {message}")
        except Exception as e:
            logger.error(f"Failed to send message: {e}")

# Create singleton KafkaProducer instance, reading bootstrap servers from env
kafka_producer = KafkaProducer(bootstrap_servers=os.getenv("KAFKA_BOOTSTRAP_SERVERS", "automq:9092"))

# Helper async functions for FastAPI startup/shutdown event handlers
async def start_kafka():
    await kafka_producer.start()

async def stop_kafka():
    await kafka_producer.stop()
