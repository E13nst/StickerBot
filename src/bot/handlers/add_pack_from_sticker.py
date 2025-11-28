import logging
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.states import WAITING_STICKER_PACK_LINK, CHOOSING_ACTION
from src.bot.handlers.start import main_menu_keyboard

logger = logging.getLogger(__name__)


async def handle_sticker_for_add_pack(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service,
    sticker_service
) -> int:
    """Обработка стикера для добавления стикерсета в галерею - минимальная версия"""
    message = update.effective_message
    
    logger.info("Got update in handle_sticker_for_add_pack: update_id=%s", update.update_id)
    
    if not message:
        logger.error("handle_sticker_for_add_pack вызван без message")
        return WAITING_STICKER_PACK_LINK
    
    sticker = message.sticker
    
    if not sticker:
        logger.warning("Message without sticker in handle_sticker_for_add_pack")
        await message.reply_text(
            "Мне нужен именно стикер, не картинка.\n"
            "Пришли стикер из того набора, который хочешь добавить в галерею."
        )
        return WAITING_STICKER_PACK_LINK

    set_name = sticker.set_name
    logger.info("Sticker info: file_id=%s, set_name=%s", sticker.file_id, set_name)

    if not set_name:
        logger.warning("Sticker without set_name: file_id=%s", sticker.file_id)
        await message.reply_text(
            "У этого стикера не удалось определить стикерпак.\n"
            "Попробуй прислать стикер из обычного набора."
        )
        return WAITING_STICKER_PACK_LINK

    # БАЗОВАЯ логика: просто ссылка на пак по имени набора
    pack_link = f"https://t.me/addstickers/{set_name}"
    
    # Сохраняем в context для дальнейшего использования
    context.user_data['sticker_set_name'] = set_name
    context.user_data['sticker_set_link'] = pack_link

    text = (
        "Нашёл стикерсет этого стикера:\n"
        f"{pack_link}\n\n"
        "Скоро я смогу добавить его в галерею и начислить тебе +10 ART."
    )

    await message.reply_text(text)

    # Вернём пользователя в главное меню
    await message.reply_text("Что выбираем дальше?", reply_markup=main_menu_keyboard())
    
    return CHOOSING_ACTION




