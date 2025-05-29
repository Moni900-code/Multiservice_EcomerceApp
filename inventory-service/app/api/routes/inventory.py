import logging
import httpx
from datetime import datetime
from typing import List, Optional, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Body, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.models.inventory import (
    InventoryItem, InventoryHistory,
    InventoryItemCreate, InventoryItemUpdate, InventoryItemResponse,
    InventoryCheck, InventoryReserve, InventoryRelease, InventoryAdjust
)
from app.api.dependencies import get_current_user, is_admin
from app.db.postgresql import get_db
from app.services.product import product_service
from app.core.config import settings
from app.services.inventory_kafka_service import kafka_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/inventory", tags=["inventory"])

async def get_kafka_producer():
    await kafka_service.start()
    try:
        yield kafka_service.kafka_producer
    finally:
        await kafka_service.stop()

@router.post("/", response_model=InventoryItemResponse, status_code=201)
async def create_inventory_item(
    item: InventoryItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(is_admin),
    kafka_producer=Depends(get_kafka_producer)
):
    product = await product_service.get_product(item.product_id)
    if not product:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product with ID {item.product_id} not found"
        )
    
    db_item = InventoryItem(
        product_id=item.product_id,
        available_quantity=item.available_quantity,
        reserved_quantity=item.reserved_quantity,
        reorder_threshold=item.reorder_threshold
    )
    
    try:
        db.add(db_item)
        await db.flush()
        
        history_entry = InventoryHistory(
            product_id=item.product_id,
            quantity_change=item.available_quantity,
            previous_quantity=0,
            new_quantity=item.available_quantity,
            change_type="add",
            reference_id=None
        )
        db.add(history_entry)
        
        await db.commit()
        await db.refresh(db_item)

        await kafka_service.send_stock_update(
            product_id=item.product_id,
            stock=item.available_quantity
        )
        
        logger.info(f"Created inventory item for product {item.product_id}")
        return db_item
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Inventory item for product {item.product_id} already exists"
        )

# বাকি কোড অপরিবর্তিত (আগের মতো)
@router.get("/", response_model=List[InventoryItemResponse])
async def get_inventory_items(
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=100),
    low_stock_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    query = select(InventoryItem)
    
    if low_stock_only:
        query = query.where(
            InventoryItem.available_quantity <= InventoryItem.reorder_threshold
        )
    
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    items = result.scalars().all()
    
    return items

@router.get("/check", response_model=Dict[str, Any])
async def check_inventory(
    product_id: str = Query(...),
    quantity: int = Query(..., gt=0),
    db: AsyncSession = Depends(get_db)
):
    query = select(InventoryItem).where(InventoryItem.product_id == product_id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        return {"available": False, "message": f"Product {product_id} not found in inventory"}
    
    is_available = item.available_quantity >= quantity
    
    return {
        "available": is_available,
        "current_quantity": item.available_quantity,
        "requested_quantity": quantity,
        "product_id": product_id
    }

@router.get("/{product_id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    product_id: str = Path(...),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    query = select(InventoryItem).where(InventoryItem.product_id == product_id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product {product_id} not found"
        )
    
    return item

@router.put("/{product_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    product_id: str,
    item_update: InventoryItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(is_admin),
    kafka_producer=Depends(get_kafka_producer)
):
    query = select(InventoryItem).where(InventoryItem.product_id == product_id)
    result = await db.execute(query)
    existing_item = result.scalars().first()
    
    if not existing_item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product {product_id} not found"
        )
    
    update_data = {}
    previous_quantity = existing_item.available_quantity
    
    if item_update.available_quantity is not None:
        update_data["available_quantity"] = item_update.available_quantity
    
    if item_update.reserved_quantity is not None:
        update_data["reserved_quantity"] = item_update.reserved_quantity
    
    if item_update.reorder_threshold is not None:
        update_data["reorder_threshold"] = item_update.reorder_threshold
    
    update_data["updated_at"] = func.now()
    
    query = (
        update(InventoryItem)
        .where(InventoryItem.product_id == product_id)
        .values(**update_data)
        .returning(InventoryItem)
    )
    
    result = await db.execute(query)
    updated_item = result.scalars().first()
    
    if "available_quantity" in update_data:
        quantity_change = update_data["available_quantity"] - previous_quantity
        history_entry = InventoryHistory(
            product_id=product_id,
            quantity_change=quantity_change,
            previous_quantity=previous_quantity,
            new_quantity=update_data["available_quantity"],
            change_type="update",
            reference_id=None
        )
        db.add(history_entry)
    
    await db.commit()

    if "available_quantity" in update_data:
        await kafka_service.send_stock_update(
            product_id=product_id,
            stock=update_data["available_quantity"]
        )

    await check_and_notify_low_stock(updated_item)
    
    logger.info(f"Updated inventory for product {product_id}")
    return updated_item

@router.post("/reserve", response_model=Dict[str, Any])
async def reserve_inventory(
    reservation: InventoryReserve,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    kafka_producer=Depends(get_kafka_producer)
):
    query = select(InventoryItem).where(InventoryItem.product_id == reservation.product_id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product {reservation.product_id} not found"
        )
    
    if item.available_quantity < reservation.quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory. Requested: {reservation.quantity}, Available: {item.available_quantity}"
        )
    
    new_available = item.available_quantity - reservation.quantity
    new_reserved = item.reserved_quantity + reservation.quantity
    
    query = (
        update(InventoryItem)
        .where(InventoryItem.product_id == reservation.product_id)
        .values(
            available_quantity=new_available,
            reserved_quantity=new_reserved,
            updated_at=func.now()
        )
        .returning(InventoryItem)
    )
    
    result = await db.execute(query)
    updated_item = result.scalars().first()
    
    history_entry = InventoryHistory(
        product_id=reservation.product_id,
        quantity_change=-reservation.quantity,
        previous_quantity=item.available_quantity,
        new_quantity=new_available,
        change_type="reserve",
        reference_id=reservation.order_id
    )
    db.add(history_entry)
    
    await db.commit()
    
    await kafka_service.send_stock_update(
        product_id=reservation.product_id,
        stock=new_available
    )
    
    await check_and_notify_low_stock(updated_item)
    
    logger.info(f"Reserved {reservation.quantity} units of product {reservation.product_id}")
    
    return {
        "reserved": True,
        "product_id": reservation.product_id,
        "quantity": reservation.quantity,
        "available_quantity": new_available,
        "reserved_quantity": new_reserved
    }

@router.post("/release", response_model=Dict[str, Any])
async def release_inventory(
    release: InventoryReserve,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user),
    kafka_producer=Depends(get_kafka_producer)
):
    query = select(InventoryItem).where(InventoryItem.product_id == release.product_id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product {release.product_id} not found"
        )
    
    if item.reserved_quantity < release.quantity:
        logger.warning(
            f"Attempted to release more than reserved. Requested: {release.quantity}, "
            f"Reserved: {item.reserved_quantity}. Capping at reserved amount."
        )
        release.quantity = item.reserved_quantity
    
    new_available = item.available_quantity + release.quantity
    new_reserved = item.reserved_quantity - release.quantity
    
    query = (
        update(InventoryItem)
        .where(InventoryItem.product_id == release.product_id)
        .values(
            available_quantity=new_available,
            reserved_quantity=new_reserved,
            updated_at=func.now()
        )
        .returning(InventoryItem)
    )
    
    result = await db.execute(query)
    updated_item = result.scalars().first()
    
    history_entry = InventoryHistory(
        product_id=release.product_id,
        quantity_change=release.quantity,
        previous_quantity=item.available_quantity,
        new_quantity=new_available,
        change_type="release",
        reference_id=release.order_id
    )
    db.add(history_entry)
    
    await db.commit()

    await kafka_service.send_stock_update(
        product_id=release.product_id,
        stock=new_available
    )
    
    logger.info(f"Released {release.quantity} units of product {release.product_id}")
    
    return {
        "released": True,
        "product_id": release.product_id,
        "quantity": release.quantity,
        "available_quantity": new_available,
        "reserved_quantity": new_reserved
    }

@router.post("/adjust", response_model=InventoryItemResponse)
async def adjust_inventory(
    adjustment: InventoryAdjust,
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(is_admin),
    kafka_producer=Depends(get_kafka_producer)
):
    query = select(InventoryItem).where(InventoryItem.product_id == adjustment.product_id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for product {adjustment.product_id} not found"
        )
    
    new_quantity = item.available_quantity + adjustment.quantity_change
    
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reduce inventory below zero. Current: {item.available_quantity}, Adjustment: {adjustment.quantity_change}"
        )
    
    query = (
        update(InventoryItem)
        .where(InventoryItem.product_id == adjustment.product_id)
        .values(
            available_quantity=new_quantity,
            updated_at=func.now()
        )
        .returning(InventoryItem)
    )
    
    result = await db.execute(query)
    updated_item = result.scalars().first()
    
    change_type = "add" if adjustment.quantity_change > 0 else "remove"
    history_entry = InventoryHistory(
        product_id=adjustment.product_id,
        quantity_change=adjustment.quantity_change,
        previous_quantity=item.available_quantity,
        new_quantity=new_quantity,
        change_type=change_type,
        reference_id=adjustment.reference_id
    )
    db.add(history_entry)
    
    await db.commit()

    await kafka_service.send_stock_update(
        product_id=adjustment.product_id,
        stock=new_quantity
    )
    
    await check_and_notify_low_stock(updated_item)
    
    logger.info(f"Adjusted inventory for product {adjustment.product_id} by {adjustment.quantity_change}")
    return updated_item

@router.get("/low-stock", response_model=List[InventoryItemResponse])
async def get_low_stock(
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    query = select(InventoryItem).where(
        InventoryItem.available_quantity <= InventoryItem.reorder_threshold
    )
    
    result = await db.execute(query)
    items = result.scalars().all()
    
    return items

@router.get("/history/{product_id}", response_model=List[Dict[str, Any]])
async def get_inventory_history(
    product_id: str,
    limit: int = Query(20, ge=5, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    query = select(InventoryItem).where(InventoryItem.product_id == product_id)
    result = await db.execute(query)
    item = result.scalars().first()
    
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Inventory for {product_id} not found"
        )
    
    query = (
        select(InventoryHistory)
        .where(InventoryHistory.product_id == product_id)
        .order_by(InventoryHistory.timestamp.desc())
        .limit(limit)
    )
    
    result = await db.execute(query)
    history = result.scalars().all()
    
    history_list = [
        {
            "pk": h.id,
            "product_id": h.product_id,
            "quantity_change": h.quantity_change,
            "previous_quantity": h.previous_quantity,
            "new_quantity": h.new_quantity,
            "change_type": h.change_type,
            "reference_id": h.reference_id,
            "timestamp": h.timestamp
        }
        for h in history
    ]
    
    return history_list

async def check_and_notify_low_stock(inventory_item: InventoryItem):
    if not settings.ENABLE_NOTIFICATIONS or not settings.NOTIFICATION_URL:
        return
    
    if inventory_item.available_quantity <= inventory_item.reorder_threshold:
        try:
            product = await product_service.get_product(inventory_item.product_id)
            product_name = product.get("name", inventory_item.product_id) if product else inventory_item.product_id
            
            message = {
                "type": "low_stock",
                "product_id": inventory_item.product_id,
                "product_name": product_name,
                "current_quantity": inventory_item.available_quantity,
                "threshold": inventory_item.reorder_threshold,
                "timestamp": datetime.utcnow().isoformat()
            }
            await kafka_service.send_stock_update(
                product_id=inventory_item.product_id,
                stock=inventory_item.available_quantity
            )
            logger.info(f"Low stock notification sent for product {inventory_item.product_id}")
        except Exception as e:
            logger.error(f"Failed to send low stock notification: {e}")