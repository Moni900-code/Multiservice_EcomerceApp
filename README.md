

## Apache Kafka Integration for Product & Inventory Services

To ensure real-time synchronization between the **Product** and **Inventory** microservices, we use **Apache Kafka** as a distributed message broker.

### Why Apache Kafka?

- **Decoupling**: Enables asynchronous communication between services without direct API calls.
- **Event-Driven**: Publishes product and inventory updates to Kafka topics for real-time processing.
- **Reliable & Scalable**: Offers fault-tolerant messaging with high throughput and persistent storage.

---

## Workflow Diagram
![Kafka Architecture](images/Workflow.svg)

---

## Explanation of the Workflow

### What are Producers and Consumers in Kafka?

- **Producer**: Publishes events/messages to a Kafka topic.
- **Consumer**: Subscribes to and processes messages from a Kafka topic.

### Service Roles

1. **User Service** → *Producer Only*
   - Sends `user.created` events when a new user registers.
   - Does not consume Kafka messages.

2. **Product Service** → *Producer Only*
   - Sends `product.created` events when a product is added.
   - Does not depend on external Kafka events.

3. **Inventory Service** → *Producer + Consumer*
   - **Consumes**: `product.created` (from Product Service) and `order.placed` (from Order Service) to create/update stock entries.
   - **Produces**: `stock.updated` after inventory changes.

4. **Order Service** → *Producer + Consumer*
   - **Consumes**: `stock.updated` to verify stock availability before placing orders.
   - **Produces**: `order.placed` after a successful order.

---

## Kafka Setup and Configuration

### Docker Compose Configuration for Apache Kafka

Add the following to the root `docker-compose.yml` to configure Apache Kafka and ZooKeeper:

```yaml
kafka:
    image: bitnami/kafka:3.4
    container_name: kafka
    ports:
      - "9092:9092"
    environment:
      - KAFKA_CFG_BROKER_ID=1
      - KAFKA_CFG_ZOOKEEPER_CONNECT=zookeeper:2181
      - KAFKA_CFG_LISTENERS=PLAINTEXT://:9092
      - KAFKA_CFG_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092
      - KAFKA_CFG_LISTENER_SECURITY_PROTOCOL_MAP=PLAINTEXT:PLAINTEXT
      - ALLOW_PLAINTEXT_LISTENER=yes
      - KAFKA_CFG_AUTO_CREATE_TOPICS_ENABLE=true
      - KAFKA_CFG_NUM_PARTITIONS=3
      - KAFKA_CFG_DEFAULT_REPLICATION_FACTOR=1
      - KAFKA_AUTO_CREATE_TOPICS_ENABLE=true
    depends_on:
      zookeeper:
        condition: service_healthy
    networks:
      - microservice-network
    volumes:
      - kafka_data:/bitnami/kafka
    healthcheck:
      test: ["CMD-SHELL", "kafka-topics.sh --bootstrap-server localhost:9092 --list"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: on-failure
  zookeeper:
    image: bitnami/zookeeper:latest
    ports:
      - "2181:2181"
    environment:
      - ALLOW_ANONYMOUS_LOGIN=yes
      - ZOO_4LW_COMMANDS_WHITELIST=mntr,srvr,ruok
    networks:
      - microservice-network
    volumes:
      - zookeeper_data:/bitnami/zookeeper
    healthcheck:
      test: ["CMD-SHELL", "echo ruok | nc -w 3 localhost 2181 | grep imok"]
      interval: 10s
      timeout: 5s
      retries: 5
    restart: on-failure
networks:
  microservice-network:
    driver: bridge
volumes:
  mongodb_product_data:
  mongodb_order_data:
  postgres_inventory_data:
  postgres_user_data:
  kafka_data:
  zookeeper_data:
```

**Explanation**:
- **ZooKeeper**: Manages Kafka's metadata, such as topic configurations and broker coordination.
- **Kafka**: Configured with a single broker (ID: 1) listening on `kafka:9092`. The `KAFKA_ADVERTISED_LISTENERS` ensures services connect using the `kafka` hostname within the `microservice-network`.
- **Volumes**: Persist Kafka and ZooKeeper data.
- **Networks**: Ensures all services communicate over the `microservice-network`.

---

### Kafka Integration for Product Service

The Product Service uses the `aiokafka` Python library for asynchronous Kafka producer operations, with lifecycle management via FastAPI startup and shutdown events.

#### Directory Structure
```bash
product-service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   └── products.py    # Handles product creation and publishes to Kafka
│   │   └── dependencies.py    # Provides Kafka producer as a FastAPI dependency
│   ├── core/
│   │   └── config.py          # Kafka broker and topic settings
│   ├── db/
│   │   └── (no changes)
│   ├── models/
│   │   └── (no changes)
│   ├── services/
│   │   ├── inventory_service.py      # (no changes)
│   │   ├── kafka_producer.py         # Kafka message publisher
│   └── main.py                       # Registers Kafka lifecycle events
├── .env                              # Kafka environment variables
├── requirements.txt                  # Includes aiokafka
├── docker-compose.yml                # Includes Kafka dependency
└── Dockerfile                        # (no changes)
```

### Some base files: 

**requirements.txt**:
```text
fastapi
uvicorn
pymongo
aiokafka
```

#### Kafka Setup in `.env`
Add to `product-service/.env`:
```env
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_TOPIC=product-topic
```

#### Docker Compose Configuration
Update `product-service/docker-compose.yml`:
```yaml
services:
  product-service:
    .....
    depends_on:
      - mongodb
      - kafka
    networks:
      - product-network
      - microservice-network
    environment:
      - USER_SERVICE_URL=http://user-service:8003/api/v1
      - INVENTORY_SERVICE_URL=http://inventory-service:8002/api/v1
      - ORDER_SERVICE_URL=http://order-service:8001/api/v1
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - KAFKA_TOPIC=product-topic
```

#### Configuration in `config.py`
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_TOPIC: str = "product-topic"
```

#### Dependencies in `dependencies.py`
```python
from app.services.kafka_producer import KafkaProducerService
from app.core.config import settings

kafka_producer = KafkaProducerService(bootstrap_servers=settings.KAFKA_BOOTSTRAP_SERVERS)

async def get_kafka_producer() -> KafkaProducerService:
    return kafka_producer
```




### Kafka Integration for Inventory Service

The Inventory Service uses FastAPI for APIs, SQLAlchemy for PostgreSQL, and `aiokafka` for asynchronous Kafka producer and consumer operations.

#### Directory Structure
```bash
inventory-service/
├── app/
│   ├── api/
│   │   ├── routes/
│   │   │   └── inventory.py        # Processes Kafka messages to update inventory
│   │   └── dependencies.py         # Kafka producer/consumer dependencies
│   ├── core/
│   │   └── config.py               # Kafka settings
│   ├── db/
│   │   └── (no changes)
│   ├── models/
│   │   └── (no changes)
│   ├── services/
│   │   ├── inventory_kafka_service.py   # Logic for inventory updates from Kafka
│   │   ├── kafka_producer.py            # Publishes to Kafka
│   │   ├── kafka_consumer.py            # Consumes from Kafka
│   │   └── product.py                   # (no changes)
│   └── main.py                          # Runs Kafka consumer as a background task
├── .env
├── requirements.txt
├── docker-compose.yml
└── Dockerfile
```
### Some base files: 

**requirements.txt**:
```text
fastapi
uvicorn
sqlalchemy
psycopg2-binary
aiokafka
```

#### Kafka Setup in `.env`
Add to `inventory-service/.env`:
```env
KAFKA_BOOTSTRAP_SERVERS=kafka:9092
KAFKA_PRODUCER_TOPIC=stock-updated
KAFKA_CONSUMER_TOPIC=product-topic
```

#### Docker Compose Configuration
Update `inventory-service/docker-compose.yml`:
```yaml
services:
  inventory-service:
    ......
    depends_on:
      - postgres
      - kafka
    networks:
      - inventory-network
      - microservice-network
    environment:
      - KAFKA_BOOTSTRAP_SERVERS=kafka:9092
      - KAFKA_PRODUCER_TOPIC=stock-updated
      - KAFKA_CONSUMER_TOPIC=product-topic
      - PRODUCT_SERVICE_URL=http://product-service:8000/api/v1
```

#### Configuration in `config.py`
```python
from pydantic import BaseSettings

class Settings(BaseSettings):
    KAFKA_BOOTSTRAP_SERVERS: str = "kafka:9092"
    KAFKA_PRODUCER_TOPIC: str = "stock-updated"
    KAFKA_CONSUMER_TOPIC: str = "product-topic"
```


## Test the Apache Kafka Integration:

**Command:**
```bash
docker-compose up --build -d
docker ps
```
### Check Kafka Broker API Versions
**Command:**
```bash
docker exec -it kafka kafka-broker-api-versions.sh --bootstrap-server kafka:9092
```

**Explanation:**
Queries the API versions supported by the Kafka broker at `kafka:9092`. 

**Expected Output:**
```
kafka:9092 (id: 1 rack: null) -> (
        Produce(0): 0 to 9 [usable: 9],
        Fetch(1): 0 to 13 [usable: 13],
        ListOffsets(2): 0 to 7 [usable: 7],
        Metadata(3): 0 to 12 [usable: 12],
        LeaderAndIsr(4): 0 to 7 [usable: 7],
        StopReplica(5): 0 to 4 [usable: 4],
        UpdateMetadata(6): 0 to 8 [usable: 8],
        ControlledShutdown(7): 0 to 3 [usable: 3],……)
```

### Verify Kafka-ZooKeeper Connection
**Command:**
```bash
docker-compose logs kafka | grep zookeeper
```

**Explanation:**
Filters Kafka service logs for ZooKeeper-related entries, confirming successful connection to ZooKeeper at `zookeeper:2181`.

**Expected Output:**
```
kafka  | [2025-05-31 11:07:09,455] INFO Session establishment complete on server zookeeper/172.23.0.2:2181, session id = 0x100005b4d7c0000, negotiated timeout = 18000 (org.apache.zookeeper.ClientCnxn)
kafka  | [2025-05-31 11:07:09,459] INFO [ZooKeeperClient Kafka server] Connected. (kafka.zookeeper.ZooKeeperClient)
```

### List Docker Networks
**Command:**
```bash
docker network ls
```

**Expected Output:**
```
NETWORK ID     NAME                                            DRIVER    SCOPE
e194cecbd5b9   bridge                                          bridge    local
e9c43590a756   host                                            host      local
d8bcb8355959   multiservice_ecomerceapp_microservice-network   bridge    local
488862115c3a   none                                           null      local
```

### Inspect Docker Network
**Command:**
```bash
docker network inspect multiservice_ecomerceapp_microservice-network
```

**Explanation:**
Provides details about the `microservice-network`, including connected containers (e.g., Kafka, ZooKeeper, services) and their IP addresses in the `172.23.0.0/16` subnet.



### Health Checks for Services
**Commands:**
```bash
curl -f http://localhost:8000/health
curl -f http://localhost:8001/health
curl -f http://localhost:8002/health
curl -f http://localhost:8003/health
``` 
**Expected Output:**
```
{"status":"ok","service":"product-service"}
{"status":"ok","service":"order-service"}
{"status":"ok","service":"inventory-service"}
{"status":"ok","service":"user-service"}
```

### Logs Checks for Services
**Commands:**
```bash
docker-compose logs product-service
docker-compose logs inventory-service
docker-compose logs order-service
docker-compose logs user-service

``` 


### Install `jq` for JSON Parsing
**Command:**
```bash
apt-get update && apt-get install -y jq
```

**Explanation:**
Updates the package index and installs `jq`, a command-line JSON processor, used to format API responses in subsequent commands.


### Register User (First Attempt)
**Command:**

```bash
curl -X POST "http://localhost/api/v1/auth/register" \
-H "Content-Type: application/json" \
-d '{
"email": "admin@example.com",
"password": "Admin123",
"first_name": "John",
"last_name": "song",
"phone": "555-123-4567"
}' | jq .
```

**Explanation:**
Successfully registers a user with a stronger password. The response includes user details and a unique ID, formatted by `jq`.

**Expected Output:**
```
{
  "email": "admin@example.com",
  "first_name": "John",
  "last_name": "song",
  "phone": "555-123-4567",
  "id": 1,
  "is_active": true,
  "created_at": "2025-05-31T11:22:44.112506+00:00",
  "addresses": []
}
```

### User Login
**Command:**
```bash
curl -X POST "http://localhost/api/v1/auth/login" \
-H "Content-Type: application/x-www-form-urlencoded" \
-d "username=admin@example.com&password=Admin123" | jq .
```

**Expected Output:**
```
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzQ4NjkyNDAzLCJ0eXBlIjoiYWNjZXNzIn0.vju9Nq-pFLZockxLBkF3J3fU_wS8LE0_whDFYwtwlWE",
  "refresh_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxIiwiZXhwIjoxNzQ5Mjk1NDAzLCJ0eXBlIjoicmVmcmVzaCJ9.-2WdDezPIMroZZkiVUsE3KfPT2Xl3_qxbxiQox96ZKo",
  "token_type": "bearer"
}
```

### Set Environment Variable for Token
**Command:**
```bash
export TOKEN="access_token replace here"
```

**Explanation:**
Sets the `TOKEN` environment variable with the access token from the login response for use in authenticated API calls.


### Get Current User Details
**Command:**
```bash
curl -X GET "http://localhost/api/v1/users/me" \
-H "Authorization: Bearer $TOKEN" | jq .
```

**Expected Output:**
```
{
  "email": "admin@example.com",
  "first_name": "John",
  "last_name": "song",
  "phone": "555-123-4567",
  "id": 1,
  "is_active": true,
  "created_at": "2025-05-31T11:22:44.112506+00:00",
  "addresses": []
}
```

### Create a Product
**Command:**
```bash
curl -X POST "http://localhost/api/v1/products/" \
-H "Authorization: Bearer $TOKEN" \
-H "Content-Type: application/json" \
-d '{
"name": "Premium Smartphone",
"description": "Latest model with high-end camera and long battery life",
"category": "Electronics",
"price": 899.99,
"quantity": 50
}' | jq .
```

**Expected Output:**
```
{
  "name": "Premium Smartphone",
  "description": "Latest model with high-end camera and long battery life",
  "category": "Electronics",
  "price": 899.99,
  "quantity": 50,
  "_id": "683ae74305f79b34a72b6ce4"
}
```

### List All Products
**Command:**
```bash
curl -X GET "http://localhost/api/v1/products/" \
-H "Authorization: Bearer $TOKEN" | jq .
```

**Expected Output:**
```
  {
    "name": "Premium Smartphone",
    "description": "Latest model with high-end camera and long battery life",
    "category": "Electronics",
    "price": 899.99,
    "quantity": 50,
    "_id": "683ae74305f79b34a72b6ce4"
  }

```
## Product Service:

### Verify Product Service Kafka Integration
**Command:**
```bash
docker-compose logs product-service | grep kafka
```

**Expected Output:**
```
multiservice_ecomerceapp-product-service-1  | INFO:app.services.kafka_producer:Kafka producer started with servers: kafka:9092
```

### Verify Product Creation Event in Kafka
**Command:**
```bash
docker-compose logs product-service | grep product-topic
```

**Expected Output:**
```
multiservice_ecomerceapp-product-service-1  | INFO:app.api.routes.products:Published product creation event to product-topic: 683ae74305f79b34a72b6ce4
```

## Inventory Service:

### Create Kafka Topic (`stock-updated`)
**Command:**
```bash
docker exec -it kafka kafka-topics.sh --bootstrap-server kafka:9092 --create --topic stock-updated --partitions 3 --replication-factor 1
```

**Expected Output:**
```
Created topic stock-updated.
```

### List Kafka Topics
**Command:**
```bash
docker exec -it kafka kafka-topics.sh --bootstrap-server kafka:9092 --list
```

**Expected Output:**
```
__consumer_offsets
product-topic
stock-updated
```

Lists all Kafka topics, confirming the presence of `__consumer_offsets` (internal Kafka topic), `product-topic` (for product events), and `stock-updated` (for inventory updates).

### Describe Kafka Topic (`stock-updated`)
**Command:**
```bash
docker exec -it kafka kafka-topics.sh --bootstrap-server kafka:9092 --describe --topic stock-updated
```

**Expected Output:**
```
Topic: stock-updated    TopicId: HonteEkqQRGIBrfE6N-JDg PartitionCount: 3       ReplicationFactor: 1    Configs: 
        Topic: stock-updated    Partition: 0    Leader: 1       Replicas: 1     Isr: 1
        Topic: stock-updated    Partition: 1    Leader: 1       Replicas: 1     Isr: 1
        Topic: stock-updated    Partition: 2    Leader: 1       Replicas: 1     Isr: 1
```

### Verify Inventory Service Kafka Integration
**Command:**
```bash
docker-compose logs inventory-service | grep kafka
```

### Kafka Consumer (Listening to `product-topic`)

The `inventory-service` acts as a **consumer** to listen for product-related events on the Kafka topic `product-topic`. It subscribes to the topic and processes messages related to new products or stock updates.

**Expected Output:**

```plaintext
Received message from product-topic:
{
  'event': 'product_created',
  'product_id': '683b273557b9aa8bd0812cb3',
  'product_data': {
    'name': 'Premium Smartphone',
    'description': 'Latest model with high-end camera and long battery life',
    'category': 'Electronics',
    'price': 899.99,
    'quantity': 50,
    '_id': '683b273557b9aa8bd0812cb3'
  }
}
```

> The service correctly listens for the `product_created` event and extracts product information to update its inventory.

---

### Kafka Producer (Publishing to `stock-updated`)

#### Sample Producer Activity:

```plaintext
Sent stock update to stock-updated:
{
  'product_id': '683b273557b9aa8bd0812cb3',
  'stock': 50
}
```

---

### Start/Stop Logs (Informational)

* Kafka producer started and stopped successfully:

  ```
  Kafka producer started
  Kafka producer stopped
  ```

* Kafka consumer started and left the group cleanly:

  ```
  Kafka consumer started
  Kafka consumer stopped
  ```

---

### Initial Warnings (Handled Automatically)

Initially, the topic `product-topic` was not available during the consumer startup:

```plaintext
WARNING - Topic product-topic is not available during auto-create initialization
ERROR - GroupCoordinatorNotAvailableError
```

These warnings were temporary and automatically resolved once the topic became available and the consumer joined the Kafka group successfully.

---

