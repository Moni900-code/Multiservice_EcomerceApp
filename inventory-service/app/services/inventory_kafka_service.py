import logging
import json
from aiokafka import AIOKafkaProducer, AIOKafkaConsumer
from app.core.config import settings

logger = logging.getLogger(__name__)

class KafkaService:
    def __init__(self):
        self.kafka_producer = None
        self.consumer = None

    async def start_producer(self):
        self.kafka_producer = AIOKafkaProducer(
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
        )
        await self.kafka_producer.start()
        logger.info("Kafka producer started")

    async def start_consumer(self):
        self.consumer = AIOKafkaConsumer(
            settings.KAFKA_CONSUMER_TOPIC,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="inventory-service-group",
            auto_offset_reset="earliest",
        )
        await self.consumer.start()
        logger.info("Kafka consumer started")

    async def stop(self):
        if self.kafka_producer:
            await self.kafka_producer.stop()
            logger.info("Kafka producer stopped")
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def send_stock_update(self, product_id: str, stock: int):
        if not self.kafka_producer:
            await self.start_producer()
        message = {
            "product_id": product_id,
            "stock": stock
        }
        await self.kafka_producer.send_and_wait(
            settings.KAFKA_PRODUCER_TOPIC,
            json.dumps(message).encode("utf-8")
        )
        logger.info(f"Sent stock update to {settings.KAFKA_PRODUCER_TOPIC}: {message}")

    async def consume(self):
        if not self.consumer:
            await self.start_consumer()
        async for msg in self.consumer:
            try:
                message = json.loads(msg.value.decode("utf-8"))
                logger.info(f"Received message from {settings.KAFKA_CONSUMER_TOPIC}: {message}")
                # Process product creation event here (if needed)
            except Exception as e:
                logger.error(f"Error processing message: {str(e)}")

kafka_service = KafkaService()