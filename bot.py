import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from database import connect, create_tables
from keyboards.user_kb import get_main_menu, get_categories_menu
from keyboards.inline_kb import product_inline_keyboard, cart_inline_keyboard
from keyboards.admin_kb import get_admin_menu
from states.product_states import AddProduct, EditProduct, DeleteProduct
from states.category_states import AddCategory, EditCategory, DeleteCategory
from states.assistant_states import SearchState, AssistantState

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
pool = None

admin_auth_stage = {}
admin_auth_data = {}


async def save_user(message: types.Message):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO users (telegram_id, first_name, username)
            VALUES ($1, $2, $3)
            ON CONFLICT (telegram_id) DO NOTHING;
            """,
            message.from_user.id,
            message.from_user.first_name,
            message.from_user.username
        )


async def log_action(telegram_id: int, action_type: str, product_id=None, category_id=None):
    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO user_actions (telegram_id, action_type, product_id, category_id)
            VALUES ($1, $2, $3, $4)
            """,
            telegram_id,
            action_type,
            product_id,
            category_id
        )


async def is_admin(telegram_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM admins WHERE telegram_id = $1",
            telegram_id
        )
    return result > 0


async def send_product_card(message: types.Message, row):
    caption = (
        f"📦 {row['name']}\n"
        f"📝 {row['description']}\n"
        f"💰 Цена: {row['price']} ₸\n"
        f"📦 В наличии: {row['stock']}"
    )

    image_url = row["image_url"]

    if image_url and str(image_url).strip():
        try:
            await message.answer_photo(
                photo=image_url,
                caption=caption,
                reply_markup=product_inline_keyboard(row["id"])
            )
            return
        except Exception:
            pass

    await message.answer(
        caption,
        reply_markup=product_inline_keyboard(row["id"])
    )


async def show_products_by_category(message: types.Message, category_name: str, emoji: str):
    try:
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT p.id, p.name, p.description, p.price, p.stock, p.image_url
                FROM products p
                JOIN categories c ON p.category_id = c.id
                WHERE c.name = $1 AND p.is_active = TRUE
                ORDER BY p.id
                """,
                category_name
            )

        if not rows:
            await message.answer(
                f"В категории {category_name} пока нет товаров.",
                reply_markup=get_main_menu()
            )
            return

        await message.answer(f"{emoji} Категория: {category_name}")

        for row in rows:
            await send_product_card(message, row)

    except Exception as e:
        await message.answer(
            f"Ошибка при открытии категории: {e}",
            reply_markup=get_main_menu()
        )


@dp.message(CommandStart())
async def start(message: types.Message):
    await save_user(message)

    await message.answer(
        "🤖 Добро пожаловать в интеллектуальный магазин!\n\n"
        "Теперь вы можете пользоваться меню как в настоящем магазине Telegram 👇",
        reply_markup=get_main_menu()
    )


# ---------- ВХОД В АДМИНКУ ----------

@dp.message(F.text == "🔐 Админ-вход")
async def admin_login_start(message: types.Message):
    user_id = message.from_user.id
    admin_auth_stage[user_id] = "login"
    admin_auth_data[user_id] = {}
    await message.answer("Введите логин администратора:")


@dp.message(lambda message: admin_auth_stage.get(message.from_user.id) == "login")
async def admin_login_input(message: types.Message):
    user_id = message.from_user.id
    admin_auth_data[user_id] = {"login": message.text.strip()}
    admin_auth_stage[user_id] = "password"
    await message.answer("Введите пароль:")


@dp.message(lambda message: admin_auth_stage.get(message.from_user.id) == "password")
async def admin_password_input(message: types.Message):
    user_id = message.from_user.id
    login = admin_auth_data.get(user_id, {}).get("login")
    password = message.text.strip()

    async with pool.acquire() as conn:
        admin = await conn.fetchrow(
            "SELECT id, login, password_hash FROM admins WHERE login = $1",
            login
        )

    if not admin:
        admin_auth_stage.pop(user_id, None)
        admin_auth_data.pop(user_id, None)
        await message.answer("Неверный логин.", reply_markup=get_main_menu())
        return

    if password != admin["password_hash"]:
        admin_auth_stage.pop(user_id, None)
        admin_auth_data.pop(user_id, None)
        await message.answer("Неверный пароль.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE admins SET telegram_id = $1 WHERE login = $2",
            user_id,
            login
        )

    admin_auth_stage.pop(user_id, None)
    admin_auth_data.pop(user_id, None)

    await message.answer(
        "✅ Вход в админ-панель выполнен успешно.",
        reply_markup=get_admin_menu()
    )


# ---------- ПОЛЬЗОВАТЕЛЬСКАЯ ЧАСТЬ ----------

@dp.message(F.text == "ℹ️ Помощь")
async def help_handler(message: types.Message):
    await message.answer(
        "📌 Возможности бота:\n\n"
        "🛒 Каталог — просмотр товаров\n"
        "🔍 Поиск — поиск по названию\n"
        "❤️ Избранное — сохранённые товары\n"
        "🧺 Корзина — товары к заказу\n"
        "🎯 Рекомендации — персональные предложения\n"
        "🤖 Умный помощник — подбор товара\n"
        "👤 Профиль — ваши данные\n"
        "🔐 Админ-вход — вход в админ-панель",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🛒 Каталог")
async def catalog_handler(message: types.Message):
    await log_action(message.from_user.id, "open_catalog")
    await message.answer(
        "Выберите категорию товаров 👇",
        reply_markup=get_categories_menu()
    )


@dp.message(F.text == "📱 Электроника")
async def electronics_handler(message: types.Message):
    await log_action(message.from_user.id, "open_category")
    await show_products_by_category(message, "Электроника", "📱")


@dp.message(F.text == "👕 Одежда")
async def clothes_handler(message: types.Message):
    await log_action(message.from_user.id, "open_category")
    await show_products_by_category(message, "Одежда", "👕")


@dp.message(F.text == "👟 Обувь")
async def shoes_handler(message: types.Message):
    await log_action(message.from_user.id, "open_category")
    await show_products_by_category(message, "Обувь", "👟")


@dp.message(F.text == "🎒 Аксессуары")
async def accessories_handler(message: types.Message):
    await log_action(message.from_user.id, "open_category")
    await show_products_by_category(message, "Аксессуары", "🎒")


@dp.callback_query(F.data.startswith("fav_"))
async def add_to_favorites(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO favorites (telegram_id, product_id)
            VALUES ($1, $2)
            ON CONFLICT (telegram_id, product_id) DO NOTHING;
            """,
            callback.from_user.id,
            product_id
        )

    await log_action(callback.from_user.id, "add_to_favorite", product_id=product_id)
    await callback.answer("Товар добавлен в избранное ❤️")


@dp.callback_query(F.data.startswith("cart_"))
async def add_to_cart(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[1])

    async with pool.acquire() as conn:
        await conn.execute(
            """
            INSERT INTO cart (telegram_id, product_id, quantity)
            VALUES ($1, $2, 1)
            ON CONFLICT (telegram_id, product_id)
            DO UPDATE SET quantity = cart.quantity + 1;
            """,
            callback.from_user.id,
            product_id
        )

    await log_action(callback.from_user.id, "add_to_cart", product_id=product_id)
    await callback.answer("Товар добавлен в корзину 🧺")


@dp.message(F.text == "❤️ Избранное")
async def favorites_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.id, p.name, p.description, p.price, p.stock, p.image_url
            FROM favorites f
            JOIN products p ON f.product_id = p.id
            WHERE f.telegram_id = $1
            ORDER BY f.id DESC
            """,
            message.from_user.id
        )

    if not rows:
        await message.answer(
            "У вас пока нет избранных товаров.",
            reply_markup=get_main_menu()
        )
        return

    await message.answer("❤️ Ваше избранное:", reply_markup=get_main_menu())

    for row in rows:
        await send_product_card(message, row)


@dp.message(F.text == "🧺 Корзина")
async def cart_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.price, c.quantity
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.telegram_id = $1
            ORDER BY c.id DESC
            """,
            message.from_user.id
        )

    if not rows:
        await message.answer("Ваша корзина пуста.", reply_markup=get_main_menu())
        return

    total = 0
    text = "🧺 Ваша корзина:\n\n"

    for row in rows:
        item_total = row["price"] * row["quantity"]
        total += item_total
        text += (
            f"📦 {row['name']}\n"
            f"💰 {row['price']} ₸ x {row['quantity']} = {item_total} ₸\n\n"
        )

    text += f"Итого: {total} ₸"

    await message.answer(text, reply_markup=cart_inline_keyboard())
    await message.answer("Главное меню 👇", reply_markup=get_main_menu())


@dp.callback_query(F.data == "clear_cart")
async def clear_cart(callback: CallbackQuery):
    async with pool.acquire() as conn:
        await conn.execute(
            "DELETE FROM cart WHERE telegram_id = $1",
            callback.from_user.id
        )

    await callback.answer("Корзина очищена")
    await callback.message.answer(
        "Корзина успешно очищена 🗑",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🎯 Рекомендации")
async def recommendations_handler(message: types.Message):
    async with pool.acquire() as conn:
        favorite_category = await conn.fetchval(
            """
            SELECT favorite_category
            FROM users
            WHERE telegram_id = $1
            """,
            message.from_user.id
        )

        if favorite_category:
            rows = await conn.fetch(
                """
                SELECT p.name, p.price, p.description
                FROM products p
                JOIN categories c ON p.category_id = c.id
                WHERE c.name = $1 AND p.is_active = TRUE
                ORDER BY p.price ASC
                LIMIT 3
                """,
                favorite_category
            )
        else:
            rows = await conn.fetch(
                """
                SELECT name, price, description
                FROM products
                WHERE is_active = TRUE
                ORDER BY price ASC
                LIMIT 3
                """
            )

    if not rows:
        await message.answer("Пока нет рекомендаций.", reply_markup=get_main_menu())
        return

    text = "🎯 Рекомендации для вас:\n\n"
    for row in rows:
        text += (
            f"📦 {row['name']}\n"
            f"📝 {row['description']}\n"
            f"💰 {row['price']} ₸\n\n"
        )

    if favorite_category:
        text += f"Подобрано с учетом вашей любимой категории: {favorite_category}"

    await message.answer(text, reply_markup=get_main_menu())


@dp.message(F.text == "👤 Профиль")
async def profile_handler(message: types.Message):
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT telegram_id, first_name, username, created_at, budget, favorite_category
            FROM users
            WHERE telegram_id = $1
            """,
            message.from_user.id
        )

        favorites_count = await conn.fetchval(
            "SELECT COUNT(*) FROM favorites WHERE telegram_id = $1",
            message.from_user.id
        )

        cart_count = await conn.fetchval(
            "SELECT COUNT(*) FROM cart WHERE telegram_id = $1",
            message.from_user.id
        )

    if not user:
        await message.answer(
            "Профиль не найден. Нажмите /start",
            reply_markup=get_main_menu()
        )
        return

    username = f"@{user['username']}" if user["username"] else "не указан"
    budget = f"{user['budget']} ₸" if user["budget"] else "не задан"
    favorite_category = user["favorite_category"] if user["favorite_category"] else "не определена"

    await message.answer(
        f"👤 Ваш профиль\n\n"
        f"Имя: {user['first_name']}\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"Username: {username}\n"
        f"Бюджет: {budget}\n"
        f"Любимая категория: {favorite_category}\n"
        f"Избранных товаров: {favorites_count}\n"
        f"Товаров в корзине: {cart_count}\n"
        f"Дата регистрации: {user['created_at']}",
        reply_markup=get_main_menu()
    )


# ---------- ПОИСК ----------

@dp.message(F.text == "🔍 Поиск")
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer("Введите название товара или ключевое слово для поиска:")


@dp.message(SearchState.waiting_for_query)
async def search_process(message: types.Message, state: FSMContext):
    query = message.text.strip()

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, description, price, stock, image_url
            FROM products
            WHERE is_active = TRUE
              AND (
                LOWER(name) LIKE LOWER($1)
                OR LOWER(description) LIKE LOWER($1)
              )
            ORDER BY price ASC
            LIMIT 10
            """,
            f"%{query}%"
        )

    await log_action(message.from_user.id, "search")

    await state.clear()

    if not rows:
        await message.answer("По вашему запросу ничего не найдено.", reply_markup=get_main_menu())
        return

    await message.answer(f"🔍 Найдено товаров: {len(rows)}", reply_markup=get_main_menu())

    for row in rows:
        await send_product_card(message, row)


# ---------- УМНЫЙ ПОМОЩНИК ----------

@dp.message(F.text == "🤖 Умный помощник")
async def assistant_start(message: types.Message, state: FSMContext):
    await state.set_state(AssistantState.waiting_for_category)
    await message.answer(
        "🤖 Умный помощник поможет подобрать товар.\n\n"
        "Напишите интересующую категорию:\n"
        "Электроника / Одежда / Обувь / Аксессуары"
    )


@dp.message(AssistantState.waiting_for_category)
async def assistant_category(message: types.Message, state: FSMContext):
    category = message.text.strip()
    await state.update_data(category=category)
    await state.set_state(AssistantState.waiting_for_budget)
    await message.answer(
        "Введите максимальный бюджет в тенге.\n"
        "Например: 30000"
    )


@dp.message(AssistantState.waiting_for_budget)
async def assistant_budget(message: types.Message, state: FSMContext):
    try:
        budget = int(message.text.strip())
    except ValueError:
        await message.answer("Введите бюджет числом, например: 30000")
        return

    await state.update_data(budget=budget)
    await state.set_state(AssistantState.waiting_for_priority)
    await message.answer(
        "Что для вас важнее?\n"
        "Напишите одно слово:\n"
        "цена / качество / универсальность"
    )


@dp.message(AssistantState.waiting_for_priority)
async def assistant_finish(message: types.Message, state: FSMContext):
    priority = message.text.strip().lower()
    data = await state.get_data()

    category = data.get("category")
    budget = data.get("budget")

    async with pool.acquire() as conn:
        category_exists = await conn.fetchval(
            "SELECT id FROM categories WHERE name = $1",
            category
        )

        if not category_exists:
            await state.clear()
            await message.answer("Такой категории нет. Попробуйте снова.", reply_markup=get_main_menu())
            return

        if priority == "цена":
            order_sql = "ORDER BY p.price ASC"
        elif priority == "качество":
            order_sql = "ORDER BY p.price DESC"
        else:
            order_sql = "ORDER BY p.stock DESC, p.price ASC"

        rows = await conn.fetch(
            f"""
            SELECT p.id, p.name, p.description, p.price, p.stock, p.image_url
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.name = $1
              AND p.price <= $2
              AND p.is_active = TRUE
            {order_sql}
            LIMIT 5
            """,
            category,
            budget
        )

        await conn.execute(
            """
            UPDATE users
            SET budget = $1, favorite_category = $2
            WHERE telegram_id = $3
            """,
            budget,
            category,
            message.from_user.id
        )

        await conn.execute(
            """
            INSERT INTO assistant_sessions (telegram_id, category, budget_max, priority)
            VALUES ($1, $2, $3, $4)
            """,
            message.from_user.id,
            category,
            budget,
            priority
        )

    await state.clear()

    if not rows:
        await message.answer(
            "🤖 Я не нашёл подходящих товаров по этим параметрам.\n"
            "Попробуйте увеличить бюджет или выбрать другую категорию.",
            reply_markup=get_main_menu()
        )
        return

    await message.answer(
        f"🤖 Подобрал товары по вашим параметрам:\n"
        f"Категория: {category}\n"
        f"Бюджет: до {budget} ₸\n"
        f"Приоритет: {priority}",
        reply_markup=get_main_menu()
    )

    for row in rows:
        await send_product_card(message, row)


# ---------- АДМИН-ПАНЕЛЬ ----------

@dp.message(F.text == "📊 Статистика")
async def admin_stats_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
        products_count = await conn.fetchval("SELECT COUNT(*) FROM products")
        categories_count = await conn.fetchval("SELECT COUNT(*) FROM categories")
        favorites_count = await conn.fetchval("SELECT COUNT(*) FROM favorites")
        cart_count = await conn.fetchval("SELECT COUNT(*) FROM cart")
        actions_count = await conn.fetchval("SELECT COUNT(*) FROM user_actions")

        top_categories = await conn.fetch(
            """
            SELECT favorite_category, COUNT(*) AS cnt
            FROM users
            WHERE favorite_category IS NOT NULL
            GROUP BY favorite_category
            ORDER BY cnt DESC
            LIMIT 5
            """
        )

    text = (
        "📊 Статистика магазина\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"📦 Товаров: {products_count}\n"
        f"🗂 Категорий: {categories_count}\n"
        f"❤️ Добавлений в избранное: {favorites_count}\n"
        f"🧺 Товаров в корзинах: {cart_count}\n"
        f"📈 Действий пользователей: {actions_count}\n\n"
        "🔥 Любимые категории пользователей:\n"
    )

    if top_categories:
        for item in top_categories:
            text += f"• {item['favorite_category']} — {item['cnt']}\n"
    else:
        text += "Пока нет данных\n"

    await message.answer(text, reply_markup=get_admin_menu())


@dp.message(F.text == "👥 Пользователи")
async def admin_users_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT first_name, username, telegram_id, created_at
            FROM users
            ORDER BY created_at DESC
            LIMIT 20
            """
        )

    if not rows:
        await message.answer("Пользователей пока нет.", reply_markup=get_admin_menu())
        return

    text = "👥 Последние пользователи:\n\n"
    for row in rows:
        username = f"@{row['username']}" if row["username"] else "не указан"
        text += (
            f"Имя: {row['first_name']}\n"
            f"Username: {username}\n"
            f"ID: {row['telegram_id']}\n"
            f"Дата: {row['created_at']}\n\n"
        )

    await message.answer(text, reply_markup=get_admin_menu())


@dp.message(F.text == "📦 Товары")
async def admin_products_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.price, p.stock, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            ORDER BY p.id
            """
        )

    if not rows:
        await message.answer("Товаров пока нет.", reply_markup=get_admin_menu())
        return

    text = "📦 Список товаров:\n\n"
    for row in rows:
        category = row["category_name"] if row["category_name"] else "без категории"
        text += (
            f"📦 {row['name']}\n"
            f"💰 {row['price']} ₸\n"
            f"🏷 Категория: {category}\n"
            f"📦 Остаток: {row['stock']}\n\n"
        )

    await message.answer(text, reply_markup=get_admin_menu())


@dp.message(F.text == "🗂 Категории")
async def admin_categories_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT id, name, description
            FROM categories
            ORDER BY id
            """
        )

    if not rows:
        await message.answer("Категорий пока нет.", reply_markup=get_admin_menu())
        return

    text = "🗂 Категории:\n\n"
    for row in rows:
        text += f"{row['id']}. {row['name']}\nОписание: {row['description']}\n\n"

    await message.answer(text, reply_markup=get_admin_menu())


# ---------- УПРАВЛЕНИЕ ТОВАРАМИ ----------

@dp.message(F.text == "➕ Добавить товар")
async def admin_add_product(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(AddProduct.name)
    await message.answer("Введите название товара:")


@dp.message(AddProduct.name)
async def add_product_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddProduct.description)
    await message.answer("Введите описание товара:")


@dp.message(AddProduct.description)
async def add_product_description(message: types.Message, state: FSMContext):
    await state.update_data(description=message.text.strip())
    await state.set_state(AddProduct.price)
    await message.answer("Введите цену товара в тенге:")


@dp.message(AddProduct.price)
async def add_product_price(message: types.Message, state: FSMContext):
    try:
        price = int(message.text.strip())
    except ValueError:
        await message.answer("Введите цену числом, например: 25000")
        return

    await state.update_data(price=price)
    await state.set_state(AddProduct.image_url)
    await message.answer("Введите ссылку на картинку:")


@dp.message(AddProduct.image_url)
async def add_product_image(message: types.Message, state: FSMContext):
    await state.update_data(image_url=message.text.strip())
    await state.set_state(AddProduct.category)
    await message.answer("Введите категорию точно так: Электроника / Одежда / Обувь / Аксессуары")


@dp.message(AddProduct.category)
async def add_product_category(message: types.Message, state: FSMContext):
    await state.update_data(category=message.text.strip())
    await state.set_state(AddProduct.stock)
    await message.answer("Введите количество на складе:")


@dp.message(AddProduct.stock)
async def add_product_finish(message: types.Message, state: FSMContext):
    try:
        stock = int(message.text.strip())
    except ValueError:
        await message.answer("Введите количество числом, например: 10")
        return

    data = await state.get_data()

    async with pool.acquire() as conn:
        category_id = await conn.fetchval(
            "SELECT id FROM categories WHERE name = $1",
            data["category"]
        )

        if not category_id:
            await message.answer("Такой категории нет.")
            await state.clear()
            await message.answer("Возврат в админ-меню.", reply_markup=get_admin_menu())
            return

        await conn.execute(
            """
            INSERT INTO products (name, description, price, image_url, category_id, stock)
            VALUES ($1, $2, $3, $4, $5, $6)
            """,
            data["name"],
            data["description"],
            data["price"],
            data["image_url"],
            category_id,
            stock
        )

    await state.clear()
    await message.answer("✅ Товар успешно добавлен.", reply_markup=get_admin_menu())


@dp.message(F.text == "✏️ Изменить цену товара")
async def edit_product_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(EditProduct.choose_product)
    await message.answer("Введите точное название товара:")


@dp.message(EditProduct.choose_product)
async def edit_product_choose(message: types.Message, state: FSMContext):
    await state.update_data(product=message.text.strip())
    await state.set_state(EditProduct.new_price)
    await message.answer("Введите новую цену в тенге:")


@dp.message(EditProduct.new_price)
async def edit_product_finish(message: types.Message, state: FSMContext):
    try:
        new_price = int(message.text.strip())
    except ValueError:
        await message.answer("Введите цену числом.")
        return

    data = await state.get_data()

    async with pool.acquire() as conn:
        result = await conn.execute(
            "UPDATE products SET price = $1 WHERE name = $2",
            new_price,
            data["product"]
        )

    await state.clear()

    if result.endswith("0"):
        await message.answer("Товар не найден.", reply_markup=get_admin_menu())
        return

    await message.answer("💰 Цена обновлена.", reply_markup=get_admin_menu())


@dp.message(F.text == "❌ Удалить товар")
async def admin_delete_product(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(DeleteProduct.choose_product)
    await message.answer("Введите точное название товара для удаления:")


@dp.message(DeleteProduct.choose_product)
async def delete_product(message: types.Message, state: FSMContext):
    product_name = message.text.strip()

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM products WHERE name = $1",
            product_name
        )

    await state.clear()

    if result.endswith("0"):
        await message.answer("Товар не найден.", reply_markup=get_admin_menu())
        return

    await message.answer("🗑 Товар удалён.", reply_markup=get_admin_menu())


# ---------- УПРАВЛЕНИЕ КАТЕГОРИЯМИ ----------

@dp.message(F.text == "➕ Добавить категорию")
async def admin_add_category_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(AddCategory.name)
    await message.answer("Введите название новой категории:")


@dp.message(AddCategory.name)
async def add_category_name(message: types.Message, state: FSMContext):
    await state.update_data(name=message.text.strip())
    await state.set_state(AddCategory.description)
    await message.answer("Введите описание категории:")


@dp.message(AddCategory.description)
async def add_category_description(message: types.Message, state: FSMContext):
    data = await state.get_data()

    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT COUNT(*) FROM categories WHERE name = $1",
            data["name"]
        )

        if exists > 0:
            await state.clear()
            await message.answer("Такая категория уже существует.", reply_markup=get_admin_menu())
            return

        await conn.execute(
            """
            INSERT INTO categories (name, description)
            VALUES ($1, $2)
            """,
            data["name"],
            message.text.strip()
        )

    await state.clear()
    await message.answer("✅ Категория добавлена.", reply_markup=get_admin_menu())


@dp.message(F.text == "✏️ Изменить категорию")
async def admin_edit_category_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(EditCategory.old_name)
    await message.answer("Введите текущее название категории:")


@dp.message(EditCategory.old_name)
async def edit_category_old_name(message: types.Message, state: FSMContext):
    await state.update_data(old_name=message.text.strip())
    await state.set_state(EditCategory.new_name)
    await message.answer("Введите новое название категории:")


@dp.message(EditCategory.new_name)
async def edit_category_new_name(message: types.Message, state: FSMContext):
    await state.update_data(new_name=message.text.strip())
    await state.set_state(EditCategory.new_description)
    await message.answer("Введите новое описание категории:")


@dp.message(EditCategory.new_description)
async def edit_category_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()

    async with pool.acquire() as conn:
        result = await conn.execute(
            """
            UPDATE categories
            SET name = $1, description = $2
            WHERE name = $3
            """,
            data["new_name"],
            message.text.strip(),
            data["old_name"]
        )

    await state.clear()

    if result.endswith("0"):
        await message.answer("Категория не найдена.", reply_markup=get_admin_menu())
        return

    await message.answer("✏️ Категория обновлена.", reply_markup=get_admin_menu())


@dp.message(F.text == "❌ Удалить категорию")
async def admin_delete_category_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(DeleteCategory.name)
    await message.answer("Введите название категории для удаления:")


@dp.message(DeleteCategory.name)
async def delete_category_finish(message: types.Message, state: FSMContext):
    category_name = message.text.strip()

    async with pool.acquire() as conn:
        result = await conn.execute(
            "DELETE FROM categories WHERE name = $1",
            category_name
        )

    await state.clear()

    if result.endswith("0"):
        await message.answer("Категория не найдена.", reply_markup=get_admin_menu())
        return

    await message.answer("🗑 Категория удалена.", reply_markup=get_admin_menu())


@dp.message(F.text == "🚪 Выход из админ-панели")
async def admin_logout_handler(message: types.Message):
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE admins SET telegram_id = NULL WHERE telegram_id = $1",
            message.from_user.id
        )
    await message.answer("Вы вышли из админ-панели.", reply_markup=get_main_menu())


@dp.message(F.text == "⬅️ Назад")
async def back_handler(message: types.Message):
    await message.answer("Главное меню 👇", reply_markup=get_main_menu())


@dp.message()
async def fallback(message: types.Message):
    await message.answer(
        "Пожалуйста, используйте кнопки ниже 👇",
        reply_markup=get_main_menu()
    )


async def main():
    global pool
    pool = await connect()
    await create_tables(pool)

    print("Бот запущен: магазин + админка + поиск + умный помощник")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())