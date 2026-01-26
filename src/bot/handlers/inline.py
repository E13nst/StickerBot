import logging
from typing import List, Optional
from urllib.parse import urlencode
from telegram import Update, InlineQueryResultCachedSticker, InlineQueryResultsButton, WebAppInfo
from telegram.ext import ContextTypes

from src.config.settings import WAVESPEED_INLINE_CACHE_TIME, MINIAPP_GALLERY_URL

logger = logging.getLogger(__name__)

INLINE_LIMIT = 20
TELEGRAM_MAX_RESULTS = 50  # Максимальное количество результатов в inline query


def create_miniapp_button(
    inline_query_id: str,
    user_id: int
) -> Optional[InlineQueryResultsButton]:
    """
    Создает кнопку для открытия MiniApp в inline query.
    Кнопка отображается НАД результатами и открывает mini app напрямую без отправки сообщения.
    
    Args:
        inline_query_id: ID inline query для передачи в MiniApp
        user_id: ID пользователя для передачи в MiniApp
    
    Returns:
        InlineQueryResultsButton с WebAppInfo или None, если MiniApp URL не настроен
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
    
    logger.info(f"Created MiniApp button with URL: {web_app_url[:100]}...")
    
    return InlineQueryResultsButton(
        text="🎨 Нарисовать стикер с ИИ ≻",
        web_app=WebAppInfo(url=web_app_url)
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
        
        # Создаем кнопку MiniApp
        miniapp_button = create_miniapp_button(
            inline_query_id=inline_query_id,
            user_id=user_id
        )
        
        if not miniapp_button:
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
        
        # Возвращаем пустой список результатов с кнопкой MiniApp
        # Кнопка отобразится НАД результатами и откроет mini app напрямую
        try:
            await inline_query.answer(
                [],  # Пустой список результатов
                cache_time=0,  # Не кэшируем, чтобы всегда показывать актуальную кнопку
                is_personal=True,
                button=miniapp_button  # Кнопка откроет mini app без отправки сообщения
            )
            logger.info(
                f"Successfully sent MiniApp button for empty query. "
                f"Button will open mini app directly without sending message."
            )
        except Exception as e:
            logger.error(f"Error answering inline query with MiniApp button: {e}", exc_info=True)
        return
    
    # СЦЕНАРИЙ B: Есть запрос - поиск по галерее + кнопка MiniApp
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
    
    # Создаем кнопку MiniApp для отображения НАД результатами поиска
    miniapp_button = create_miniapp_button(
        inline_query_id=inline_query_id,
        user_id=user_id
    )
    
    # Отвечаем на inline-запрос результатами поиска И кнопкой MiniApp
    try:
        await inline_query.answer(
            search_results,
            cache_time=WAVESPEED_INLINE_CACHE_TIME,
            is_personal=True,
            next_offset=next_offset,
            button=miniapp_button  # Кнопка будет показана НАД результатами поиска
        )
        logger.info(
            f"Successfully sent {len(search_results)} search results with MiniApp button "
            f"for query: {raw_query!r}"
        )
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
