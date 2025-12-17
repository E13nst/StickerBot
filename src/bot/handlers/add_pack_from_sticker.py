"""
Модуль для обработки добавления стикерсетов в галерею.

Содержит обработчики:
- handle_sticker_for_add_pack: основной обработчик стикера
- handle_add_to_gallery: обработчик кнопки "Добавить в галерею"
"""

import logging
import asyncio
from typing import Optional, Dict, Any

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReactionTypeEmoji
from telegram.ext import ContextTypes

from src.bot.states import WAITING_STICKER_PACK_LINK, CHOOSING_ACTION
from src.bot.handlers.start import main_menu_keyboard
from src.utils.links import create_miniapp_deeplink_simple
from src.utils.stickerset_cache import AsyncStickerSetCache
from src.services.gallery_service import GalleryService

logger = logging.getLogger(__name__)


# ============================================================================
# Публичные обработчики (handlers)
# ============================================================================

async def handle_sticker_for_add_pack(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service: GalleryService,
    sticker_service,
    stickerset_cache: AsyncStickerSetCache
) -> int:
    """
    Обработчик стикера для добавления стикерсета в галерею.
    
    Flow:
    1. Извлечь информацию о стикерсете
    2. Проверить наличие в галерее (с кэшем)
    3. Отправить соответствующий ответ (разное для групп и личных чатов)
    
    Args:
        update: Telegram update
        context: Bot context
        gallery_service: Сервис работы с галереей
        sticker_service: Сервис работы со стикерами
        stickerset_cache: Кэш стикерсетов
    
    Returns:
        Следующее состояние ConversationHandler
    """
    message = update.effective_message
    
    logger.info(f"Got update in handle_sticker_for_add_pack: update_id={update.update_id}")
    
    if not message:
        logger.error("handle_sticker_for_add_pack вызван без message")
        return WAITING_STICKER_PACK_LINK
    
    # Шаг 1: Извлечение информации о стикерсете
    pack_info = extract_sticker_pack_info(message.sticker)
    if not pack_info:
        await send_invalid_sticker_message(message)
        return WAITING_STICKER_PACK_LINK

    # Сохраняем для реакций позже
    context.user_data['original_sticker_message_id'] = message.message_id
    context.user_data['sticker_set_name'] = pack_info['set_name']
    context.user_data['sticker_set_link'] = pack_info['link']
    
    # Шаг 2: Проверка наличия в галерее с кэшем
    exists_info = await check_sticker_set_with_cache(
        pack_info['link'],
        gallery_service,
        stickerset_cache
    )
    
    # Шаг 3: Отправка ответа в зависимости от типа чата
    is_group = is_group_chat(update)
    
    if exists_info.get('exists'):
        await handle_existing_sticker_set(update, context, exists_info, is_group)
    else:
        await handle_new_sticker_set(message, pack_info)
    
        return CHOOSING_ACTION


async def handle_add_to_gallery(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service: GalleryService,
    stickerset_cache: AsyncStickerSetCache
) -> int:
    """
    Обработчик кнопки 'Добавить в галерею'.
    
    После успешного добавления отправляет И сообщение И реакцию для любого типа чата.
    
    Args:
        update: Telegram update
        context: Bot context
        gallery_service: Сервис работы с галереей
        stickerset_cache: Кэш стикерсетов
    
    Returns:
        Следующее состояние ConversationHandler
    """
    query = update.callback_query
    
    logger.info(f"handle_add_to_gallery called: callback_data={query.data if query else 'None'}")
    
    if not query:
        logger.error("handle_add_to_gallery вызван без callback_query")
        return CHOOSING_ACTION
    
    await query.answer()
    
    # Извлекаем имя стикерсета из callback_data
    set_name = extract_set_name_from_callback(query.data)
    if not set_name:
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
    
    # Добавляем в галерею
    result = await add_sticker_set_to_gallery(
        pack_link,
        user_id,
        gallery_service
    )
    
    if result:
        # Обновляем кэш после успешного добавления
        await update_cache_after_adding(pack_link, result, stickerset_cache)
        
        # Отправляем сообщение об успехе
        await send_success_message(query, context, pack_link, result)
        
        # Добавляем реакцию 👍 для ЛЮБОГО чата
        await add_success_reaction(update, context)
    else:
        await send_error_message(query)
    
    return CHOOSING_ACTION


# ============================================================================
# Вспомогательные функции (helpers)
# ============================================================================

def extract_sticker_pack_info(sticker) -> Optional[Dict[str, str]]:
    """
    Извлечь информацию о стикерпаке из стикера.
    
    Args:
        sticker: Объект стикера из Telegram
    
    Returns:
        Dict с полями set_name, link, file_id или None если невалидный
    """
    if not sticker:
        logger.warning("No sticker provided")
        return None
    
    set_name = sticker.set_name
    if not set_name:
        logger.warning(f"Sticker without set_name: file_id={sticker.file_id}")
        return None
    
    logger.info(f"Sticker info: file_id={sticker.file_id}, set_name={set_name}")
    
    return {
        'set_name': set_name,
        'link': f"https://t.me/addstickers/{set_name}",
        'file_id': sticker.file_id
    }


async def check_sticker_set_with_cache(
    url: str,
    service: GalleryService,
    cache: AsyncStickerSetCache
) -> Dict[str, Any]:
    """
    Проверить наличие стикерсета в галерее с использованием кэша.
    
    Flow:
    1. Попытка получить из кэша
    2. Fallback на API при cache miss
    3. Сохранение результата в кэш
    
    Args:
        url: URL стикерсета
        service: Сервис галереи
        cache: Кэш стикерсетов
    
    Returns:
        Dict с полями exists (bool|None), id (int|None), error (str|None)
    """
    # Уровень 1: Попытка получить из кэша
    cached_entry = await try_cache_lookup(url, cache)
    if cached_entry is not None:
        logger.info(f"Cache HIT for {url}")
        return {
            'exists': cached_entry['exists'],
            'id': cached_entry.get('set_id'),
            'cached': True
        }
    
    # Уровень 2: Fallback на API
    logger.info(f"Cache MISS for {url}, calling Gallery API")
    api_result = await fetch_from_gallery_api(url, service)
    
    # Уровень 3: Сохранение в кэш (best effort)
    if api_result and 'error' not in api_result:
        await try_cache_save(url, api_result, cache)
    
    return api_result


async def handle_existing_sticker_set(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    exists_info: Dict[str, Any],
    is_group: bool
) -> None:
    """
    Обработка стикерсета, который уже есть в галерее.
    
    Args:
        update: Telegram update
        context: Bot context
        exists_info: Информация о существующем стикерсете
        is_group: Является ли чат групповым
    """
    message = update.effective_message
    
    # Ставим реакцию ✅ для ЛЮБОГО типа чата
    await set_reaction_safe(context.bot, message, '✅')
    
    if not is_group:
        # В личке дополнительно отправляем текстовое сообщение с кнопками
        text = format_already_exists_message()
        keyboard = build_existing_set_keyboard(exists_info, context.bot.username)
        await message.reply_text(text, reply_markup=keyboard)


async def handle_new_sticker_set(
    message,
    pack_info: Dict[str, str]
) -> None:
    """
    Обработка нового стикерсета (которого нет в галерее).
    
    Args:
        message: Telegram message
        pack_info: Информация о стикерсете
    """
    text = format_new_set_proposal()
    keyboard = build_add_to_gallery_keyboard(pack_info['set_name'])
    
    await message.reply_text(text, reply_markup=keyboard)


async def add_sticker_set_to_gallery(
    pack_link: str,
    user_id: int,
    gallery_service: GalleryService
) -> Optional[Dict[str, Any]]:
    """
    Добавить стикерсет в галерею через API.
    
    Args:
        pack_link: URL стикерсета
        user_id: ID пользователя
        gallery_service: Сервис галереи
    
    Returns:
        Результат добавления или None при ошибке
    """
    if not gallery_service or not gallery_service.is_configured():
        logger.warning("Gallery service not configured")
        return None
    
    try:
        result = await asyncio.to_thread(
            gallery_service.save_sticker_set,
            user_id=user_id,
            sticker_set_id=None,
            sticker_set_link=pack_link,
            title=None,
            visibility="PUBLIC"
        )
        
        if result:
            logger.info(f"Sticker set added to gallery: user_id={user_id}, set_id={result.get('id')}")
        
        return result
    except Exception as e:
        logger.error(f"Error saving sticker set to gallery: {e}", exc_info=True)
        return None


async def update_cache_after_adding(
    pack_link: str,
    result: Dict[str, Any],
    cache: AsyncStickerSetCache
) -> None:
    """
    Обновить кэш после успешного добавления стикерсета.
    
    Args:
        pack_link: URL стикерсета
        result: Результат добавления от API
        cache: Кэш стикерсетов
    """
    try:
        await cache.set(
            pack_link,
            exists=True,
            set_id=result.get('id')
        )
        logger.debug(f"Cache updated after adding: {pack_link}")
    except Exception as e:
        logger.warning(f"Failed to update cache after adding: {e}")


async def send_success_message(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    pack_link: str,
    result: Dict[str, Any]
) -> None:
    """
    Отправить сообщение об успешном добавлении стикерсета.
    
    Args:
        query: Callback query
        context: Bot context
        pack_link: URL стикерсета
        result: Результат добавления
    """
    success_text = format_success_message(pack_link, result, context.bot.username)
    keyboard = build_success_keyboard(result)
    
    try:
        await query.edit_message_text(success_text, reply_markup=keyboard)
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        if query.message:
            await query.message.reply_text(success_text, reply_markup=keyboard)


async def add_success_reaction(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> None:
    """
    Добавить реакцию 👍 после успешного добавления стикерсета.
    
    Реакция ставится на исходное сообщение со стикером.
    
    Args:
        update: Telegram update
        context: Bot context
    """
    target_message_id = context.user_data.get('original_sticker_message_id')
    
    if not target_message_id:
        logger.warning("No original_sticker_message_id in user_data")
        return
    
    try:
        await context.bot.set_message_reaction(
            chat_id=update.effective_chat.id,
            message_id=target_message_id,
            reaction=[ReactionTypeEmoji(emoji='👍')]
        )
        logger.info(f"Successfully added reaction 👍 to message {target_message_id}")
    except Exception as e:
        logger.warning(f"Failed to add reaction after gallery addition: {e}")
        # Это не критично, продолжаем работу


# ============================================================================
# Приватные утилиты (utilities)
# ============================================================================

def is_group_chat(update: Update) -> bool:
    """
    Проверить, является ли чат групповым.
    
    Args:
        update: Telegram update
    
    Returns:
        True если чат групповой или супергруппа
    """
    chat_type = update.effective_chat.type
    return chat_type in ['group', 'supergroup']


async def try_cache_lookup(
    url: str,
    cache: AsyncStickerSetCache
) -> Optional[Dict[str, Any]]:
    """
    Попытаться получить запись из кэша.
    
    Args:
        url: URL для поиска
        cache: Кэш
    
    Returns:
        Запись из кэша или None
    """
    try:
        return await cache.get(url)
    except Exception as e:
        logger.warning(f"Cache lookup failed: {e}")
        return None


async def fetch_from_gallery_api(
    url: str,
    service: GalleryService
) -> Dict[str, Any]:
    """
    Получить информацию о стикерсете из Gallery API.
    
    Args:
        url: URL стикерсета
        service: Сервис галереи
    
    Returns:
        Dict с информацией о стикерсете
    """
    if not service or not service.is_configured():
        logger.warning("Gallery service not configured")
        return {'exists': None, 'error': 'service_not_configured'}
    
    try:
        result = await asyncio.to_thread(
            service.check_sticker_set,
            url=url
        )
        
        if result and 'error' in result:
            logger.warning(f"API returned error for {url}: {result.get('message')}")
        
        return result or {'exists': None, 'error': 'no_response'}
    except Exception as e:
        logger.error(f"API error checking sticker set: {e}", exc_info=True)
        return {'exists': None, 'error': 'api_exception'}


async def try_cache_save(
    url: str,
    result: Dict[str, Any],
    cache: AsyncStickerSetCache
) -> None:
    """
    Попытаться сохранить результат в кэш.
    
    Args:
        url: URL стикерсета
        result: Результат проверки
        cache: Кэш
    """
    try:
        await cache.set(
            url,
            result.get('exists'),
            result.get('id')
        )
        logger.debug(f"Cache saved: {url}")
    except Exception as e:
        logger.warning(f"Failed to save to cache: {e}")


async def set_reaction_safe(bot, message, emoji: str) -> None:
    """
    Установить реакцию с graceful failure.
    
    Args:
        bot: Telegram bot
        message: Сообщение для реакции
        emoji: Эмодзи для реакции
    """
    try:
        await bot.set_message_reaction(
            chat_id=message.chat_id,
            message_id=message.message_id,
            reaction=[ReactionTypeEmoji(emoji=emoji)]
        )
        logger.info(f"Set reaction {emoji} on message {message.message_id}")
    except Exception as e:
        logger.warning(f"Failed to set reaction {emoji}: {e}")


def extract_set_name_from_callback(callback_data: str) -> Optional[str]:
    """
    Извлечь имя стикерсета из callback_data.
    
    Args:
        callback_data: Данные callback query
    
    Returns:
        Имя стикерсета или None
    """
    if not callback_data or not callback_data.startswith('add_to_gallery:'):
        logger.error(f"Invalid callback_data: {callback_data}")
        return None
    
    set_name = callback_data.replace('add_to_gallery:', '', 1)
    if not set_name:
        logger.error("Empty set_name in callback_data")
        return None
    
    return set_name


# ============================================================================
# Форматирование сообщений и клавиатур
# ============================================================================

async def send_invalid_sticker_message(message) -> None:
    """Отправить сообщение о невалидном стикере."""
    await message.reply_text(
        "У этого стикера не удалось определить стикерпак.\n"
        "Попробуй прислать стикер из обычного набора."
    )


def format_already_exists_message() -> str:
    """Отформатировать сообщение о том, что стикерсет уже существует."""
    return (
        "Мы уже знаем этот стикерсет — он уже в Галерее 🔁\n\n"
        "Но твой вклад всё равно важен: ты помогаешь нам собирать "
        "самую большую коллекцию.\n\n"
        "Хочешь ART и место в рейтинге — пришли стикер из набора, "
        "которого ещё нет в Stixly."
    )


def format_new_set_proposal() -> str:
    """Отформатировать предложение добавить новый стикерсет."""
    return (
        "О! Такого я ещё не видел 👀\n\n"
        "Этот стикерсет может стать частью самой большой галереи стикеров.\n"
        "За него я начислю тебе +10 ART — это внутренняя валюта за вклад в Stixly.\n\n"
        "Добавим этот набор в Галерею?"
    )


def format_success_message(
    pack_link: str,
    result: Dict[str, Any],
    bot_username: Optional[str]
) -> str:
    """Отформатировать сообщение об успешном добавлении."""
    text = (
            "✅ Стикерсет успешно добавлен в галерею!\n\n"
            f"За твой вклад начислено +10 ART.\n\n"
            f"Стикерсет: {pack_link}"
        )
        
    set_id = result.get('id')
    if set_id and bot_username:
        miniapp_deeplink = create_miniapp_deeplink_simple(bot_username, f"set_id={set_id}")
        text += f"\n\nПосмотреть в Stixly: {miniapp_deeplink}"
    
    return text


def build_existing_set_keyboard(
    exists_info: Dict[str, Any],
    bot_username: Optional[str]
) -> InlineKeyboardMarkup:
    """Построить клавиатуру для существующего стикерсета."""
    keyboard = []
    set_id = exists_info.get('id')
    
    if set_id:
        miniapp_url = f"https://sticker-art-e13nst.amvera.io/miniapp/gallery?set_id={set_id}"
        keyboard.append([
            InlineKeyboardButton(
                "Посмотреть в Stixly",
                web_app=WebAppInfo(url=miniapp_url)
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            "Главное меню",
            callback_data="back_to_main"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


def build_add_to_gallery_keyboard(set_name: str) -> InlineKeyboardMarkup:
    """Построить клавиатуру для добавления в галерею."""
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
    
    return InlineKeyboardMarkup(keyboard)


def build_success_keyboard(result: Dict[str, Any]) -> InlineKeyboardMarkup:
    """Построить клавиатуру для сообщения об успехе."""
    keyboard = []
    set_id = result.get('id')
    
    if set_id:
        miniapp_url = f"https://sticker-art-e13nst.amvera.io/miniapp/gallery?set_id={set_id}"
        keyboard.append([
            InlineKeyboardButton(
                "Посмотреть в Stixly",
                web_app=WebAppInfo(url=miniapp_url)
            )
        ])
    
    keyboard.append([
        InlineKeyboardButton(
            "Главное меню",
            callback_data="back_to_main"
        )
    ])
    
    return InlineKeyboardMarkup(keyboard)


async def send_error_message(query) -> None:
    """Отправить сообщение об ошибке."""
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
