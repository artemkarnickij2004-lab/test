"""FSM-состояния админки."""
from aiogram.fsm.state import State, StatesGroup


class AddPhoto(StatesGroup):
    image = State()        # ждём саму фотографию
    title = State()        # ждём название
    description = State()  # ждём описание
    price = State()        # ждём цену в звёздах
