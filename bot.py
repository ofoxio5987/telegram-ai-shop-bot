import asyncio
import os

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import CommandStart
from aiogram.types import CallbackQuery

from database import connect, create_tables
from keyboards.user_kb import get_main_menu, get_categories_menu
from keyboards.inline_kb import product_inline_keyboard, cart_inline_keyboard

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
                f"💰 Цена: {row['price']}₽\n"
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
            f"💰 {row['price']}₽\n\n"
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
            f"💰 {row['price']}₽ x {row['quantity']} = {item_total}₽\n\n"
        )

    text += f"Итого: {total}₽"

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
            f"💰 {row['price']}₽\n\n"
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
    budget = user["budget"] if user["budget"] else "не задан"
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
    await message.answer(
        "Поиск добавим следующим шагом.",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🤖 Умный помощник")
async def assistant_handler(message: types.Message):
    await message.answer(
        "Умный помощник будет следующим этапом.\n"
        "Скоро он будет подбирать товары по бюджету и цели покупки.",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🔐 Админ-вход")
async def admin_login_handler(message: types.Message):
    await message.answer(
        "Админ-панель будет следующим этапом.\n"
        "Скоро добавим вход по логину и паролю, статистику и управление товарами.",
        reply_markup=get_main_menu()
    )


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

    print("Бот запущен: магазин с картинками, избранным и корзиной")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())