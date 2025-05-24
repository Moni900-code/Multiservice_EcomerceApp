import logging
from aiokafka import AIOKafkaConsumer
from app.core.config import settings

logger = logging.getLogger(__name__)

class KafkaConsumer:
    def __init__(self, topics):
        self.consumer = None
        self.topics = topics

    async def start(self):
        self.consumer = AIOKafkaConsumer(
            *self.topics,
            bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
            group_id="inventory-service-group",
            auto_offset_reset="earliest",
        )
        await self.consumer.start()
        logger.info(f"Kafka consumer started for topics: {self.topics}")

    async def stop(self):
        if self.consumer:
            await self.consumer.stop()
            logger.info("Kafka consumer stopped")

    async def consume_messages(self):
        if self.consumer is None:
            logger.error("Consumer not started")
            return

        async for msg in self.consumer:
            logger.info(f"Consumed message: topic={msg.topic} key={msg.key} value={msg.value}")
            # TODO: Add message processing logic here

# Create singleton consumer instance subscribing to consumer topic
kafka_consumer = KafkaConsumer([settings.KAFKA_CONSUMER_TOPIC])
