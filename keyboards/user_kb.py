from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def get_main_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 Каталог"), KeyboardButton(text="🔍 Поиск")],
            [KeyboardButton(text="❤️ Избранное"), KeyboardButton(text="🧺 Корзина")],
            [KeyboardButton(text="📜 Мои заказы"), KeyboardButton(text="🎯 Рекомендации")],
            [KeyboardButton(text="🤖 Умный помощник"), KeyboardButton(text="👤 Профиль")],
            [KeyboardButton(text="ℹ️ Помощь")]
        ],
        resize_keyboard=True
    )


def build_categories_keyboard(categories):
    keyboard = []

    row = []
    for cat in categories:
        row.append(KeyboardButton(text=cat))

        if len(row) == 2:
            keyboard.append(row)
            row = []

    if row:
        keyboard.append(row)

    keyboard.append([KeyboardButton(text="⬅️ Назад")])

    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True
    )
