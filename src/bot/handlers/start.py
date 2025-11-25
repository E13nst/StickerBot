import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ContextTypes

from src.bot.states import CHOOSING_ACTION

logger = logging.getLogger(__name__)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога"""
    user = update.message.from_user
    context.user_data.clear()

    reply_keyboard = [
        ['Создать новый стикерсет', 'Добавить в существующий'],
        ['Управлять публикацией']
    ]

    await update.message.reply_text(
        f"Привет, {user.first_name}! Я помогу тебе собрать стикерсет.\n"
        "Выбирай, что будем делать:",
        reply_markup=ReplyKeyboardMarkup(
            reply_keyboard,
            one_time_keyboard=True,
            input_field_placeholder='Что будем делать?'
        )
    )

    return CHOOSING_ACTION

