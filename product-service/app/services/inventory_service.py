import httpx
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

class InventoryService:
    def __init__(self, base_url: str):
        self.base_url = base_url

    async def create_inventory(self, product_id: str, initial_quantity: int, reorder_threshold: int):
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    f"{self.base_url}/inventory/",
                    json={
                        "product_id": product_id,
                        "available_quantity": initial_quantity,
                        "reserved_quantity": 0,
                        "reorder_threshold": reorder_threshold
                    }
                )
                response.raise_for_status()
                logger.info(f"Inventory created for product_id: {product_id}")
                return response.json()
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error creating inventory for product {product_id}: {e.response.text}")
                raise
            except httpx.RequestError as e:
                logger.error(f"Request error creating inventory for product {product_id}: {str(e)}")
                raise

inventory_service = InventoryService(base_url="http://inventory-service:8002/api/v1")