from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Каталог"), KeyboardButton(text="🔍 Поиск")],
            [KeyboardButton(text="❤️ Избранное"), KeyboardButton(text="🧺 Корзина")],
            [KeyboardButton(text="📜 Мои заказы"), KeyboardButton(text="🎯 Рекомендации")],
            [KeyboardButton(text="🤖 Умный помощник"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="ℹ️ Помощь"), KeyboardButton(text="🔐 Админ-вход")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие"
    )


def get_categories_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Электроника"), KeyboardButton(text="👕 Одежда")],
            [KeyboardButton(text="👟 Обувь"), KeyboardButton(text="🎒 Аксессуары")],
            [KeyboardButton(text="⬅️ Назад")]
        ],
        resize_keyboard=True
    )