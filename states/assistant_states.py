from aiogram.fsm.state import State, StatesGroup


class SearchState(StatesGroup):
    waiting_for_query = State()


class ManagerOrderSearchState(StatesGroup):
    waiting_for_order_id = State()
