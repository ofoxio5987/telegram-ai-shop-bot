from aiogram.fsm.state import State, StatesGroup


class SearchState(StatesGroup):
    waiting_for_query = State()


class AssistantState(StatesGroup):
    waiting_for_category = State()
    waiting_for_budget = State()
    waiting_for_priority = State()