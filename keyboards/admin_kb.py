from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_admin_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📊 Статистика"), KeyboardButton(text="👥 Пользователи")],
            [KeyboardButton(text="📦 Товары"), KeyboardButton(text="🗂 Категории")],
            [KeyboardButton(text="➕ Добавить товар")],
            [KeyboardButton(text="✏️ Изменить цену товара")],
            [KeyboardButton(text="❌ Удалить товар")],
            [KeyboardButton(text="🚪 Выход из админ-панели")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Админ-меню"
    )