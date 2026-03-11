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
    choose_field = State()
    new_value = State()


class DeleteProduct(StatesGroup):
    choose_product = State()