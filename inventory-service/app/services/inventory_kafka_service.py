from app.service.kafka_producer import kafka_producer
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class InventoryKafkaService:
    @staticmethod
    async def send_stock_update(product_id: str, stock: int):
        message = {
            "product_id": product_id,
            "stock": stock,
        }
        await kafka_producer.send(settings.KAFKA_PRODUCER_TOPIC, message)

    @staticmethod
    async def process_consumed_message(message_bytes: bytes):
        # Deserialize and handle incoming messages here
        import json
        try:
            message = json.loads(message_bytes.decode("utf-8"))
            logger.info(f"Processing consumed mACessage: {message}")
            # TODO: Business logic here, e.g., update inventory, notify other services, etc.
        except Exception as e:
            logger.error(f"Error processing consumed message: {e}")
