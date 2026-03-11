import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery

from database import connect, create_tables
from keyboards.user_kb import get_main_menu, get_categories_menu
from keyboards.inline_kb import product_inline_keyboard, cart_inline_keyboard
from keyboards.admin_kb import get_admin_menu

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден")

if not DATABASE_URL:
    raise ValueError("DATABASE_URL не найден")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()
pool = None

# Простая и надежная авторизация без FSM
admin_auth_stage = {}   # user_id -> "login" / "password"
admin_auth_data = {}    # user_id -> {"login": "admin"}


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
            caption = (
                f"📦 {row['name']}\n"
                f"📝 {row['description']}\n"
                f"💰 Цена: {row['price']} ₸\n"
                f"📦 В наличии: {row['stock']}"
            )

            image_url = row["image_url"]

            if image_url and image_url.strip():
                try:
                    await message.answer_photo(
                        photo=image_url,
                        caption=caption,
                        reply_markup=product_inline_keyboard(row["id"])
                    )
                except Exception:
                    await message.answer(
                        caption,
                        reply_markup=product_inline_keyboard(row["id"])
                    )
            else:
                await message.answer(
                    caption,
                    reply_markup=product_inline_keyboard(row["id"])
                )

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


# ---------- НАДЕЖНЫЙ ВХОД В АДМИНКУ ----------

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

    # Прямая и надежная проверка
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
            SELECT p.name, p.description, p.price
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

    text = "❤️ Ваше избранное:\n\n"
    for row in rows:
        text += (
            f"📦 {row['name']}\n"
            f"📝 {row['description']}\n"
            f"💰 {row['price']} ₸\n\n"
        )

    await message.answer(text, reply_markup=get_main_menu())


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


@dp.message(F.text == "🔍 Поиск")
async def search_handler(message: types.Message):
    await message.answer("Поиск добавим следующим шагом.", reply_markup=get_main_menu())


@dp.message(F.text == "🤖 Умный помощник")
async def assistant_handler(message: types.Message):
    await message.answer(
        "Умный помощник будет следующим этапом.\n"
        "Скоро он будет подбирать товары по бюджету и цели покупки.",
        reply_markup=get_main_menu()
    )


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

    text = (
        "📊 Статистика магазина\n\n"
        f"👥 Пользователей: {users_count}\n"
        f"📦 Товаров: {products_count}\n"
        f"🗂 Категорий: {categories_count}\n"
        f"❤️ Добавлений в избранное: {favorites_count}\n"
        f"🧺 Товаров в корзинах: {cart_count}\n"
        f"📈 Действий пользователей: {actions_count}"
    )

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


@dp.message(F.text == "➕ Добавить товар")
async def admin_add_product_placeholder(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return
    await message.answer("Добавление товара подключим следующим шагом.", reply_markup=get_admin_menu())


@dp.message(F.text == "✏️ Изменить цену товара")
async def admin_edit_product_placeholder(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return
    await message.answer("Изменение цены подключим следующим шагом.", reply_markup=get_admin_menu())


@dp.message(F.text == "❌ Удалить товар")
async def admin_delete_product_placeholder(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return
    await message.answer("Удаление товара подключим следующим шагом.", reply_markup=get_admin_menu())


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

    print("Бот запущен: магазин + надежный вход в админку")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())