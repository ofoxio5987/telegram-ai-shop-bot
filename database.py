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
            budget INTEGER,
            favorite_category TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS admins(
            id SERIAL PRIMARY KEY,
            login TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS categories(
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            description TEXT
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            price INTEGER NOT NULL,
            image_url TEXT,
            category_id INTEGER REFERENCES categories(id) ON DELETE SET NULL,
            stock INTEGER DEFAULT 0,
            is_active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS favorites(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (telegram_id, product_id)
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS cart(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            quantity INTEGER DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (telegram_id, product_id)
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            total_amount INTEGER DEFAULT 0,
            status TEXT DEFAULT 'new',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS order_items(
            id SERIAL PRIMARY KEY,
            order_id INTEGER REFERENCES orders(id) ON DELETE CASCADE,
            product_id INTEGER REFERENCES products(id) ON DELETE CASCADE,
            quantity INTEGER NOT NULL,
            price INTEGER NOT NULL
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS user_actions(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            action_type TEXT NOT NULL,
            product_id INTEGER,
            category_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        await conn.execute("""
        CREATE TABLE IF NOT EXISTS assistant_sessions(
            id SERIAL PRIMARY KEY,
            telegram_id BIGINT NOT NULL,
            category TEXT,
            budget_min INTEGER,
            budget_max INTEGER,
            priority TEXT,
            target_person TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        """)

        categories_count = await conn.fetchval("SELECT COUNT(*) FROM categories;")

        if categories_count == 0:
            await conn.execute("""
            INSERT INTO categories (name, description) VALUES
            ('Электроника', 'Смартфоны, наушники, гаджеты'),
            ('Одежда', 'Повседневная и стильная одежда'),
            ('Обувь', 'Кроссовки, ботинки, туфли'),
            ('Аксессуары', 'Сумки, рюкзаки, часы');
            """)

        products_count = await conn.fetchval("SELECT COUNT(*) FROM products;")

        if products_count == 0:
            await conn.execute("""
            INSERT INTO products (name, description, price, image_url, category_id, stock)
            VALUES
            ('Смартфон X1', 'Современный смартфон с отличной камерой', 120000, '', 1, 12),
            ('Наушники ProSound', 'Беспроводные наушники с шумоподавлением', 25000, '', 1, 20),
            ('Умные часы FitTime', 'Стильные часы для спорта и повседневной жизни', 30000, '', 1, 15),
            ('Худи Urban Style', 'Комфортное худи на каждый день', 18000, '', 2, 10),
            ('Кроссовки RunFast', 'Лёгкие и удобные кроссовки', 28000, '', 3, 8),
            ('Рюкзак UrbanBag', 'Практичный городской рюкзак', 15000, '', 4, 18);
            """)

        admin_count = await conn.fetchval("SELECT COUNT(*) FROM admins;")

        if admin_count == 0:
            # логин: admin
            # пароль: admin123
            await conn.execute("""
            INSERT INTO admins (login, password_hash)
            VALUES ('admin', '$2b$12$J1sZlC0M9M1lE8xM8fB0eOQv5rYx0Kk2lE1eM8pQxF4k0A4C4fG8C');
            """)