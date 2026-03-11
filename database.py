import asyncpg
from config import DATABASE_URL


async def connect():
    return await asyncpg.create_pool(DATABASE_URL)


async def create_tables(pool):
    async with pool.acquire() as conn:
        await conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT UNIQUE NOT NULL,
            first_name TEXT,
            username TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            price INT NOT NULL,
            category TEXT NOT NULL
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            product_id INT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        count = await conn.fetchval("SELECT COUNT(*) FROM products;")

        if count == 0:
            await conn.execute("""
            INSERT INTO products (name, price, category) VALUES
            ('Смартфон X1', 120000, 'Электроника'),
            ('Наушники ProSound', 25000, 'Электроника'),
            ('Умные часы FitTime', 30000, 'Гаджеты'),
            ('Рюкзак UrbanBag', 15000, 'Аксессуары'),
            ('Кроссовки RunFast', 28000, 'Обувь');
            """)