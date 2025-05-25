
### 🔗 Kafka Integration for Product & Inventory Services (using AutoMQ)

To ensure real-time synchronization between the **Product** and **Inventory** microservices, we integrate them using **Kafka (AutoMQ)** as a high-performance, distributed message broker.

## Why Kafka AutoMQ?

* Connects Product & Inventory services without direct calls.
* Sends product and inventory updates as messages.
* Reliable, scalable, and keeps track of changes.

---
# Workflow Diagram: 
![alt text](images/Kafka_architecture.png)


---

## Explanation of the workflow
### What are Producers and Consumers in Kafka?

* **Producer:** A service that **publishes** events/messages to Kafka.
* **Consumer:** A service that **subscribes to** (reads) messages from Kafka and acts on them.

---

## Service Roles:

1. **User Service** → *Producer Only*

   * Sends `user.created` when a new user registers.
   * Doesn’t need to consume anything.

2. **Product Service** → *Producer Only*

   * Sends `product.created` when a product is added.
   * Doesn’t depend on external Kafka events.

3. **Inventory Service** → *Producer + Consumer*

   * **Consumes** `product.created`, `order.placed` to create stock entries.
   * **Produces** `stock.updated` after stock changes.

4. **Order Service** → *Producer + Consumer*

   * **Consumes** `stock.updated` to verify stock before placing orders.
   * **Produces** `order.placed` after a successful order.

---


Add the following code to the root `docker-compose.yml` file to configure AutoMQ settings:  
```bash
  # Kafka Service (AutoMQ)
  automq:
    image: automq/automq-ce:latest
    ports:
      - "9092:9092"
      - "8080:8080"
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_LISTENERS: PLAINTEXT://0.0.0.0:9092
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://automq:9092
      KAFKA_LOG_DIRS: /kafka-logs
    volumes:
      - automq_data:/kafka-logs
    networks:
      - microservice-network

```
# Kafka AutoMQ Integration for Product Service

This section explains how Kafka AutoMQ is integrated into the Product Service to enable asynchronous, reliable, and scalable messaging for product and inventory events. Kafka acts as a message broker that helps decouple the services, ensuring better performance and real-time synchronization across distributed components.

---

We use the **`aiokafka`** Python library for asynchronous Kafka producer implementation and manage Kafka connection lifecycle with FastAPI startup and shutdown events.


```bash
product-service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   └── products.py    # Handles processing messages from Kafka consumer to update product information
│   │   └── dependencies.py    # Provides Kafka producer/consumer as FastAPI dependencies for injection
│   ├── core/
│   │   └── config.py          # Centralized config for Kafka broker and topic settings
│   ├── db/
│   │   └── (no changes here)
│   ├── models/
│   │   └── (no changes here)
│   ├── services/
│   │   ├── inventory_service.py      # (no changes here)
│   │   ├── kafka_producer.py         # Kafka message publisher service
│   └── main.py                       # Modified to run Kafka consumer 
├── .env                        # Environment variables related to Kafka such as BOOTSTRAP_SERVERS, TOPIC_NAME
├── requirements.txt                  # Includes aiokafka and other dependencies for Kafka integration
├── docker-compose.yml                # May require adding Kafka broker service here if needed
└── Dockerfile                        # (no changes here)

```

Install Dependencies: 
```bash
pip install -r requirements.txt
```

---

## 1. Kafka Setup in `.env`

Add the following environment variables to your Product Service `.env` file:

```bash
KAFKA_BOOTSTRAP_SERVERS=automq:9092
KAFKA_TOPIC=product-topic
```

* `KAFKA_BOOTSTRAP_SERVERS`: Address of the Kafka broker (automq service)
* `KAFKA_TOPIC`: Topic name for product events

---

## 2. Docker Compose Configuration

`docker-compose.yml` file for Product Service includes: ( only the changes part added)

```yaml

    depends_on:
      - mongodb
      - automq        # Kafka broker service dependency
    networks:
      - product-network
      - microservice-network
    environment:
      - USER_SERVICE_URL=http://user-service:8003/api/v1
      - INVENTORY_SERVICE_URL=http://inventory-service:8002/api/v1
      - ORDER_SERVICE_URL=http://order-service:8001/api/v1
      - KAFKA_BOOTSTRAP_SERVERS=automq:9092  # Kafka broker address
```

---

### 3. `config.py` - Kafka Settings

Add new Kafka settings to your configuration:

```python
class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str  # e.g. "automq:9092"
    KAFKA_TOPIC: str              # e.g. "product-topic"

```

---

### 4. `dependencies.py` - Kafka Producer Service Setup

Define a singleton Kafka producer service:

```python
from your_app.kafka_producer import KafkaProducer

kafka_producer = KafkaProducer(
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS
)

async def get_kafka_producer() -> KafkaProducer:
    return kafka_producer
```

---

### 5. `kafka_producer.py` - Implement an async Kafka producer using `aiokafka`.
---

### 6. `main.py` - Register Kafka Startup/Shutdown Handlers

Register Kafka lifecycle events with FastAPI:

```python
from your_app.kafka_producer import start_kafka, stop_kafka

app.add_event_handler("startup", connect_to_mongo)
app.add_event_handler("startup", start_kafka)        # Start Kafka on app startup

app.add_event_handler("shutdown", close_mongo_connection)
app.add_event_handler("shutdown", stop_kafka)        # Stop Kafka on app shutdown
```

---


## 7. Usage: Sending Product Events to Kafka

Whenever a new product is created, the service automatically sends a Kafka event describing the product creation. This allows other microservices or consumers to react asynchronously to product changes.

Here, how the product creation endpoint uses the Kafka producer:

```python

from app.services.kafka_producer import KafkaProducerService
import logging

router = APIRouter()

@router.post("/", response_model=ProductResponse, status_code=201)
async def create_product(
    product: ProductCreate,
    db: AsyncIOMotorDatabase = Depends(get_db),
    current_user: dict = Depends(get_current_user),
    kafka_producer: KafkaProducerService = Depends(get_kafka_producer)
):
    product_dict = product.dict()
    result = await db["products"].insert_one(product_dict)
    created_product = await db["products"].find_one({"_id": result.inserted_id})

    logging.info(f"Created product: {result.inserted_id}")

    # Send product_created event to Kafka topic "products"
    try:
        await kafka_producer.send(
            topic="products",
            message={
                "event": "product_created",
                "product_id": str(result.inserted_id),
                "product_data": product_dict
            }
        )
    except Exception as e:
        logging.error(f"Kafka publish failed: {e}")

    return created_product
```

### Explanation:

* After inserting the new product into MongoDB, the service sends a JSON message to the Kafka topic `products`.
* The message includes the event type, product ID, and the product details.
* Errors during Kafka publishing are logged but do not block the API response.

---

### API Response on Product Creation 

When, create a product (e.g., "Premium Smartphone"), the API responds with the full product data including the generated product ID:

```json
{
  "name": "Premium Smartphone",
  "description": "Latest model with high-end camera and long battery life",
  "category": "Electronics",
  "price": 899.99,
  "quantity": 50,
  "_id": "product_id_1"
}
```

---

### Kafka Event Logs

On the backend, after successfully inserting the product in MongoDB, the Kafka producer sends an event to the `products` topic. The logs reflect this lifecycle:

#### On service startup:

```
INFO: Kafka producer started successfully.
```

#### On sending a product creation event to Kafka:

```
INFO: Sent Kafka message to topic 'products': {
  "event": "product_created",
  "product_id": "product_id_1",
  "product_data": {
    "name": "Premium Smartphone",
    "description": "Latest model with high-end camera and long battery life",
    "category": "Electronics",
    "price": 899.99,
    "quantity": 50
  }
}
```

* This confirms the event was published to the Kafka topic.
* The message contains the event type (`product_created`), the product ID, and the product details.

#### On any Kafka publishing failure (Kafka is down):

```
ERROR: Kafka publish failed for product product_id_1: ConnectionError: ...
```


#### On Service Shutdown

When shutting down the FastAPI service:

```
INFO: Kafka producer stopped gracefully.
```

---


# Now, 
# Kafka AutoMQ Integration for Inventory Service

The service uses FastAPI for APIs, SQLAlchemy for PostgreSQL, and `aiokafka` for asynchronous Kafka operations, with AutoMQ as the broker.

```bash
inventory-service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   └── inventory.py        # Processes messages received from Kafka consumer to update inventory
│   │   └── dependencies.py         # Injects Kafka producer/consumer as FastAPI dependencies
│   ├── core/
│   │   └── config.py               # Centralized configuration for Kafka broker and topic settings
│   ├── db/
│   │   └── (no changes here)
│   ├── models/
│   │   └── (no changes here)
│   ├── services/
│   │   ├── inventory_kafka_service.py   # Business logic to update inventory based on messages from Kafka
│   │   ├── kafka_producer.py            # Service to publish messages to Kafka
│   │   ├── kafka_consumer.py            # Service to consume messages from Kafka
│   │   └── product.py                   # (no changes here)
│   └── main.py                    # Modified to run Kafka consumer as a background task during app runtime
├── .env                      # Environment variables related to Kafka like BOOTSTRAP_SERVERS, TOPIC_NAME
├── requirements.txt                     # Includes dependencies for Kafka integration like aiokafka
├── docker-compose.yml                   # Kafka broker service may need to be added here
└── Dockerfile                           # (no changes here)

```


Install Dependencies: 
```bash
pip install -r requirements.txt
```

## 1. Kafka Setup in `.env`
Add these environment variables to the Inventory Service’s `.env` file:

```env
KAFKA_BOOTSTRAP_SERVERS=automq:9092
KAFKA_PRODUCER_TOPIC=stock-updated
KAFKA_CONSUMER_TOPIC=product-topic
```

- **KAFKA_BOOTSTRAP_SERVERS**: Address of the AutoMQ broker.
- **KAFKA_PRODUCER_TOPIC**: Topic for inventory stock updates (`stock-updated`).
- **KAFKA_CONSUMER_TOPIC**: Topic for product events from Product Service (`product-topic`).

## 2. Docker Compose Configuration
Update `docker-compose.yml` for the Inventory Service with these changes:

```yaml
services:
  inventory-service:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "8002:8002"
    depends_on:
      - postgres
      - automq  # Kafka broker dependency
    networks:
      - inventory-network
      - microservice-network
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=automq:9092
      - PRODUCT_SERVICE_URL=http://product-service:8000/api/v1
```

- Ensures dependency on `automq` service and connects to `microservice-network` for inter-service communication.

## 3. Configuration in `config.py`
Add Kafka settings to `app/core/config.py`:

```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str  # e.g., "automq:9092"
    KAFKA_PRODUCER_TOPIC: str     # e.g., "stock-updated"
    KAFKA_CONSUMER_TOPIC: str     # e.g., "product-topic"
```

## 4. Kafka Producer and Consumer Setup
### 4.1 `kafka_producer.py` - Kafka Producer Implementation
Implement an async Kafka producer in `app/service/kafka_producer.py`.

### 4.2 `dependencies.py` - Kafka Producer Dependency
Define a singleton Kafka producer in `app/api/dependencies.py`:

```python
from app.service.kafka_producer import KafkaProducer
from app.core.config import settings

kafka_producer = KafkaProducerService(
    bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS,
    topic=settings.KAFKA_PRODUCER_TOPIC

)
async def get_kafka_producer() -> KafkaProducer:
    return kafka_producer
```

### 4.3 `kafka_consumer.py` - Kafka Consumer Implementation
Implement an async Kafka consumer in `app/service/kafka_consumer.py`.

## 5. Main Application Setup in `main.py`
Register Kafka lifecycle events in `app/main.py`:

```python
from fastapi import FastAPI
from app.service.kafka_producer import kafka_producer
from app.service.kafka_consumer import kafka_consumer
import asyncio
import logging

logger = logging.getLogger(__name__)
app = FastAPI(title="Inventory Service API")

@app.on_event("startup")
async def on_startup():
    await kafka_producer.start()  # Start Kafka producer
    logger.info(" Kafka producer started")
    asyncio.create_task(kafka_consumer.start())  # Start Kafka consumer in background
    logger.info("Kafka producer and consumer started")

@app.on_event("shutdown")
async def on_shutdown():
    await kafka_producer.stop()  # Stop Kafka producer
    await kafka_consumer.stop()  # Stop Kafka consumer
    logger.info("Kafka producer and consumer stopped")
```

## 6. Usage: Kafka Integration in Inventory Service

### 6.1 Producing to `stock-updated`

The inventory service produces messages to the `stock-updated` topic whenever inventory changes occur (creating, updating, reserving, releasing, or adjusting inventory). These messages are sent via the `InventoryKafkaService.send_stock_update` method, which uses the `KafkaProducer` class to publish messages to AutoMQ.

#### **Scenarios Triggering Producer Messages**
 
The following API endpoints in `inventory.py` trigger a stock update message to the `stock-updated` topic:
- **POST `/api/v1/inventory/`**: Creates a new inventory item.
- **PUT `/api/v1/inventory/{product_id}`**: Updates an existing inventory item’s available quantity.
- **POST `/api/v1/inventory/reserve`**: Reserves inventory, reducing available quantity.
- **POST `/api/v1/inventory/adjust`**: Adjusts inventory (add or remove).
- **POST `/api/v1/inventory/release`**: Releases reserved inventory, increasing available quantity.
- **Low Stock Notification**: The `check_and_notify_low_stock` function sends a stock update when an item’s quantity falls below the reorder threshold.

#### **Producer Output**

- **Scenario**: A new inventory item is created via `POST /api/v1/inventory/` with `product_id="product_id_1"`, `available_quantity=100`.
  - **Kafka Message**:
    ```json
    {
      "product_id": "product_id_1",
      "stock": 100
    }
    ```
  - **Log Output** (from `kafka_producer.py`):
    ```
    INFO:Kafka producer started
    INFO:Sent message to topic stock-updated: {'product_id': 'product_id_1', 'stock': 100}
    ```
- **Scenario**: Reserve 20 units via `POST /api/v1/inventory/reserve` for `product_id="product_id_1"`, reducing available quantity from 100 to 80.
  - **Kafka Message**:
    ```json
    {
      "product_id": "product_id_1",
      "stock": 80
    }
    ```
  - **Log Output**:
    ```
    INFO:Sent message to topic stock-updated: {'product_id': 'product_id_1', 'stock': 80}
    INFO:Reserved 20 units of product product_id_1
    ```
- **Scenario**: Low stock detected (e.g., `available_quantity=4`, `reorder_threshold=5`) after an adjustment.
  - **Kafka Message**:
    ```json
    {
      "product_id": "product_id_1",
      "stock": 4
    }
    ```
  - **Log Output**:
    ```
    INFO:Sent low stock notification for product product_id_1 via Kafka
    INFO:Sent message to topic stock-updated: {'product_id': 'product_id_1', 'stock': 4}
    ```

### 6.2 Consuming from `product-topic`
The service consumes product events from `product-topic`. Message from Product Service:

```json
{
  "name": "Premium Smartphone",
  "description": "Latest model with high-end camera and long battery life",
  "category": "Electronics",
  "price": 899.99,
  "quantity": 50,
  "_id": "product_id_1"
}
```

In `inventory_kafka_service.py`:

```python
import json
import logging

logger = logging.getLogger(__name__)

class InventoryKafkaService:
    @staticmethod
    async def send_stock_update(product_id: str, stock: int):
        message = {"product_id": product_id, "stock": stock}
        await kafka_producer.send(settings.KAFKA_PRODUCER_TOPIC, message)

    @staticmethod
    async def process_consumed_message(message_bytes: bytes):
        try:
            message = json.loads(message_bytes.decode("utf-8"))
            logger.info(f"Processing consumed message: {message}")
            # TODO: Add logic to create/update inventory using message["_id"] and message["quantity"]
        except Exception as e:
            logger.error(f"Error processing consumed message: {e}")
```

- **Log Output** (from `kafka_consumer.py` and `inventory_kafka_service.py`):
    ```
    INFO:Kafka consumer started for topics: ['product-topic']

    INFO:Consumed message: topic=product-topic key=None value=b'{"name": "Premium Smartphone", 
    "description": "Latest model with high-end camera and long battery life", "category": "Electronics", 
    "price": 899.99, "quantity": 50, "_id": "product_id_1"}'

    INFO:Processing consumed message: {'name': 'Premium Smartphone', 'description': 'Latest model with 
    high-end camera and long battery life', 'category': 'Electronics', 'price': 899.99, 'quantity': 50, 
    '_id': 'product_id_1'}

    ```

## 7. API Response and Kafka Event Logs
- **API Response** (e.g., `POST /api/v1/inventory/`):
  ```json
  {
    "id": 1,
    "product_id": "product_id_1",
    "available_quantity": 100,
    "reserved_quantity": 0,
    "reorder_threshold": 5,
    "created_at": "2025-05-25T10:42:00+06:00",
    "updated_at": "2025-05-25T10:42:00+06:00"
  }
  ```
- **Kafka Producer Logs**:
  ```
  INFO:Kafka producer started
  INFO:Sent message to topic stock-updated: {'product_id': 'product_id_1', 'stock': 100}
  ```
- **Kafka Consumer Logs**:
  ```
  INFO:Kafka consumer started for topics: ['product-topic']
  INFO:Processing consumed message: {'name': 'Premium Smartphone', ...}
  ```
- **Error Case** (e.g., AutoMQ down):
  ```
  ERROR:Failed to send message: ConnectionError: ...
  ```

#### 8. Testing the Integration
1. **Start Service**:
   ```bash
   docker-compose up --build
   ```
2. **Produce Message**:
   ```bash
   curl -X POST http://localhost:8002/api/v1/inventory -H "Content-Type: application/json" -d '{"product_id": "product_id_1", "available_quantity": 100, "reserved_quantity": 0, "reorder_threshold": 5}'
   ```
   Verify: `kafka-console-consumer --bootstrap-server automq:9092 --topic stock-updated --from-beginning`
3. **Consume Message**:
   ```bash
   kafka-console-producer --broker-list automq:9092 --topic product-topic
   > {"name": "Premium Smartphone", "description": "Latest model...", "category": "Electronics", "price": 899.99, "quantity": 50, "_id": "product_id_1" 
   }
   ```


- **AutoMQ**: Provides scalable, low-latency, S3-based Kafka-compatible messaging.

---











