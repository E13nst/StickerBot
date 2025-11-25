import logging
from telegram import Update, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from src.bot.states import WAITING_STICKER, WAITING_EMOJI

logger = logging.getLogger(__name__)


async def handle_sticker(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_service,
    show_existing_sets_func=None,
) -> int:
    """Обработка присланного изображения"""
    user_data = context.user_data

    if 'action' not in user_data:
        await update.message.reply_text("Что-то пошло не так. Запусти процесс заново командой /start.")
        context.user_data.clear()
        return ConversationHandler.END

    try:
        # Получаем файл изображения
        if update.message and update.message.photo:
            photo_file = await update.message.photo[-1].get_file()
        elif update.message and update.message.document:
            photo_file = await update.message.document.get_file()
        else:
            await update.message.reply_text("Пришли, пожалуйста, изображение.")
            return WAITING_STICKER

        # Скачиваем изображение
        image_data = await photo_file.download_as_bytearray()

        # Для добавления в существующий набор убедимся, что набор выбран
        if user_data.get('action') == 'add_existing' and not user_data.get('selected_set'):
            if show_existing_sets_func:
                await update.message.reply_text(
                    "Сначала выбери набор из списка, затем пришли изображение."
                )
                return await show_existing_sets_func(update, context, page=user_data.get('existing_page', 0))
            else:
                await update.message.reply_text(
                    "Сначала выбери набор из списка, затем пришли изображение."
                )
                return WAITING_STICKER

        # Конвертируем в WebP
        webp_data = image_service.convert_to_webp(bytes(image_data))

        # Сохраняем во временные данные пользователя
        user_data['current_webp'] = webp_data

        await update.message.reply_text(
            "Пришли смайл, который подходит к этому стикеру.",
            reply_markup=ReplyKeyboardRemove()
        )

        return WAITING_EMOJI

    except Exception as e:
        logger.error(f"Ошибка обработки изображения: {e}")
        await update.message.reply_text(
            "Произошла ошибка при обработке изображения. Попробуй другое изображение."
        )
        return WAITING_STICKER

