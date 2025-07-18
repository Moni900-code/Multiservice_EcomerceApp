from fastapi import APIRouter, Depends, HTTPException, Path, Query, Body, status
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from typing import List, Optional, Dict, Any
import logging

from app.models.product import ProductCreate, ProductResponse, ProductUpdate, PyObjectId
from app.api.dependencies import get_current_user, get_db, get_kafka_producer
from app.services.inventory_service import inventory_service
from app.services.kafka_producer import KafkaProducer

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/products", tags=["products"])

@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(
    product: ProductCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    kafka_producer: KafkaProducer = Depends(get_kafka_producer)
):
    product_dict = product.dict()
    result = await db["products"].insert_one(product_dict)
    created_product = await db["products"].find_one({"_id": result.inserted_id})

    logger.info(f"Created product: {result.inserted_id}")

    product_dict["_id"] = str(result.inserted_id)

    try:
        await kafka_producer.send(
            topic="product-topic",
            value={
                "event": "product_created",
                "product_id": str(result.inserted_id),
                "product_data": product_dict
            }
        )
        logger.info(f"Published product creation event to product-topic: {result.inserted_id}")
    except Exception as e:
        logger.error(f"Kafka publish failed: {e}")

    try:
        await inventory_service.create_inventory(
            product_id=str(result.inserted_id),
            initial_quantity=product.quantity,
            reorder_threshold=max(5, int(product.quantity * 0.1))
        )
        logger.info(f"Created inventory for product: {result.inserted_id}")
    except Exception as e:
        logger.error(f"Error creating inventory for product {result.inserted_id}: {str(e)}")

    return created_product

@router.get("/", response_model=List[ProductResponse])
async def get_products(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    category: Optional[str] = Query(None),
    name: Optional[str] = Query(None),
    min_price: Optional[float] = Query(None, ge=0),
    max_price: Optional[float] = Query(None, ge=0),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    query = {}
    if category:
        query["category"] = category
    if name:
        query["name"] = {"$regex": name, "$options": "i"}
    if min_price is not None or max_price is not None:
        query["price"] = {}
        if min_price is not None:
            query["price"]["$gte"] = min_price
        if max_price is not None:
            query["price"]["$lte"] = max_price

    cursor = db["products"].find(query).skip(skip).limit(limit)
    products = await cursor.to_list(length=limit)
    return products

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: str = Path(...),
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    try:
        product_obj_id = PyObjectId(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID format")

    product = await db["products"].find_one({"_id": product_obj_id})
    if product:
        return product

    raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")

@router.put("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: str,
    product: ProductUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    try:
        product_obj_id = PyObjectId(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID format")

    update_data = {k: v for k, v in product.dict().items() if v is not None}
    if not update_data:
        raise HTTPException(status_code=400, detail="No fields to update")

    product = await db["products"].find_one_and_update(
        {"_id": product_obj_id},
        {"$set": update_data},
        return_document=ReturnDocument.AFTER
    )

    if product:
        logger.info(f"Updated product: {product_id}")
        return product

    raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")

@router.delete("/{product_id}", status_code=204)
async def delete_product(
    product_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    try:
        product_obj_id = PyObjectId(product_id)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid product ID format")

    result = await db["products"].delete_one({"_id": product_obj_id})
    if result.deleted_count:
        logger.info(f"Deleted product: {product_id}")
        return None

    raise HTTPException(status_code=404, detail=f"Product with ID {product_id} not found")

@router.get("/category/list", response_model=List[str])
async def get_categories(db: AsyncIOMotorDatabase = Depends(get_db)):
    categories = await db["products"].distinct("category")
    return categories