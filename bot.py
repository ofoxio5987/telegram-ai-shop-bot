import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from dotenv import load_dotenv
import os

from database import connect, create_tables

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


@dp.message(CommandStart())
async def start(message: types.Message):
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

    await message.answer(
        "🤖 Интеллектуальный Telegram-бот для персонализации покупательского опыта\n\n"
        "Вы успешно зарегистрированы в системе.\n\n"
        "Доступные команды:\n"
        "/catalog — каталог товаров\n"
        "/recommend — рекомендации\n"
        "/profile — профиль\n"
        "/help — помощь"
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📌 Доступные команды:\n\n"
        "/start — запуск бота\n"
        "/catalog — показать каталог\n"
        "/recommend — получить рекомендации\n"
        "/profile — посмотреть профиль\n"
        "/help — помощь"
    )


@dp.message(Command("catalog"))
async def catalog(message: types.Message):
    async with pool.acquire() as conn:
        products = await conn.fetch(
            "SELECT name, price, category FROM products ORDER BY id LIMIT 10;"
        )

    if not products:
        await message.answer("Каталог пуст.")
        return

    text = "🛒 Каталог товаров:\n\n"

    for product in products:
        text += (
            f"📦 {product['name']}\n"
            f"💰 Цена: {product['price']}₽\n"
            f"🏷 Категория: {product['category']}\n\n"
        )

    await message.answer(text)


@dp.message(Command("recommend"))
async def recommend(message: types.Message):
    async with pool.acquire() as conn:
        products = await conn.fetch(
            "SELECT name, price FROM products ORDER BY price ASC LIMIT 3;"
        )

    if not products:
        await message.answer("Пока нет товаров для рекомендаций.")
        return

    text = "🤖 Персональные рекомендации:\n\n"

    for product in products:
        text += f"• {product['name']} — {product['price']}₽\n"

    text += "\nСейчас это базовые рекомендации. Позже мы сделаем умную персонализацию."

    await message.answer(text)


@dp.message(Command("profile"))
async def profile(message: types.Message):
    async with pool.acquire() as conn:
        user = await conn.fetchrow(
            """
            SELECT telegram_id, first_name, username, created_at
            FROM users
            WHERE telegram_id = $1;
            """,
            message.from_user.id
        )

    if not user:
        await message.answer("Профиль не найден. Нажмите /start")
        return

    username = f"@{user['username']}" if user["username"] else "не указан"

    await message.answer(
        f"👤 Профиль пользователя\n\n"
        f"Имя: {user['first_name']}\n"
        f"Telegram ID: {user['telegram_id']}\n"
        f"Username: {username}\n"
        f"Дата регистрации: {user['created_at']}\n"
    )


@dp.message()
async def fallback(message: types.Message):
    await message.answer("Неизвестная команда. Используй /help")


async def main():
    global pool

    pool = await connect()
    await create_tables(pool)

    print("Бот запущен с PostgreSQL")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())