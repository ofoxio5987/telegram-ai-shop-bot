import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN не найден в файле .env")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start(message: types.Message):
    await message.answer(
        "🤖 Интеллектуальный Telegram-бот для персонализации покупательского опыта\n\n"
        "Доступные команды:\n"
        "/catalog — каталог товаров\n"
        "/recommend — персональные рекомендации\n"
        "/profile — профиль пользователя\n"
        "/help — помощь"
    )


@dp.message(Command("help"))
async def help_command(message: types.Message):
    await message.answer(
        "📌 Список команд:\n\n"
        "/start — запуск бота\n"
        "/catalog — открыть каталог\n"
        "/recommend — получить рекомендации\n"
        "/profile — посмотреть профиль\n"
        "/help — помощь"
    )


@dp.message(Command("catalog"))
async def catalog(message: types.Message):
    await message.answer(
        "🛒 Каталог временно работает без базы данных.\n\n"
        "Примеры товаров:\n"
        "1. Смартфон X1 — 120000₽\n"
        "2. Наушники ProSound — 25000₽\n"
        "3. Умные часы FitTime — 30000₽\n"
        "4. Рюкзак UrbanBag — 15000₽\n"
        "5. Кроссовки RunFast — 28000₽"
    )


@dp.message(Command("recommend"))
async def recommend(message: types.Message):
    await message.answer(
        "🤖 Персональные рекомендации:\n\n"
        "На основе популярных предпочтений могу предложить:\n"
        "• Смартфон X1\n"
        "• Наушники ProSound\n"
        "• Умные часы FitTime\n\n"
        "Когда подключим базу данных, рекомендации станут персональными."
    )


@dp.message(Command("profile"))
async def profile(message: types.Message):
    user = message.from_user

    await message.answer(
        f"👤 Профиль пользователя\n\n"
        f"Имя: {user.first_name}\n"
        f"Telegram ID: {user.id}\n"
        f"Username: @{user.username if user.username else 'не указан'}\n\n"
        f"Позже здесь будут:\n"
        f"• история покупок\n"
        f"• интересы\n"
        f"• бюджет\n"
        f"• персональные предложения"
    )


@dp.message()
async def echo_unknown(message: types.Message):
    await message.answer(
        "Я пока не знаю эту команду.\n"
        "Используй /help чтобы посмотреть доступные команды."
    )


async def main():
    print("Бот запущен без базы данных")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())