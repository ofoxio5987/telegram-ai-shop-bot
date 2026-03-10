import asyncpg
from config import DATABASE_URL


async def connect():
    return await asyncpg.create_pool(DATABASE_URL)


async def create_tables(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE,
            name TEXT,
            interests TEXT,
            budget TEXT
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            name TEXT,
            price INT,
            category TEXT
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id SERIAL PRIMARY KEY,
            user_id INT,
            product_id INT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)