import logging
from typing import List
from telegram import Update, InlineQueryResultCachedSticker
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)

INLINE_LIMIT = 20


async def handle_inline_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service
) -> None:
    """Обработчик inline-запросов для поиска стикеров"""
    inline_query = update.inline_query
    
    if inline_query is None:
        logger.warning("handle_inline_query вызван, но inline_query is None")
        return
    
    raw_query = (inline_query.query or "").strip()
    
    # Парсинг offset
    offset_str = inline_query.offset or "0"
    try:
        offset = int(offset_str)
    except ValueError:
        offset = 0
    
    # Вызов галереи
    try:
        stickers = await gallery_service.search_stickers_inline(
            query=raw_query,
            limit=INLINE_LIMIT,
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
    
    # Пагинация
    next_offset = str(offset + INLINE_LIMIT) if len(stickers) == INLINE_LIMIT else ""
    
    # Отвечаем на inline-запрос
    try:
        await inline_query.answer(
            results,
            cache_time=5,
            is_personal=True,
            next_offset=next_offset,
        )
    except Exception as e:
        # Обрабатываем ошибки gracefully (не падаем при timeout или invalid query)
        error_msg = str(e)
        if "Result_id_invalid" in error_msg or "invalid" in error_msg.lower():
            logger.error(
                f"Ошибка валидации ID результатов для inline-запроса: {error_msg}. "
                f"raw_query={raw_query!r}, offset={offset}, results_count={len(results)}"
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

