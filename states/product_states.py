from aiogram.fsm.state import State, StatesGroup


class AddProduct(StatesGroup):
    name = State()
    description = State()
    price = State()
    image_url = State()
    category = State()
    stock = State()


class EditProduct(StatesGroup):
    choose_product = State()
    new_price = State()


class DeleteProduct(StatesGroup):
    choose_product = State()