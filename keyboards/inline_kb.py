from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def product_inline_keyboard(product_id: int):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="❤️ В избранное", callback_data=f"fav_{product_id}"),
                InlineKeyboardButton(text="🧺 В корзину", callback_data=f"cart_{product_id}")
            ]
        ]
    )


def cart_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🗑 Очистить корзину", callback_data="clear_cart")
            ]
        ]
    )