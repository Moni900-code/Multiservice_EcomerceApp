import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Body, status
from fastapi.responses import JSONResponse
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo import ReturnDocument
from typing import List, Optional, Dict, Any
from bson import ObjectId
from decimal import Decimal
from datetime import datetime
import logging

from app.models.order import OrderCreate, OrderResponse, OrderUpdate, OrderStatusUpdate
from app.api.dependencies import get_current_user, get_db, is_admin
from app.services.user import user_service
from app.services.product import product_service
from app.services.inventory import inventory_service
from app.core.config import settings

# Configure logger
logger = logging.getLogger(__name__)

# Create router
router = APIRouter(prefix="/orders", tags=["orders"])


@router.post("/", response_model=OrderResponse, status_code=201)
async def create_order(
    order: OrderCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Create a new order.
    
    This endpoint will:
    1. Verify the user exists
    2. Verify all products exist and prices are correct
    3. Check inventory availability
    4. Reserve inventory
    5. Create the order in pending status
    """
    # Verify the user exists
    user_valid = await user_service.verify_user(order.user_id)
    if not user_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID"
        )
    
    # Verify all products exist and prices are correct
    products_valid = await product_service.verify_products(order.items)
    if not products_valid:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="One or more products are invalid or have incorrect prices"
        )
    
    # Check inventory availability for all items
    inventory_checks = []
    for item in order.items:
        inventory_available = await inventory_service.check_inventory(
            item.product_id, 
            item.quantity
        )
        inventory_checks.append((item, inventory_available))
    
    if not all(available for _, available in inventory_checks):
        unavailable_items = [
            f"Product {item.product_id} (quantity: {item.quantity})"
            for item, available in inventory_checks
            if not available
        ]
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Insufficient inventory for: {', '.join(unavailable_items)}"
        )
    
    # Reserve inventory for all items
    for item, _ in inventory_checks:
        await inventory_service.reserve_inventory(item.product_id, item.quantity)
    
    # Calculate total price
    total_price = sum(
        Decimal(str(item.price)) * item.quantity
        for item in order.items
    )
    
    # Create the order
    now = datetime.utcnow()
    
    # Convert order items to dictionary format, explicitly converting Decimal to float
    items_dict = []
    for item in order.items:
        items_dict.append({
            "product_id": item.product_id,
            "quantity": item.quantity,
            "price": float(item.price)  # Convert Decimal to float for MongoDB
        })
    
    order_dict = {
        "user_id": order.user_id,
        "items": items_dict,
        "total_price": float(total_price),  # Convert Decimal to float for MongoDB
        "status": settings.ORDER_STATUS["PENDING"],
        "shipping_address": order.shipping_address.dict(),
        "created_at": now,
        "updated_at": now
    }
    
    result = await db["orders"].insert_one(order_dict)
    
    # Retrieve the created order
    created_order = await db["orders"].find_one({"_id": result.inserted_id})
    
    logger.info(f"Created order: {result.inserted_id}")
    return created_order


@router.get("/", response_model=List[OrderResponse])
async def get_orders(
    skip: int = Query(0, ge=0, description="Number of orders to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max number of orders to return"),
    status: Optional[str] = Query(None, description="Filter by order status"),
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    start_date: Optional[str] = Query(None, description="Start date (YYYY-MM-DD)"),
    end_date: Optional[str] = Query(None, description="End date (YYYY-MM-DD)"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all orders with optional filtering.
    
    This endpoint allows filtering by:
    - Order status
    - User ID
    - Date range
    """
    query = {}
    
    # Apply filters if provided
    if status:
        if status not in settings.ORDER_STATUS.values():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(settings.ORDER_STATUS.values())}"
            )
        query["status"] = status
    
    if user_id:
        try:
            query["user_id"] = str(ObjectId(user_id))
        except:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid user ID format"
            )
    
    # Date filtering
    date_filter = {}
    if start_date:
        try:
            start_datetime = datetime.strptime(start_date, "%Y-%m-%d")
            date_filter["$gte"] = start_datetime
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid start_date format. Use YYYY-MM-DD"
            )
    
    if end_date:
        try:
            # Add a day to include the entire end date
            end_datetime = datetime.strptime(end_date, "%Y-%m-%d")
            end_datetime = end_datetime.replace(hour=23, minute=59, second=59)
            date_filter["$lte"] = end_datetime
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid end_date format. Use YYYY-MM-DD"
            )
    
    if date_filter:
        query["created_at"] = date_filter
    
    # Run the query
    cursor = db["orders"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    orders = await cursor.to_list(length=limit)
    
    return orders


@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: str = Path(..., description="The ID of the order to retrieve"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get a single order by ID.
    """
    # Validate the order ID
    if not ObjectId.is_valid(order_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid order ID format"
        )
    
    order = await db["orders"].find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    
    return order


@router.get("/user/{user_id}", response_model=List[OrderResponse])
async def get_user_orders(
    user_id: str = Path(..., description="User ID to get orders for"),
    skip: int = Query(0, ge=0, description="Number of orders to skip"),
    limit: int = Query(10, ge=1, le=100, description="Max number of orders to return"),
    status: Optional[str] = Query(None, description="Filter by order status"),
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Get all orders for a specific user.
    """
    # Validate the user ID
    if not ObjectId.is_valid(user_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid user ID format"
        )
    
    # Build the query
    query = {"user_id": user_id}
    
    if status:
        if status not in settings.ORDER_STATUS.values():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status. Must be one of: {', '.join(settings.ORDER_STATUS.values())}"
            )
        query["status"] = status
    
    # Run the query
    cursor = db["orders"].find(query).sort("created_at", -1).skip(skip).limit(limit)
    orders = await cursor.to_list(length=limit)
    
    return orders


@router.put("/{order_id}/status", response_model=OrderResponse)
async def update_order_status(
    order_id: str,
    status_update: OrderStatusUpdate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Update the status of an order.
    
    This will validate the status transition and update inventory as needed.
    """
    # Validate the order ID
    if not ObjectId.is_valid(order_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid order ID format"
        )
    
    # Get the current order
    order = await db["orders"].find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    
    current_status = order["status"]
    new_status = status_update.status
    
    # Check if the status transition is allowed
    if new_status not in settings.ALLOWED_STATUS_TRANSITIONS.get(current_status, []):
        allowed = settings.ALLOWED_STATUS_TRANSITIONS.get(current_status, [])
        allowed_str = ", ".join(allowed) if allowed else "none"
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid status transition from '{current_status}' to '{new_status}'. Allowed transitions: {allowed_str}"
        )
    
    # Handle inventory updates for specific transitions
    if current_status == settings.ORDER_STATUS["PENDING"] and new_status in [
        settings.ORDER_STATUS["CANCELLED"]
    ]:
        # Release inventory if order is cancelled from pending state
        for item in order["items"]:
            await inventory_service.release_inventory(
                item["product_id"],
                item["quantity"]
            )
    
    # Update the order status
    updated_order = await db["orders"].find_one_and_update(
        {"_id": ObjectId(order_id)},
        {
            "$set": {
                "status": new_status,
                "updated_at": datetime.utcnow()
            }
        },
        return_document=ReturnDocument.AFTER
    )
    
    logger.info(f"Updated order {order_id} status from {current_status} to {new_status}")
    return updated_order


@router.delete("/{order_id}", status_code=204)
async def cancel_order(
    order_id: str,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: Dict[str, Any] = Depends(get_current_user)
):
    """
    Cancel an order (if not shipped).
    
    This will set the order status to cancelled and release inventory.
    """
    # Validate the order ID
    if not ObjectId.is_valid(order_id):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid order ID format"
        )
    
    # Get the current order
    order = await db["orders"].find_one({"_id": ObjectId(order_id)})
    if not order:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Order with ID {order_id} not found"
        )
    
    current_status = order["status"]
    
    # Check if the order can be cancelled
    non_cancellable = [
        settings.ORDER_STATUS["SHIPPED"], 
        settings.ORDER_STATUS["DELIVERED"],
        settings.ORDER_STATUS["CANCELLED"],
        settings.ORDER_STATUS["REFUNDED"]
    ]
    
    if current_status in non_cancellable:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel order in '{current_status}' status"
        )
    
    # Release inventory if the order was in a state that had reserved inventory
    inventory_states = [
        settings.ORDER_STATUS["PENDING"],
        settings.ORDER_STATUS["PAID"],
        settings.ORDER_STATUS["PROCESSING"]
    ]
    
    if current_status in inventory_states:
        for item in order["items"]:
            await inventory_service.release_inventory(
                item["product_id"],
                item["quantity"]
            )
    
    # Update the order status to cancelled
    await db["orders"].update_one(
        {"_id": ObjectId(order_id)},
        {
            "$set": {
                "status": settings.ORDER_STATUS["CANCELLED"],
                "updated_at": datetime.utcnow()
            }
        }
    )
    
    logger.info(f"Cancelled order {order_id}")
    return None