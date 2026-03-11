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
            telegram_id BIGINT,
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

        electronics_id = await conn.fetchval(
            "SELECT id FROM categories WHERE name = 'Электроника';"
        )
        clothes_id = await conn.fetchval(
            "SELECT id FROM categories WHERE name = 'Одежда';"
        )
        shoes_id = await conn.fetchval(
            "SELECT id FROM categories WHERE name = 'Обувь';"
        )
        accessories_id = await conn.fetchval(
            "SELECT id FROM categories WHERE name = 'Аксессуары';"
        )

        products_count = await conn.fetchval("SELECT COUNT(*) FROM products;")

        if products_count == 0:
            await conn.execute("""
            INSERT INTO products (name, description, price, image_url, category_id, stock) VALUES
            ($1,  $2,  $3,  $4,  $5,  $6),
            ($7,  $8,  $9,  $10, $11, $12),
            ($13, $14, $15, $16, $17, $18),
            ($19, $20, $21, $22, $23, $24),
            ($25, $26, $27, $28, $29, $30),
            ($31, $32, $33, $34, $35, $36)
            """,
            'Смартфон X1',
            'Современный смартфон с отличной камерой',
            120000,
            'https://placehold.co/600x400/png?text=Smartphone+X1',
            electronics_id,
            12,

            'Наушники ProSound',
            'Беспроводные наушники с шумоподавлением',
            25000,
            'https://placehold.co/600x400/png?text=ProSound+Headphones',
            electronics_id,
            20,

            'Умные часы FitTime',
            'Стильные часы для спорта и повседневной жизни',
            30000,
            'https://placehold.co/600x400/png?text=FitTime+Smartwatch',
            electronics_id,
            15,

            'Худи Urban Style',
            'Комфортное худи на каждый день',
            18000,
            'https://placehold.co/600x400/png?text=Urban+Hoodie',
            clothes_id,
            10,

            'Кроссовки RunFast',
            'Лёгкие и удобные кроссовки',
            28000,
            'https://placehold.co/600x400/png?text=RunFast+Sneakers',
            shoes_id,
            8,

            'Рюкзак UrbanBag',
            'Практичный городской рюкзак',
            15000,
            'https://placehold.co/600x400/png?text=UrbanBag+Backpack',
            accessories_id,
            18
            )

        admin_exists = await conn.fetchval(
            "SELECT COUNT(*) FROM admins WHERE login = 'admin';"
        )

        if admin_exists == 0:
            # Логин: admin
            # Пароль: admin123
            await conn.execute("""
            INSERT INTO admins (login, password_hash)
            VALUES ('admin', '$2b$12$J1sZlC0M9M1lE8xM8fB0eOQv5rYx0Kk2lE1eM8pQxF4k0A4C4fG8C');
            """)