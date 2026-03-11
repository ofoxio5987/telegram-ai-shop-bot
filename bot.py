import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart

from database import connect, create_tables
from keyboards.user_kb import get_main_menu, get_categories_menu

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


@dp.message(CommandStart())
async def start(message: types.Message):
    await save_user(message)

    await message.answer(
        "🤖 Добро пожаловать в интеллектуальный магазин!\n\n"
        "Я помогу подобрать товары, сохранить избранное, оформить заказ и получить персональные рекомендации.",
        reply_markup=get_main_menu()
    )


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
        "🔐 Админ-вход — вход в админ-панель"
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
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.description, p.price
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.name = 'Электроника' AND p.is_active = TRUE
            ORDER BY p.id
            """
        )

    await log_action(message.from_user.id, "open_category")

    if not rows:
        await message.answer("В этой категории пока нет товаров.", reply_markup=get_main_menu())
        return

    text = "📱 Электроника:\n\n"
    for row in rows:
        text += f"📦 {row['name']}\n{row['description']}\n💰 {row['price']}₽\n\n"

    await message.answer(text, reply_markup=get_main_menu())


@dp.message(F.text == "👕 Одежда")
async def clothes_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.description, p.price
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.name = 'Одежда' AND p.is_active = TRUE
            ORDER BY p.id
            """
        )

    if not rows:
        await message.answer("В этой категории пока нет товаров.", reply_markup=get_main_menu())
        return

    text = "👕 Одежда:\n\n"
    for row in rows:
        text += f"📦 {row['name']}\n{row['description']}\n💰 {row['price']}₽\n\n"

    await message.answer(text, reply_markup=get_main_menu())


@dp.message(F.text == "👟 Обувь")
async def shoes_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.description, p.price
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.name = 'Обувь' AND p.is_active = TRUE
            ORDER BY p.id
            """
        )

    if not rows:
        await message.answer("В этой категории пока нет товаров.", reply_markup=get_main_menu())
        return

    text = "👟 Обувь:\n\n"
    for row in rows:
        text += f"📦 {row['name']}\n{row['description']}\n💰 {row['price']}₽\n\n"

    await message.answer(text, reply_markup=get_main_menu())


@dp.message(F.text == "🎒 Аксессуары")
async def accessories_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.description, p.price
            FROM products p
            JOIN categories c ON p.category_id = c.id
            WHERE c.name = 'Аксессуары' AND p.is_active = TRUE
            ORDER BY p.id
            """
        )

    if not rows:
        await message.answer("В этой категории пока нет товаров.", reply_markup=get_main_menu())
        return

    text = "🎒 Аксессуары:\n\n"
    for row in rows:
        text += f"📦 {row['name']}\n{row['description']}\n💰 {row['price']}₽\n\n"

    await message.answer(text, reply_markup=get_main_menu())


@dp.message(F.text == "⬅️ Назад")
async def back_handler(message: types.Message):
    await message.answer("Главное меню 👇", reply_markup=get_main_menu())


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
        text += f"📦 {row['name']}\n{row['description']}\n💰 {row['price']}₽\n\n"

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

    if not user:
        await message.answer("Профиль не найден. Нажмите /start", reply_markup=get_main_menu())
        return

    username = f"@{user['username']}" if user["username"] else "не указан"
    budget = user["budget"] if user["budget"] else "не задан"
    favorite_category = user["favorite_category"] if user["favorite_category"] else "не определена"

    await message.answer(
        f"👤 Ваш профиль\n\n"
        f"Имя: {user['first_name']}\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"Username: {username}\n"
        f"Бюджет: {budget}\n"
        f"Любимая категория: {favorite_category}\n"
        f"Дата регистрации: {user['created_at']}",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "❤️ Избранное")
async def favorites_handler(message: types.Message):
    await message.answer("Раздел избранного будет следующим шагом.", reply_markup=get_main_menu())


@dp.message(F.text == "🧺 Корзина")
async def cart_handler(message: types.Message):
    await message.answer("Раздел корзины будет следующим шагом.", reply_markup=get_main_menu())


@dp.message(F.text == "🔍 Поиск")
async def search_handler(message: types.Message):
    await message.answer("Поиск товаров добавим следующим шагом.", reply_markup=get_main_menu())


@dp.message(F.text == "🤖 Умный помощник")
async def assistant_handler(message: types.Message):
    await message.answer(
        "Умный помощник скоро появится.\n"
        "Он будет подбирать товары по категории, бюджету и цели покупки.",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🔐 Админ-вход")
async def admin_login_handler(message: types.Message):
    await message.answer(
        "Админ-панель будет следующим этапом.\n"
        "Мы добавим вход по логину и паролю, статистику и управление товарами.",
        reply_markup=get_main_menu()
    )


@dp.message()
async def fallback(message: types.Message):
    await message.answer("Пожалуйста, используйте кнопки ниже 👇", reply_markup=get_main_menu())


async def main():
    global pool
    pool = await connect()
    await create_tables(pool)

    print("Бот запущен: версия каркаса дипломного проекта")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())