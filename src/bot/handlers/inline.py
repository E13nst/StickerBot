import logging
from typing import List, Optional
from urllib.parse import urlencode
from telegram import Update, InlineQueryResultCachedSticker, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.config.settings import WAVESPEED_INLINE_CACHE_TIME, MINIAPP_GALLERY_URL
from src.utils.links import create_miniapp_deeplink

logger = logging.getLogger(__name__)

INLINE_LIMIT = 20
TELEGRAM_MAX_RESULTS = 50  # Максимальное количество результатов в inline query


def build_miniapp_button_result(
    inline_query_id: str,
    user_id: int,
    bot_username: Optional[str] = None
) -> Optional[InlineQueryResultArticle]:
    """
    Создает единственный результат с кнопкой для открытия MiniApp.
    Используется только для пустых inline-запросов.
    
    ВАЖНО: В inline query нельзя использовать WebApp кнопку (web_app).
    Используем url кнопку с deep link для открытия MiniApp.
    
    Args:
        inline_query_id: ID inline query для передачи в MiniApp
        user_id: ID пользователя для передачи в MiniApp
        bot_username: Имя бота без @ (для создания deep link)
    
    Returns:
        InlineQueryResultArticle с url button или None, если MiniApp URL не настроен
    """
    if not MINIAPP_GALLERY_URL:
        logger.warning("MINIAPP_GALLERY_URL not configured, cannot create MiniApp button")
        return None
    
    # Формируем URL MiniApp с параметрами
    params = {
        "inline_query_id": inline_query_id,
        "user_id": str(user_id),
    }
    
    web_app_url = f"{MINIAPP_GALLERY_URL}?{urlencode(params)}"
    
    # В inline query нельзя использовать web_app кнопку, используем url кнопку
    # Если есть bot_username, создаем deep link, иначе используем прямой URL
    if bot_username:
        # Создаем deep link через startapp для открытия MiniApp
        button_url = create_miniapp_deeplink(bot_username, web_app_url)
        logger.info(f"Created MiniApp deep link: {button_url[:100]}...")
    else:
        # Fallback: используем прямой URL (может открыться в браузере)
        button_url = web_app_url
        logger.warning("bot_username not available, using direct URL (may open in browser)")
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "🎨 Нарисовать стикер с ИИ ≻",
            url=button_url
        )
    ]])
    
    logger.info(f"Created MiniApp button with URL: {button_url[:100]}...")
    
    # Используем улучшенный формат как у конкурентов
    # ВАЖНО: В inline query нельзя использовать WebApp кнопку (web_app).
    # Используем url кнопку с deep link через startapp.
    # При нажатии на результат отправится минимальное сообщение "🎨",
    # пользователь должен нажать на кнопку для открытия MiniApp.
    return InlineQueryResultArticle(
        id="create_sticker_1",
        title="🎨 Нарисовать стикер с ИИ",
        description="Нажмите кнопку для создания",
        # Минимальное сообщение, которое отправится при нажатии на результат (не на кнопку)
        # Пользователь должен нажать на кнопку "🎨 Нарисовать стикер с ИИ ≻" для открытия MiniApp
        input_message_content=InputTextMessageContent(
            "🎨",
            parse_mode=None
        ),
        reply_markup=keyboard,
        # Опционально: можно добавить thumb_url для иконки
        # thumb_url="https://ваш-домен/thumb.png",
        # thumb_width=64,
        # thumb_height=64
    )


async def build_search_results(
    inline_query,
    raw_query: str,
    gallery_service,
    offset: int,
    limit: int = INLINE_LIMIT
) -> List[InlineQueryResultCachedSticker]:
    """
    Строит результаты поиска для inline query.
    НЕ отправляет ответ в Telegram, только возвращает список результатов.
    
    Args:
        limit: Максимальное количество результатов поиска (по умолчанию INLINE_LIMIT)
    """
    try:
        stickers = await gallery_service.search_stickers_inline(
            query=raw_query,
            limit=limit,
            offset=offset,
        )
        
        if not stickers:
            stickers = []
    except Exception as e:
        logger.error(f"Ошибка при поиске стикеров для inline-запроса: {e}", exc_info=True)
        stickers = []
    
    # Логирование результата
    logger.info(
        f"inline search: raw_query={raw_query!r}, offset={offset}, "
        f"found_items={len(stickers)}"
    )
    
    # Формируем результаты
    results: List[InlineQueryResultCachedSticker] = []
    for idx, item in enumerate(stickers):
        file_id = item.get("stickerFileId") or item.get("file_id")
        
        if not file_id:
            continue
        
        # Формируем короткий ID (Telegram ограничивает до 64 символов)
        # Используем setId и индекс для уникальности
        setId = item.get("setId")
        if setId is not None:
            result_id = f"s{setId}_{offset + idx}"
        else:
            # Fallback: используем хэш file_id для уникальности
            file_id_hash = hash(file_id) % 1000000  # Ограничиваем до 6 цифр
            result_id = f"st_{abs(file_id_hash)}_{offset + idx}"
        
        # Обрезаем до 64 символов на всякий случай
        if len(result_id) > 64:
            result_id = result_id[:64]
        
        results.append(
            InlineQueryResultCachedSticker(
                id=result_id,
                sticker_file_id=file_id,
            )
        )
    
    return results


async def handle_inline_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service
) -> None:
    """Обработчик inline-запросов для поиска стикеров и генерации"""
    inline_query = update.inline_query
    
    if inline_query is None:
        logger.warning("handle_inline_query вызван, но inline_query is None")
        return
    
    raw_query = (inline_query.query or "").strip()
    
    # Извлекаем параметры для передачи в MiniApp
    inline_query_id = inline_query.id
    if not inline_query.from_user:
        logger.error("inline_query.from_user is None, cannot process query")
        return
    
    user_id = inline_query.from_user.id
    
    # СЦЕНАРИЙ А: Пустой запрос - только кнопка MiniApp для генерации
    if not raw_query:
        logger.info(
            f"Inline query от пользователя {user_id}: query='{raw_query}', "
            f"inline_query_id={inline_query_id}, user_id={user_id}"
        )
        
        # Получаем bot_username для создания deep link
        bot_username = context.bot.username if context.bot else None
        
        miniapp_result = build_miniapp_button_result(
            inline_query_id=inline_query_id,
            user_id=user_id,
            bot_username=bot_username
        )
        
        if not miniapp_result:
            # Если MiniApp URL не настроен, возвращаем пустой результат
            logger.warning("MiniApp button not available, returning empty results")
            try:
                await inline_query.answer(
                    [],
                    cache_time=0,  # Не кэшируем пустые результаты
                    is_personal=True,
                )
            except Exception as e:
                logger.error(f"Error answering empty inline query: {e}", exc_info=True)
            return
        
        # Возвращаем только кнопку MiniApp (один результат, как у конкурентов)
        try:
            await inline_query.answer(
                [miniapp_result],
                cache_time=0,  # Не кэшируем, чтобы всегда показывать актуальную кнопку
                is_personal=True,
            )
            # Логируем URL кнопки (может быть url или web_app)
            button_url = None
            if miniapp_result.reply_markup and miniapp_result.reply_markup.inline_keyboard:
                button = miniapp_result.reply_markup.inline_keyboard[0][0]
                button_url = button.url if hasattr(button, 'url') and button.url else 'N/A'
            logger.info(
                f"Successfully sent MiniApp button for empty query. "
                f"Button URL: {button_url[:80] if button_url else 'N/A'}..."
            )
        except Exception as e:
            logger.error(f"Error answering inline query with MiniApp button: {e}", exc_info=True)
        return
    
    # СЦЕНАРИЙ B: Есть запрос - только поиск по галерее
    logger.info(f"Search query detected: {raw_query!r}, inline_query_id={inline_query_id}, user_id={user_id}")
    
    # Парсинг offset
    offset_str = inline_query.offset or "0"
    try:
        offset = int(offset_str)
    except ValueError:
        offset = 0
    
    # Строим результаты поиска
    search_results = await build_search_results(
        inline_query, raw_query, gallery_service, offset, limit=INLINE_LIMIT
    )
    
    # Дополнительная защита: обрезаем search_results до INLINE_LIMIT
    if len(search_results) > INLINE_LIMIT:
        search_results = search_results[:INLINE_LIMIT]
    
    # Проверка: итоговый список не должен превышать TELEGRAM_MAX_RESULTS
    if len(search_results) > TELEGRAM_MAX_RESULTS:
        search_results = search_results[:TELEGRAM_MAX_RESULTS]
    
    # Пагинация: next_offset считается по search_results
    if len(search_results) == INLINE_LIMIT:
        next_offset = str(offset + INLINE_LIMIT)
    else:
        next_offset = ""
    
    # Отвечаем на inline-запрос только результатами поиска
    try:
        await inline_query.answer(
            search_results,
            cache_time=WAVESPEED_INLINE_CACHE_TIME,
            is_personal=True,
            next_offset=next_offset,
        )
        logger.info(f"Successfully sent {len(search_results)} search results for query: {raw_query!r}")
    except Exception as e:
        # Обрабатываем ошибки gracefully (не падаем при timeout или invalid query)
        error_msg = str(e)
        if "Result_id_invalid" in error_msg or "invalid" in error_msg.lower():
            logger.error(
                f"Ошибка валидации ID результатов для inline-запроса: {error_msg}. "
                f"raw_query={raw_query!r}, offset={offset}, results_count={len(search_results)}"
            )
        elif "timeout" in error_msg.lower() or "too old" in error_msg.lower():
            logger.warning(
                f"Запрос истек или слишком старый: {error_msg}. "
                f"raw_query={raw_query!r}, offset={offset}"
            )
        else:
            logger.error(
                f"Ошибка при отправке ответа на inline-запрос: {error_msg}",
                exc_info=True
            )
