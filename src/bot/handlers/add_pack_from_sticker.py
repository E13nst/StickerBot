import logging
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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

    # Проверяем наличие стикерсета в галерее
    check_result = None
    if gallery_service and gallery_service.is_configured():
        try:
            check_result = await asyncio.to_thread(
                gallery_service.check_sticker_set,
                url=pack_link
            )
        except Exception as e:
            logger.error(f"Error checking sticker set in gallery: {e}", exc_info=True)

    # Обрабатываем результат проверки
    if check_result and 'error' in check_result:
        # Ошибка при проверке
        error_message = check_result.get('message', 'Произошла ошибка при проверке стикерсета')
        await message.reply_text(
            f"Не удалось проверить стикерсет: {error_message}\n\n"
            f"Найден стикерсет: {pack_link}"
        )
        await message.reply_text("Что выбираем дальше?", reply_markup=main_menu_keyboard())
        return CHOOSING_ACTION
    
    if check_result and check_result.get('exists'):
        # Стикерсет уже есть в галерее
        text = (
            "Мы уже знаем этот стикерсет — он уже в Галерее 🔁\n\n"
            "Но твой вклад всё равно важен: ты помогаешь нам собирать самую большую коллекцию.\n\n"
            "Хочешь ART и место в рейтинге — пришли стикер из набора, которого ещё нет в Stixly."
        )
        await message.reply_text(text)
        await message.reply_text("Что выбираем дальше?", reply_markup=main_menu_keyboard())
        return CHOOSING_ACTION
    else:
        # Стикерсета нет в галерее - предлагаем добавить
        text = (
            "О! Такого я ещё не видел 👀\n\n"
            "Этот стикерсет может стать частью самой большой галереи стикеров.\n"
            "За него я начислю тебе +10 ART — это внутренняя валюта за вклад в Stixly.\n\n"
            "Добавим этот набор в Галерею?"
        )
        
        keyboard = [
            [
                InlineKeyboardButton(
                    "Добавить в галерею",
                    callback_data=f"add_to_gallery:{set_name}"
                )
            ],
            [
                InlineKeyboardButton(
                    "Главное меню",
                    callback_data="back_to_main"
                )
            ]
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        
        await message.reply_text(text, reply_markup=reply_markup)
        return CHOOSING_ACTION


async def handle_add_to_gallery(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service,
) -> int:
    """Обработчик кнопки 'Добавить в галерею'"""
    query = update.callback_query
    
    if not query:
        logger.error("handle_add_to_gallery вызван без callback_query")
        return CHOOSING_ACTION
    
    await query.answer()
    
    # Извлекаем имя стикерсета из callback_data
    callback_data = query.data
    if not callback_data or not callback_data.startswith('add_to_gallery:'):
        logger.error(f"Invalid callback_data in handle_add_to_gallery: {callback_data}")
        await query.edit_message_text("Ошибка: неверные данные запроса.")
        return CHOOSING_ACTION
    
    set_name = callback_data.replace('add_to_gallery:', '', 1)
    if not set_name:
        logger.error("Empty set_name in handle_add_to_gallery")
        await query.edit_message_text("Ошибка: не удалось определить стикерсет.")
        return CHOOSING_ACTION
    
    # Восстанавливаем URL стикерсета
    pack_link = f"https://t.me/addstickers/{set_name}"
    user_id = update.effective_user.id
    
    # Показываем сообщение о начале добавления
    try:
        await query.edit_message_text("Добавляю стикерсет в галерею...")
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
    
    # Вызываем save_sticker_set для добавления в галерею
    result = None
    if gallery_service and gallery_service.is_configured():
        try:
            result = await asyncio.to_thread(
                gallery_service.save_sticker_set,
                user_id=user_id,
                sticker_set_id=None,
                sticker_set_link=pack_link,
                title=None,
                visibility="PUBLIC",
            )
        except Exception as e:
            logger.error(f"Error saving sticker set to gallery: {e}", exc_info=True)
    
    # Показываем результат
    if result:
        success_text = (
            "✅ Стикерсет успешно добавлен в галерею!\n\n"
            f"За твой вклад начислено +10 ART.\n\n"
            f"Стикерсет: {pack_link}"
        )
        try:
            await query.edit_message_text(success_text)
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            if query.message:
                await query.message.reply_text(success_text)
    else:
        error_text = (
            "❌ Не удалось добавить стикерсет в галерею.\n\n"
            "Попробуй позже или обратись в поддержку."
        )
        try:
            await query.edit_message_text(error_text)
        except Exception as e:
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            if query.message:
                await query.message.reply_text(error_text)
    
    # Возвращаем пользователя в главное меню
    from src.bot.handlers.start import main_menu_keyboard
    try:
        if query.message:
            await query.message.reply_text("Что выбираем дальше?", reply_markup=main_menu_keyboard())
    except Exception as e:
        logger.warning(f"Не удалось отправить главное меню: {e}")
    
    return CHOOSING_ACTION




