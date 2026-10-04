from typing import Optional
from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from app.config import settings
from app.logging import logger

client: Optional[AsyncIOMotorClient] = None
db: Optional[AsyncIOMotorDatabase] = None


async def connect_to_mongodb() -> AsyncIOMotorDatabase:
    global client, db
    logger.info(f"Connecting to MongoDB at {settings.MONGODB_URI} (db: {settings.MONGODB_DB_NAME})")
    client = AsyncIOMotorClient(settings.MONGODB_URI)
    db = client[settings.MONGODB_DB_NAME]
    return db


async def close_mongodb_connection() -> None:
    global client
    if client:
        logger.info("Closing MongoDB connection")
        client.close()
        client = None


def get_database() -> AsyncIOMotorDatabase:
    if db is None:
        raise RuntimeError("Database is not connected. Call connect_to_mongodb() first.")
    return db


async def init_db_indexes(database: AsyncIOMotorDatabase) -> None:
    """Ensure required indexes are created for performance and tenant isolation."""
    try:
        # Cafes
        await database.cafes.create_index([("slug", 1)], unique=True, sparse=True)

        # Tables
        await database.tables.create_index([("cafe_id", 1), ("number", 1)], unique=True)
        await database.tables.create_index([("cafe_id", 1), ("qr_token", 1)], unique=True)

        # Staff Users
        await database.staff_users.create_index([("email", 1)], unique=True)
        await database.staff_users.create_index([("cafe_id", 1), ("role", 1)])

        # Menu Items
        await database.menu_items.create_index([("cafe_id", 1), ("status", 1), ("category", 1)])
        await database.menu_items.create_index([("cafe_id", 1), ("is_available", 1)])

        # Menu Categories
        await database.menu_categories.create_index([("cafe_id", 1), ("sort_order", 1)])

        # Carts (TTL on updated_at: 24h)
        await database.carts.create_index([("session_id", 1)], unique=True)
        await database.carts.create_index([("cafe_id", 1), ("session_id", 1)])
        await database.carts.create_index([("updated_at", 1)], expireAfterSeconds=86400)

        # Orders
        await database.orders.create_index([("cafe_id", 1), ("order_status", 1), ("created_at", -1)])
        await database.orders.create_index([("cafe_id", 1), ("table_id", 1), ("created_at", -1)])
        await database.orders.create_index([("cafe_id", 1), ("session_id", 1), ("created_at", -1)])
        await database.orders.create_index([("idempotency_key", 1)], unique=True, sparse=True)
        # Partial unique index for UTR when provided
        await database.orders.create_index(
            [("cafe_id", 1), ("payments.utr", 1)],
            unique=True,
            sparse=True
        )

        # Bills
        await database.bills.create_index([("cafe_id", 1), ("order_id", 1)], unique=True)
        await database.bills.create_index([("cafe_id", 1), ("bill_number", 1)], unique=True)

        # Events (domain event store with sequence)
        await database.events.create_index([("cafe_id", 1), ("seq", 1)], unique=True)
        await database.events.create_index([("created_at", 1)], expireAfterSeconds=172800)  # 48h TTL

        # Counters (atomic bill numbers and sequence numbers)
        await database.counters.create_index([("cafe_id", 1), ("key", 1)], unique=True)

        # Customer Sessions
        await database.sessions.create_index([("session_id", 1)], unique=True)
        await database.sessions.create_index([("expires_at", 1)], expireAfterSeconds=0)

        logger.info("MongoDB indexes verified successfully.")
    except Exception as e:
        logger.warning(f"Index initialization warning (could be running without live replica set): {e}")
