import logging
from telegram import Update
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отмена диалога"""
    from telegram import ReplyKeyboardRemove
    
    context.user_data.clear()

    await update.message.reply_text(
        "Диалог отменен. Используй /start чтобы начать заново.",
        reply_markup=ReplyKeyboardRemove()
    )

    return -1  # ConversationHandler.END


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Глобальный обработчик ошибок"""
    logger.exception("Unhandled exception while processing update %s", update, exc_info=context.error)

    try:
        if update:
            message = getattr(update, 'effective_message', None)
            if message:
                await message.reply_text("Ой, что-то пошло не так. Попробуй ещё раз чуть позже.")
                return
            callback = getattr(update, 'callback_query', None)
            if callback:
                await callback.answer("Случилась ошибка. Попробуй снова.", show_alert=True)
    except Exception as notify_error:
        logger.error("Failed to notify user about error: %s", notify_error)

