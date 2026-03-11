from aiogram.fsm.state import State, StatesGroup


class AddCategory(StatesGroup):
    name = State()
    description = State()


class EditCategory(StatesGroup):
    old_name = State()
    new_name = State()
    new_description = State()


class DeleteCategory(StatesGroup):
    name = State()