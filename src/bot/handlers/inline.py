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
        return
    
    raw_query = (inline_query.query or "").strip()
    
    # Защита от пустого запроса
    if not raw_query:
        await inline_query.answer([], cache_time=5, is_personal=True)
        return
    
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
    
    # Формируем результаты
    results: List[InlineQueryResultCachedSticker] = []
    for idx, item in enumerate(stickers):
        file_id = item.get("stickerFileId") or item.get("file_id")
        
        if not file_id:
            continue
        
        results.append(
            InlineQueryResultCachedSticker(
                id=f"st_{offset + idx}_{file_id}",
                sticker_file_id=file_id,
            )
        )
    
    # Пагинация
    next_offset = str(offset + INLINE_LIMIT) if len(stickers) == INLINE_LIMIT else ""
    
    # Отвечаем на inline-запрос
    await update.inline_query.answer(
        results,
        cache_time=30,
        is_personal=True,
        next_offset=next_offset,
    )

