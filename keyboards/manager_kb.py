from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_manager_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Все заказы"), KeyboardButton(text="🔎 Найти заказ")],
            [KeyboardButton(text="📝 На регистрации"), KeyboardButton(text="🟢 Активные")],
            [KeyboardButton(text="✅ Выполненные"), KeyboardButton(text="❌ Отменённые")],
            [KeyboardButton(text="📈 Статусы заказов")],
            [KeyboardButton(text="🚪 Выход из панели менеджера")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Панель менеджера"
    )
