from aiogram.fsm.state import State, StatesGroup


class SearchState(StatesGroup):
    waiting_for_query = State()


class AssistantState(StatesGroup):
    waiting_for_request = State()
