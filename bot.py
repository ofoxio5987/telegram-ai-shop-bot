import asyncio
import os
import re

from dotenv import load_dotenv
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand, BotCommandScopeDefault
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

from database import connect, create_tables
from keyboards.user_kb import get_main_menu, build_categories_keyboard
from keyboards.inline_kb import (
    product_inline_keyboard,
    favorite_inline_keyboard,
    cart_inline_keyboard,
)
from keyboards.admin_kb import get_admin_menu
from keyboards.manager_kb import get_manager_menu
from states.product_states import AddProduct, EditProduct, DeleteProduct
from states.category_states import AddCategory, EditCategory, DeleteCategory
from states.assistant_states import SearchState, ManagerOrderSearchState


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

auth_stage = {}
auth_data = {}

MAIN_MENU_BUTTONS = {
    "🛒 Каталог", "🔍 Поиск", "❤️ Избранное", "🧺 Корзина", "📜 Мои заказы",
    "📦 Отследить заказ", "🎯 Рекомендации", "🤖 Умный помощник", "👤 Профиль", "ℹ️ Помощь", "⬅️ Назад"
}

ADMIN_MENU_BUTTONS = {
    "📊 Статистика", "👥 Пользователи", "🧑‍💼 Менеджеры", "📦 Товары", "🗂 Категории",
    "➕ Добавить товар", "➕ Добавить категорию", "✏️ Изменить товар", "✏️ Изменить категорию",
    "❌ Удалить товар", "❌ Удалить категорию", "🚪 Выход из админ-панели"
}

MANAGER_MENU_BUTTONS = {
    "📦 Все заказы", "🔎 Найти заказ", "📝 На регистрации", "🟢 Активные",
    "✅ Выполненные", "❌ Отменённые", "📈 Статусы заказов", "🚪 Выход из панели менеджера"
}

BLOCKED_AUTH_INPUTS = MAIN_MENU_BUTTONS | ADMIN_MENU_BUTTONS | MANAGER_MENU_BUTTONS


def clear_pending_auth(user_id: int):
    auth_stage.pop(user_id, None)
    auth_data.pop(user_id, None)


async def logout_roles(user_id: int):
    async with pool.acquire() as conn:
        await conn.execute("UPDATE admins SET telegram_id = NULL WHERE telegram_id = $1", user_id)
        await conn.execute("UPDATE managers SET telegram_id = NULL WHERE telegram_id = $1", user_id)


ORDER_STATUS_LABELS = {
    "registered": "📝 На регистрации",
    "active": "🟢 Активный",
    "completed": "✅ Выполнен",
    "cancelled": "❌ Отменён",
}


def format_status(status: str) -> str:
    return ORDER_STATUS_LABELS.get(status, status)


def build_user_order_keyboard(order_id: int, status: str):
    buttons = []
    if status in {"registered", "active"}:
        buttons.append([
            InlineKeyboardButton(text="❌ Отменить заказ", callback_data=f"usercancel_{order_id}")
        ])
    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


def build_order_manage_keyboard(order_id: int, status: str):
    buttons = []

    if status == "registered":
        buttons.append([
            InlineKeyboardButton(text="🟢 Активный", callback_data=f"orderstatus_{order_id}_active"),
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"orderstatus_{order_id}_cancelled"),
        ])
    elif status == "active":
        buttons.append([
            InlineKeyboardButton(text="📝 На регистрацию", callback_data=f"orderstatus_{order_id}_registered"),
            InlineKeyboardButton(text="✅ Выполнен", callback_data=f"orderstatus_{order_id}_completed"),
        ])
        buttons.append([
            InlineKeyboardButton(text="❌ Отменить", callback_data=f"orderstatus_{order_id}_cancelled")
        ])
    elif status in {"completed", "cancelled"}:
        buttons.append([
            InlineKeyboardButton(text="🔄 Вернуть в работу", callback_data=f"orderstatus_{order_id}_active")
        ])

    return InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None


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


async def is_manager(telegram_id: int) -> bool:
    async with pool.acquire() as conn:
        result = await conn.fetchval(
            "SELECT COUNT(*) FROM managers WHERE telegram_id = $1",
            telegram_id
        )
    return result > 0


def normalize_priority(raw_text: str) -> str:
    text = raw_text.strip().lower()

    if any(word in text for word in ["цена", "цену", "дешево", "дёшево", "дешевле", "дёшевле", "эконом", "недорого", "бюджет"]):
        return "цена"

    if any(word in text for word in ["качество", "качеству", "качественный", "лучшее", "лучший", "премиум", "надеж", "надёж", "качествен"]):
        return "качество"

    return "универсальность"


def normalize_category(raw_text: str | None) -> str | None:
    if not raw_text:
        return None

    text = raw_text.strip().lower()

    category_map = {
        "Электроника": [
            "электроника", "телефон", "смартфон", "ноутбук", "планшет",
            "гаджет", "наушник", "колонк", "техника", "электрон"
        ],
        "Одежда": [
            "одежда", "футболк", "кофта", "куртк", "рубашк",
            "брюк", "джинс", "худи", "плать", "шмот"
        ],
        "Обувь": [
            "обувь", "кроссов", "ботин", "туфл", "сандал",
            "тапк", "сапог"
        ],
        "Аксессуары": [
            "аксессуар", "часы", "сумк", "рюкзак", "кошелек",
            "кошелёк", "ремень", "браслет", "украшен"
        ],
    }

    for category, keywords in category_map.items():
        if text == category.lower():
            return category
        if any(keyword in text for keyword in keywords):
            return category

    return None


def parse_user_request(user_text: str) -> dict:
    text = user_text.lower().strip()

    category = normalize_category(text)

    budget = None
    budget_patterns = [
        r"до\s*(\d+)",
        r"бюджет\s*(\d+)",
        r"(\d+)\s*₸",
        r"(\d+)\s*тенге",
        r"(\d{4,})",
    ]
    for pattern in budget_patterns:
        match = re.search(pattern, text)
        if match:
            try:
                budget = int(match.group(1))
                break
            except ValueError:
                budget = None

    priority = normalize_priority(text)

    if "девушк" in text or "жене" in text or "женщин" in text:
        target_person = "девушке"
    elif "мужчин" in text or "парню" in text or "мужу" in text:
        target_person = "мужчине"
    elif "ребен" in text or "ребён" in text or "дет" in text:
        target_person = "ребенку"
    else:
        target_person = None

    if category is None and "подар" in text:
        if target_person == "девушке":
            category = "Аксессуары"
        elif target_person == "мужчине":
            category = "Электроника"

    return {
        "category": category,
        "budget": budget,
        "priority": priority,
        "target_person": target_person,
    }


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


async def send_favorite_card(message: types.Message, row):
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
                reply_markup=favorite_inline_keyboard(row["id"])
            )
            return
        except Exception:
            pass

    await message.answer(
        caption,
        reply_markup=favorite_inline_keyboard(row["id"])
    )


async def show_products_by_category(message: types.Message, category_name: str, emoji: str = "📦"):
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


async def process_assistant_request(message: types.Message, user_text: str) -> bool:
    parsed = parse_user_request(user_text)

    category = parsed.get("category")
    budget = parsed.get("budget")
    priority = parsed.get("priority")
    target_person = parsed.get("target_person")

    if not category:
        return False

    async with pool.acquire() as conn:
        category_exists = await conn.fetchval(
            "SELECT id FROM categories WHERE name = $1",
            category
        )

        if not category_exists:
            await message.answer(
                f"Категория '{category}' не найдена в базе.",
                reply_markup=get_main_menu()
            )
            return True

        if priority == "цена":
            order_sql = "ORDER BY p.price ASC"
        elif priority == "качество":
            order_sql = "ORDER BY p.price DESC"
        else:
            order_sql = "ORDER BY p.stock DESC, p.price ASC"

        if budget is not None:
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
        else:
            rows = await conn.fetch(
                f"""
                SELECT p.id, p.name, p.description, p.price, p.stock, p.image_url
                FROM products p
                JOIN categories c ON p.category_id = c.id
                WHERE c.name = $1
                  AND p.is_active = TRUE
                {order_sql}
                LIMIT 5
                """,
                category
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
            INSERT INTO assistant_sessions (telegram_id, category, budget_max, priority, target_person)
            VALUES ($1, $2, $3, $4, $5)
            """,
            message.from_user.id,
            category,
            budget,
            priority,
            target_person
        )

    await log_action(message.from_user.id, "assistant_rule_based")
    budget_text = f"до {budget} ₸" if budget is not None else "не указан"
    target_text = target_person if target_person else "не указан"

    if not rows:
        await message.answer(
            f"🤖 Я обработал ваш запрос:\n"
            f"• Категория: {category}\n"
            f"• Бюджет: {budget_text}\n"
            f"• Приоритет: {priority}\n"
            f"• Для кого: {target_text}\n\n"
            "📭 Подходящих товаров пока не нашлось.\n"
            "Попробуйте увеличить бюджет, изменить категорию или сформулировать запрос чуть иначе.",
            reply_markup=get_main_menu()
        )
        return True

    await message.answer(
        f"🤖 Я подобрал для вас товары по такому запросу:\n"
        f"• Категория: {category}\n"
        f"• Бюджет: {budget_text}\n"
        f"• Приоритет: {priority}\n"
        f"• Для кого: {target_text}\n\n"
        "Ниже — наиболее подходящие варианты из каталога 👇",
        reply_markup=get_main_menu()
    )

    for row in rows:
        await send_product_card(message, row)

    return True


async def build_order_text(order_row, items_rows):
    text = (
        f"📦 Заказ №{order_row['id']}\n\n"
        f"📌 Статус: {format_status(order_row['status'])}\n"
        f"💰 Сумма: {order_row['total_amount']} ₸\n"
        f"🕒 Дата оформления: {order_row['created_at']}\n\n"
        f"🧾 Состав заказа:\n"
    )

    for item in items_rows:
        item_total = item['quantity'] * item['price']
        text += f"• {item['name']} — {item['quantity']} шт. × {item['price']} ₸ = {item_total} ₸\n"

    return text


async def send_order_details(message: types.Message, order_id: int, manager_mode: bool = False):
    async with pool.acquire() as conn:
        order_row = await conn.fetchrow(
            """
            SELECT id, telegram_id, total_amount, status, created_at
            FROM orders
            WHERE id = $1
            """,
            order_id
        )

        if not order_row:
            await message.answer("Заказ не найден.")
            return

        items_rows = await conn.fetch(
            """
            SELECT p.name, oi.quantity, oi.price
            FROM order_items oi
            JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = $1
            ORDER BY oi.id
            """,
            order_id
        )

    text = await build_order_text(order_row, items_rows)

    if manager_mode:
        text += f"\n👤 Telegram ID клиента: {order_row['telegram_id']}"

    await message.answer(
        text,
        reply_markup=build_order_manage_keyboard(order_row["id"], order_row["status"]) if manager_mode else build_user_order_keyboard(order_row["id"], order_row["status"])
    )


async def show_orders_list(message: types.Message, status_filter: str | None = None, manager_mode: bool = False):
    async with pool.acquire() as conn:
        if manager_mode:
            if status_filter:
                orders = await conn.fetch(
                    """
                    SELECT id
                    FROM orders
                    WHERE status = $1
                    ORDER BY created_at DESC
                    LIMIT 15
                    """,
                    status_filter
                )
            else:
                orders = await conn.fetch(
                    """
                    SELECT id
                    FROM orders
                    ORDER BY created_at DESC
                    LIMIT 15
                    """
                )
        else:
            if status_filter:
                orders = await conn.fetch(
                    """
                    SELECT id
                    FROM orders
                    WHERE telegram_id = $1 AND status = $2
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    message.from_user.id,
                    status_filter
                )
            else:
                orders = await conn.fetch(
                    """
                    SELECT id
                    FROM orders
                    WHERE telegram_id = $1
                    ORDER BY created_at DESC
                    LIMIT 10
                    """,
                    message.from_user.id
                )

    if not orders:
        await message.answer(
            "📭 Заказы не найдены.",
            reply_markup=get_manager_menu() if manager_mode else get_main_menu()
        )
        return

    for order_row in orders:
        await send_order_details(message, order_row["id"], manager_mode=manager_mode)


@dp.message(CommandStart())
async def start(message: types.Message, state: FSMContext):
    await state.clear()
    clear_pending_auth(message.from_user.id)
    await logout_roles(message.from_user.id)
    await save_user(message)

    await message.answer(
        "🤖 Добро пожаловать в интеллектуальный магазин!\n\n"
        "Здесь вы можете искать товары, собирать корзину, оформлять заказы и отслеживать их статус прямо в Telegram 👇",
        reply_markup=get_main_menu()
    )


@dp.message(Command("admin"))
async def admin_login_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    auth_stage[user_id] = "login"
    auth_data[user_id] = {"role": "admin"}
    await message.answer("Введите логин администратора:")


@dp.message(Command("manager"))
async def manager_login_start(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    await state.clear()
    auth_stage[user_id] = "login"
    auth_data[user_id] = {"role": "manager"}
    await message.answer("Введите логин менеджера:")


@dp.message(Command("cancel"))
async def cancel_auth_or_state(message: types.Message, state: FSMContext):
    await state.clear()
    clear_pending_auth(message.from_user.id)
    await message.answer("Текущее действие отменено.", reply_markup=get_main_menu())


@dp.message(lambda message: auth_stage.get(message.from_user.id) == "login")
async def auth_login_input(message: types.Message):
    user_id = message.from_user.id
    text = (message.text or "").strip()

    if text.startswith("/") or text in BLOCKED_AUTH_INPUTS:
        await message.answer(
            "Сейчас идёт вход в систему.\n"
            "Введите логин или отправьте /cancel, чтобы отменить вход."
        )
        return

    role = auth_data.get(user_id, {}).get("role")
    auth_data[user_id]["login"] = text
    auth_stage[user_id] = "password"

    role_name = "администратора" if role == "admin" else "менеджера"
    await message.answer(f"Введите пароль {role_name}:")


@dp.message(lambda message: auth_stage.get(message.from_user.id) == "password")
async def auth_password_input(message: types.Message, state: FSMContext):
    user_id = message.from_user.id
    role = auth_data.get(user_id, {}).get("role")
    login = auth_data.get(user_id, {}).get("login")
    password = message.text.strip()

    table_name = "admins" if role == "admin" else "managers"

    async with pool.acquire() as conn:
        role_user = await conn.fetchrow(
            f"SELECT id, login, password_hash FROM {table_name} WHERE login = $1",
            login
        )

    if not role_user:
        auth_stage.pop(user_id, None)
        auth_data.pop(user_id, None)
        await state.clear()
        await message.answer("Неверный логин.", reply_markup=get_main_menu())
        return

    if password != role_user["password_hash"]:
        auth_stage.pop(user_id, None)
        auth_data.pop(user_id, None)
        await state.clear()
        await message.answer("Неверный пароль.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        await conn.execute(
            f"UPDATE {table_name} SET telegram_id = $1 WHERE login = $2",
            user_id,
            login
        )

    auth_stage.pop(user_id, None)
    auth_data.pop(user_id, None)
    await state.clear()

    if role == "admin":
        await message.answer(
            "✅ Вход в админ-панель выполнен успешно.",
            reply_markup=get_admin_menu()
        )
    else:
        await message.answer(
            "✅ Вход в панель менеджера выполнен успешно.",
            reply_markup=get_manager_menu()
        )


@dp.message(F.text == "ℹ️ Помощь")
async def help_handler(message: types.Message):
    await message.answer(
        "📌 Что умеет бот:\n\n"
        "🛒 Каталог — просмотр товаров по категориям\n"
        "🔍 Поиск — быстрый поиск по названию и описанию\n"
        "❤️ Избранное — сохранённые товары\n"
        "🧺 Корзина — подготовка заказа\n"
        "📜 Мои заказы — история и текущие статусы\n"
        "📦 Отследить заказ — быстрый доступ к заказам\n"
        "🎯 Рекомендации — подборка товаров по вашим интересам\n"
        "🤖 Умный помощник — можно просто написать, что вы хотите купить\n"
        "👤 Профиль — информация о вашем аккаунте\n\n"
        "Служебные команды:\n"
        "/admin — вход в админ-панель\n"
        "/manager — вход в панель менеджера\n"
        "/cancel — отменить текущее действие",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🤖 Умный помощник")
async def assistant_hint(message: types.Message):
    if auth_stage.get(message.from_user.id) in {"login", "password"}:
        await message.answer(
            "Сначала завершите вход или отмените его командой /cancel."
        )
        return

    await message.answer(
        "🤖 Я всегда активен и могу помочь с подбором товара.\n\n"
        "Просто напишите, что вы ищете, а я подберу подходящие варианты из каталога.\n\n"
        "Например:\n"
        "• Нужен подарок девушке до 30000\n"
        "• Хочу что-то из электроники до 50000, главное качество\n"
        "• Нужны недорогие аксессуары",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🛒 Каталог")
async def catalog_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch("SELECT name FROM categories ORDER BY name")

    if not rows:
        await message.answer(
            "🗂 Категории пока не добавлены.\n\nПопробуйте зайти позже.",
            reply_markup=get_main_menu()
        )
        return

    categories = [row["name"] for row in rows]
    await log_action(message.from_user.id, "open_catalog")

    await message.answer(
        "Выберите категорию товаров 👇",
        reply_markup=build_categories_keyboard(categories)
    )


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


@dp.callback_query(F.data.startswith("remove_fav_"))
async def remove_from_favorites(callback: CallbackQuery):
    product_id = int(callback.data.split("_")[2])

    async with pool.acquire() as conn:
        await conn.execute(
            """
            DELETE FROM favorites
            WHERE telegram_id = $1 AND product_id = $2
            """,
            callback.from_user.id,
            product_id
        )

    await callback.answer("Товар удалён из избранного")
    await callback.message.answer(
        "❌ Товар удалён из избранного.",
        reply_markup=get_main_menu()
    )


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
            "❤️ У вас пока нет избранных товаров.\n\nДобавляйте понравившиеся позиции, чтобы быстро вернуться к ним позже.",
            reply_markup=get_main_menu()
        )
        return

    await message.answer("❤️ Ваше избранное:", reply_markup=get_main_menu())

    for row in rows:
        await send_favorite_card(message, row)


@dp.message(F.text == "🧺 Корзина")
async def cart_handler(message: types.Message):
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.id, p.name, p.price, c.quantity
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.telegram_id = $1
            ORDER BY c.id DESC
            """,
            message.from_user.id
        )

    if not rows:
        await message.answer("🧺 Ваша корзина пока пуста.\n\nДобавьте товары из каталога, чтобы оформить заказ.", reply_markup=get_main_menu())
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


@dp.callback_query(F.data == "checkout_order")
async def checkout_order(callback: CallbackQuery):
    async with pool.acquire() as conn:
        cart_rows = await conn.fetch(
            """
            SELECT p.id, p.name, p.price, c.quantity
            FROM cart c
            JOIN products p ON c.product_id = p.id
            WHERE c.telegram_id = $1
            ORDER BY c.id
            """,
            callback.from_user.id
        )

        if not cart_rows:
            await callback.answer("Корзина пуста")
            return

        total_amount = 0
        for row in cart_rows:
            total_amount += row["price"] * row["quantity"]

        order_id = await conn.fetchval(
            """
            INSERT INTO orders (telegram_id, total_amount, status)
            VALUES ($1, $2, 'registered')
            RETURNING id
            """,
            callback.from_user.id,
            total_amount
        )

        for row in cart_rows:
            await conn.execute(
                """
                INSERT INTO order_items (order_id, product_id, quantity, price)
                VALUES ($1, $2, $3, $4)
                """,
                order_id,
                row["id"],
                row["quantity"],
                row["price"]
            )

            await conn.execute(
                """
                UPDATE products
                SET stock = GREATEST(stock - $1, 0)
                WHERE id = $2
                """,
                row["quantity"],
                row["id"]
            )

        await conn.execute(
            "DELETE FROM cart WHERE telegram_id = $1",
            callback.from_user.id
        )

    await log_action(callback.from_user.id, "checkout")
    await callback.answer("Заказ оформлен")
    await callback.message.answer(
        f"✅ Заказ успешно оформлен!\n\n"
        f"📦 Номер заказа: {order_id}\n"
        f"💰 Сумма: {total_amount} ₸\n"
        f"📌 Текущий статус: {format_status('registered')}\n\n"
        "⏳ Заказ ожидает обработки менеджером.\n"
        "Вы можете отслеживать его в разделе «Мои заказы».",
        reply_markup=get_main_menu()
    )


@dp.message(lambda message: message.text in {"📜 Мои заказы", "📦 Отследить заказ"})
async def my_orders_handler(message: types.Message):
    await show_orders_list(message, manager_mode=False)


@dp.callback_query(F.data.startswith("usercancel_"))
async def user_cancel_order(callback: CallbackQuery):
    order_id = int(callback.data.split("_")[1])

    async with pool.acquire() as conn:
        order_row = await conn.fetchrow(
            """
            SELECT id, status, telegram_id
            FROM orders
            WHERE id = $1 AND telegram_id = $2
            """,
            order_id,
            callback.from_user.id
        )

        if not order_row:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        if order_row["status"] not in {"registered", "active"}:
            await callback.answer("Этот заказ уже нельзя отменить", show_alert=True)
            return

        await conn.execute(
            "UPDATE orders SET status = 'cancelled' WHERE id = $1",
            order_id
        )

    await log_action(callback.from_user.id, "user_cancel_order")
    await callback.answer("Заказ отменён")
    await callback.message.answer(
        f"❌ Заказ №{order_id} отменён.\n\n"
        "Если это произошло случайно, вы можете оформить новый заказ в каталоге.",
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

        orders_count = await conn.fetchval(
            "SELECT COUNT(*) FROM orders WHERE telegram_id = $1",
            message.from_user.id
        )

    if not user:
        await message.answer(
            "👤 Профиль пока не найден.\n\nНажмите /start, чтобы бот зарегистрировал вас в системе.",
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
        f"Заказов: {orders_count}\n"
        f"Дата регистрации: {user['created_at']}",
        reply_markup=get_main_menu()
    )


@dp.message(F.text == "🔍 Поиск")
async def search_start(message: types.Message, state: FSMContext):
    await state.set_state(SearchState.waiting_for_query)
    await message.answer("🔍 Введите название товара или ключевое слово для поиска:")


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
        await message.answer("🔎 По вашему запросу ничего не найдено.\n\nПопробуйте изменить формулировку или использовать другое ключевое слово.", reply_markup=get_main_menu())
        return

    await message.answer(f"🔍 Найдено товаров: {len(rows)}", reply_markup=get_main_menu())

    for row in rows:
        await send_product_card(message, row)


@dp.message(F.text == "📦 Все заказы")
async def manager_all_orders(message: types.Message):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await show_orders_list(message, manager_mode=True)


@dp.message(F.text == "📝 На регистрации")
async def manager_registered_orders(message: types.Message):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await show_orders_list(message, status_filter="registered", manager_mode=True)


@dp.message(F.text == "🟢 Активные")
async def manager_active_orders(message: types.Message):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await show_orders_list(message, status_filter="active", manager_mode=True)


@dp.message(F.text == "✅ Выполненные")
async def manager_completed_orders(message: types.Message):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await show_orders_list(message, status_filter="completed", manager_mode=True)


@dp.message(F.text == "❌ Отменённые")
async def manager_cancelled_orders(message: types.Message):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await show_orders_list(message, status_filter="cancelled", manager_mode=True)


@dp.message(F.text == "🔎 Найти заказ")
async def manager_find_order_start(message: types.Message, state: FSMContext):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.set_state(ManagerOrderSearchState.waiting_for_order_id)
    await message.answer("Введите трекинг-номер заказа (его ID):", reply_markup=get_manager_menu())


@dp.message(ManagerOrderSearchState.waiting_for_order_id)
async def manager_find_order_finish(message: types.Message, state: FSMContext):
    if not await is_manager(message.from_user.id):
        await state.clear()
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    try:
        order_id = int(message.text.strip())
    except ValueError:
        await message.answer("Введите номер заказа числом, например: 12", reply_markup=get_manager_menu())
        return

    await state.clear()
    await send_order_details(message, order_id, manager_mode=True)


@dp.message(F.text == "📈 Статусы заказов")
async def manager_orders_stats(message: types.Message):
    if not await is_manager(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT status, COUNT(*) AS cnt
            FROM orders
            GROUP BY status
            ORDER BY cnt DESC
            """
        )

    if not rows:
        await message.answer("Статистика по заказам пока недоступна.", reply_markup=get_manager_menu())
        return

    text = "📈 Статусы заказов:\n\n"
    total = 0
    for row in rows:
        total += row["cnt"]
        text += f"{format_status(row['status'])}: {row['cnt']}\n"

    text += f"\nВсего заказов: {total}"
    await message.answer(text, reply_markup=get_manager_menu())


@dp.callback_query(F.data.startswith("orderstatus_"))
async def manager_change_order_status(callback: CallbackQuery):
    if not await is_manager(callback.from_user.id):
        await callback.answer("Доступ запрещён", show_alert=True)
        return

    _, order_id_str, new_status = callback.data.split("_", 2)
    order_id = int(order_id_str)

    async with pool.acquire() as conn:
        order_row = await conn.fetchrow(
            "SELECT id, status, telegram_id FROM orders WHERE id = $1",
            order_id
        )

        if not order_row:
            await callback.answer("Заказ не найден", show_alert=True)
            return

        current_status = order_row["status"]

        allowed_transitions = {
            "registered": {"active", "cancelled"},
            "active": {"registered", "completed", "cancelled"},
            "completed": {"active"},
            "cancelled": {"active"},
        }

        if new_status not in allowed_transitions.get(current_status, set()):
            await callback.answer("Недопустимый переход статуса", show_alert=True)
            return

        await conn.execute(
            "UPDATE orders SET status = $1 WHERE id = $2",
            new_status,
            order_id
        )

    await callback.answer(f"Статус обновлён: {format_status(new_status)}")
    await callback.message.answer(
        f"✅ Статус заказа №{order_id} обновлён.\n\n"
        f"📌 Новый статус: {format_status(new_status)}",
        reply_markup=get_manager_menu()
    )

    await log_action(callback.from_user.id, f"manager_order_status_{new_status}")

    try:
        await bot.send_message(
            order_row["telegram_id"],
            f"📦 Обновление по заказу №{order_id}\n\n"
            f"📌 Новый статус: {format_status(new_status)}\n\n"
            "Проверить детали заказа можно в разделе «Мои заказы»."
        )
    except Exception:
        pass


@dp.message(F.text == "🚪 Выход из панели менеджера")
async def manager_logout_handler(message: types.Message, state: FSMContext):
    await state.clear()
    clear_pending_auth(message.from_user.id)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE managers SET telegram_id = NULL WHERE telegram_id = $1",
            message.from_user.id
        )

    await message.answer("Вы вышли из панели менеджера.", reply_markup=get_main_menu())


@dp.message(F.text == "📊 Статистика")
async def admin_stats_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    try:
        async with pool.acquire() as conn:
            users_count = await conn.fetchval("SELECT COUNT(*) FROM users")
            managers_count = await conn.fetchval("SELECT COUNT(*) FROM managers")
            products_count = await conn.fetchval("SELECT COUNT(*) FROM products")
            active_products_count = await conn.fetchval("SELECT COUNT(*) FROM products WHERE is_active = TRUE")
            categories_count = await conn.fetchval("SELECT COUNT(*) FROM categories")
            favorites_count = await conn.fetchval("SELECT COUNT(*) FROM favorites")
            cart_count = await conn.fetchval("SELECT COUNT(*) FROM cart")
            actions_count = await conn.fetchval("SELECT COUNT(*) FROM user_actions")
            assistant_count = await conn.fetchval("SELECT COUNT(*) FROM assistant_sessions")

            orders_count = await conn.fetchval("SELECT COUNT(*) FROM orders")
            registered_count = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'registered'")
            active_count = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'active'")
            completed_count = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'completed'")
            cancelled_count = await conn.fetchval("SELECT COUNT(*) FROM orders WHERE status = 'cancelled'")

            revenue_completed = await conn.fetchval(
                "SELECT COALESCE(SUM(total_amount), 0) FROM orders WHERE status = 'completed'"
            )
            revenue_all = await conn.fetchval(
                "SELECT COALESCE(SUM(total_amount), 0) FROM orders"
            )
            avg_check_completed = await conn.fetchval(
                "SELECT COALESCE(ROUND(AVG(total_amount)), 0) FROM orders WHERE status = 'completed'"
            )
            avg_check_all = await conn.fetchval(
                "SELECT COALESCE(ROUND(AVG(total_amount)), 0) FROM orders"
            )

            ordering_users_count = await conn.fetchval(
                "SELECT COUNT(DISTINCT telegram_id) FROM orders"
            )

            top_buyer = await conn.fetchrow(
                """
                SELECT telegram_id, COUNT(*) AS orders_cnt, COALESCE(SUM(total_amount), 0) AS total_sum
                FROM orders
                GROUP BY telegram_id
                ORDER BY total_sum DESC, orders_cnt DESC
                LIMIT 1
                """
            )

            top_products_qty = await conn.fetch(
                """
                SELECT p.name, SUM(oi.quantity) AS total_qty
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                JOIN orders o ON oi.order_id = o.id
                GROUP BY p.name
                ORDER BY total_qty DESC, p.name ASC
                LIMIT 5
                """
            )

            top_products_revenue = await conn.fetch(
                """
                SELECT p.name, SUM(oi.quantity * oi.price) AS revenue
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                JOIN orders o ON oi.order_id = o.id
                GROUP BY p.name
                ORDER BY revenue DESC, p.name ASC
                LIMIT 5
                """
            )

            top_categories = await conn.fetch(
                """
                SELECT c.name AS category_name, SUM(oi.quantity) AS total_qty
                FROM order_items oi
                JOIN products p ON oi.product_id = p.id
                JOIN categories c ON p.category_id = c.id
                JOIN orders o ON oi.order_id = o.id
                GROUP BY c.name
                ORDER BY total_qty DESC, c.name ASC
                LIMIT 5
                """
            )

            order_days = await conn.fetch(
                """
                SELECT TO_CHAR(created_at::date, 'YYYY-MM-DD') AS day, COUNT(*) AS cnt, COALESCE(SUM(total_amount), 0) AS total_sum
                FROM orders
                WHERE created_at >= CURRENT_DATE - INTERVAL '6 days'
                GROUP BY created_at::date
                ORDER BY created_at::date ASC
                """
            )

        def pct(part: int, total: int) -> float:
            return round((part / total) * 100, 1) if total else 0.0

        completion_rate = pct(completed_count, orders_count)
        cancellation_rate = pct(cancelled_count, orders_count)
        active_share = pct(active_count, orders_count)
        registered_share = pct(registered_count, orders_count)

        avg_orders_per_user = round((orders_count / ordering_users_count), 2) if ordering_users_count else 0.0

        text = (
            "📊 Продвинутая статистика магазина\n\n"
            "🏪 Общая информация:\n"
            f"• Пользователей: {users_count}\n"
            f"• Менеджеров: {managers_count}\n"
            f"• Категорий: {categories_count}\n"
            f"• Товаров всего: {products_count}\n"
            f"• Активных товаров: {active_products_count}\n"
            f"• Добавлений в избранное: {favorites_count}\n"
            f"• Товаров в корзинах: {cart_count}\n"
            f"• Действий пользователей: {actions_count}\n"
            f"• Использований помощника: {assistant_count}\n\n"

            "🧾 Аналитика заказов:\n"
            f"• Всего заказов: {orders_count}\n"
            f"• На регистрации: {registered_count} ({registered_share}%)\n"
            f"• Активных: {active_count} ({active_share}%)\n"
            f"• Выполненных: {completed_count} ({completion_rate}%)\n"
            f"• Отменённых: {cancelled_count} ({cancellation_rate}%)\n\n"

            "💵 Финансовая аналитика:\n"
            f"• Сумма всех заказов: {revenue_all} ₸\n"
            f"• Выручка по выполненным заказам: {revenue_completed} ₸\n"
            f"• Средний чек по всем заказам: {avg_check_all} ₸\n"
            f"• Средний чек по выполненным заказам: {avg_check_completed} ₸\n\n"

            "👤 Пользовательская аналитика:\n"
            f"• Пользователей с заказами: {ordering_users_count}\n"
            f"• Среднее число заказов на пользователя: {avg_orders_per_user}\n"
        )

        if top_buyer:
            text += (
                f"• Топ-покупатель: {top_buyer['telegram_id']} "
                f"(заказов: {top_buyer['orders_cnt']}, сумма: {top_buyer['total_sum']} ₸)\n\n"
            )
        else:
            text += "• Топ-покупатель: пока нет данных\n\n"

        text += "🏆 Топ-5 товаров по количеству продаж:\n"
        if top_products_qty:
            for i, item in enumerate(top_products_qty, start=1):
                text += f"{i}. {item['name']} — {item['total_qty']} шт.\n"
        else:
            text += "Пока нет данных\n"

        text += "\n💰 Топ-5 товаров по выручке:\n"
        if top_products_revenue:
            for i, item in enumerate(top_products_revenue, start=1):
                text += f"{i}. {item['name']} — {item['revenue']} ₸\n"
        else:
            text += "Пока нет данных\n"

        text += "\n🗂 Топ-5 категорий по заказам:\n"
        if top_categories:
            for i, item in enumerate(top_categories, start=1):
                text += f"{i}. {item['category_name']} — {item['total_qty']} шт.\n"
        else:
            text += "Пока нет данных\n"

        text += "\n📅 Заказы за последние 7 дней:\n"
        if order_days:
            for item in order_days:
                text += f"• {item['day']} — {item['cnt']} заказ(ов), сумма: {item['total_sum']} ₸\n"
        else:
            text += "Пока нет данных\n"

        await message.answer(text, reply_markup=get_admin_menu())

    except Exception as e:
        await message.answer(
            f"Ошибка статистики: {e}",
            reply_markup=get_admin_menu()
        )


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


@dp.message(F.text == "🧑‍💼 Менеджеры")
async def admin_managers_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT login, telegram_id, created_at
            FROM managers
            ORDER BY created_at DESC
            """
        )

    if not rows:
        await message.answer("Менеджеров пока нет.", reply_markup=get_admin_menu())
        return

    text = "🧑‍💼 Менеджеры:\n\n"
    for row in rows:
        tg = row["telegram_id"] if row["telegram_id"] else "не привязан"
        text += f"Логин: {row['login']}\nTelegram ID: {tg}\nДата: {row['created_at']}\n\n"

    text += "Вход для менеджеров выполняется через команду /manager"
    await message.answer(text, reply_markup=get_admin_menu())


@dp.message(F.text == "📦 Товары")
async def admin_products_handler(message: types.Message):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    async with pool.acquire() as conn:
        rows = await conn.fetch(
            """
            SELECT p.name, p.price, p.stock, p.description, p.image_url, c.name AS category_name
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
            f"📦 Остаток: {row['stock']}\n"
            f"📝 {row['description']}\n\n"
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
async def admin_add_product(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.clear()
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


@dp.message(F.text == "✏️ Изменить товар")
async def edit_product_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.clear()
    await state.set_state(EditProduct.choose_product)
    await message.answer("Введите точное название товара, который хотите изменить:")


@dp.message(EditProduct.choose_product)
async def edit_product_choose(message: types.Message, state: FSMContext):
    product_name = message.text.strip()

    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT COUNT(*) FROM products WHERE name = $1",
            product_name
        )

    if exists == 0:
        await state.clear()
        await message.answer("Товар не найден.", reply_markup=get_admin_menu())
        return

    await state.update_data(product=product_name)
    await state.set_state(EditProduct.choose_field)
    await message.answer(
        "Что хотите изменить?\n"
        "Напишите одно слово:\n"
        "название / описание / цена / картинка / остаток / категория"
    )


@dp.message(EditProduct.choose_field)
async def edit_product_field(message: types.Message, state: FSMContext):
    field = message.text.strip().lower()

    allowed = ["название", "описание", "цена", "картинка", "остаток", "категория"]
    if field not in allowed:
        await message.answer("Введите: название / описание / цена / картинка / остаток / категория")
        return

    await state.update_data(field=field)
    await state.set_state(EditProduct.new_value)
    await message.answer("Введите новое значение:")


@dp.message(EditProduct.new_value)
async def edit_product_finish(message: types.Message, state: FSMContext):
    data = await state.get_data()
    product_name = data["product"]
    field = data["field"]
    new_value = message.text.strip()

    async with pool.acquire() as conn:
        if field == "название":
            result = await conn.execute(
                "UPDATE products SET name = $1 WHERE name = $2",
                new_value,
                product_name
            )
        elif field == "описание":
            result = await conn.execute(
                "UPDATE products SET description = $1 WHERE name = $2",
                new_value,
                product_name
            )
        elif field == "цена":
            try:
                price = int(new_value)
            except ValueError:
                await message.answer("Цена должна быть числом.")
                return

            result = await conn.execute(
                "UPDATE products SET price = $1 WHERE name = $2",
                price,
                product_name
            )
        elif field == "картинка":
            result = await conn.execute(
                "UPDATE products SET image_url = $1 WHERE name = $2",
                new_value,
                product_name
            )
        elif field == "остаток":
            try:
                stock = int(new_value)
            except ValueError:
                await message.answer("Остаток должен быть числом.")
                return

            result = await conn.execute(
                "UPDATE products SET stock = $1 WHERE name = $2",
                stock,
                product_name
            )
        else:
            category_id = await conn.fetchval(
                "SELECT id FROM categories WHERE name = $1",
                new_value
            )

            if not category_id:
                await message.answer("Такой категории нет.")
                return

            result = await conn.execute(
                "UPDATE products SET category_id = $1 WHERE name = $2",
                category_id,
                product_name
            )

    await state.clear()

    if result.endswith("0"):
        await message.answer("Изменение не выполнено.", reply_markup=get_admin_menu())
        return

    await message.answer("✏️ Товар успешно обновлён.", reply_markup=get_admin_menu())


@dp.message(F.text == "❌ Удалить товар")
async def admin_delete_product(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.clear()
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


@dp.message(F.text == "➕ Добавить категорию")
async def admin_add_category_start(message: types.Message, state: FSMContext):
    if not await is_admin(message.from_user.id):
        await message.answer("Доступ запрещён.", reply_markup=get_main_menu())
        return

    await state.clear()
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

    await state.clear()
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

    await state.clear()
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


@dp.message(F.text == "🚪 Выход из панели менеджера")
async def manager_logout_handler(message: types.Message, state: FSMContext):
    await state.clear()
    clear_pending_auth(message.from_user.id)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE managers SET telegram_id = NULL WHERE telegram_id = $1",
            message.from_user.id
        )

    await message.answer("Вы вышли из панели менеджера.", reply_markup=get_main_menu())


@dp.message(F.text == "🚪 Выход из админ-панели")
async def admin_logout_handler(message: types.Message, state: FSMContext):
    await state.clear()
    clear_pending_auth(message.from_user.id)

    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE admins SET telegram_id = NULL WHERE telegram_id = $1",
            message.from_user.id
        )
    await message.answer("Вы вышли из админ-панели.", reply_markup=get_main_menu())


@dp.message(F.text == "⬅️ Назад")
async def back_handler(message: types.Message, state: FSMContext):
    await state.clear()

    if await is_admin(message.from_user.id):
        await message.answer("Админ-меню 👇", reply_markup=get_admin_menu())
        return

    if await is_manager(message.from_user.id):
        await message.answer("Панель менеджера 👇", reply_markup=get_manager_menu())
        return

    await message.answer("Главное меню 👇", reply_markup=get_main_menu())


@dp.message()
async def category_or_assistant_router(message: types.Message, state: FSMContext):
    current_state = await state.get_state()
    if current_state is not None:
        return

    if auth_stage.get(message.from_user.id) in {"login", "password"}:
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("Пожалуйста, используйте кнопки ниже 👇", reply_markup=get_main_menu())
        return

    if await is_admin(message.from_user.id):
        await message.answer("🛠 Вы сейчас в админ-панели. Используйте кнопки ниже 👇", reply_markup=get_admin_menu())
        return

    if await is_manager(message.from_user.id):
        await message.answer("📦 Вы сейчас в панели менеджера. Используйте кнопки ниже 👇", reply_markup=get_manager_menu())
        return

    async with pool.acquire() as conn:
        exists = await conn.fetchval(
            "SELECT COUNT(*) FROM categories WHERE name = $1",
            text
        )

    if exists > 0:
        await log_action(message.from_user.id, "open_category")
        await show_products_by_category(message, text, "📦")
        return

    handled = await process_assistant_request(message, text)
    if handled:
        return

    await message.answer(
        "🤔 Я не смог точно понять запрос.\n\n"
        "Попробуйте написать, например:\n"
        "• Нужна электроника до 50000\n"
        "• Хочу недорогие аксессуары\n"
        "• Покажи обувь",
        reply_markup=get_main_menu()
    )


async def setup_bot_commands():
    commands = [
        BotCommand(command="start", description="Запустить бота"),
        BotCommand(command="admin", description="Вход в админ-панель"),
        BotCommand(command="manager", description="Вход в панель менеджера"),
        BotCommand(command="cancel", description="Отменить текущее действие"),
    ]
    await bot.set_my_commands(commands, scope=BotCommandScopeDefault())


async def main():
    global pool
    pool = await connect()
    await create_tables(pool)

    await setup_bot_commands()
    print("Бот запущен: магазин + новая логика заказов + менеджер")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
