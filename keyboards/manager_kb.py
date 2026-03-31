from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_manager_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 Все заказы"), KeyboardButton(text="🆕 Новые заказы")],
            [KeyboardButton(text="🛠 В обработке"), KeyboardButton(text="✅ Завершённые")],
            [KeyboardButton(text="❌ Отменённые"), KeyboardButton(text="📈 Статусы заказов")],
            [KeyboardButton(text="🚪 Выход из панели менеджера")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Панель менеджера"
    )
