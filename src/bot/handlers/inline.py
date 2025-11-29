import asyncio
import logging
from telegram import Update, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


async def handle_inline_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service
) -> None:
    """Обработчик inline-запросов для поиска стикерсетов"""
    inline_query = update.inline_query
    
    if inline_query is None:
        return
    
    raw_query = (inline_query.query or "").strip()
    
    # Защита от пустого запроса
    if not raw_query:
        await inline_query.answer([], cache_time=5)
        return
    
    # Парсинг offset из строки в int с fallback = 0
    offset_str = inline_query.offset or "0"
    try:
        offset = int(offset_str)
    except (ValueError, TypeError):
        offset = 0
        logger.warning(f"Не удалось распарсить offset '{offset_str}', используем 0")
    
    limit = 20  # размер страницы для inline-результатов
    
    # Вызов галереи
    try:
        items = await gallery_service.search_sticker_sets_inline(
            query=raw_query,
            limit=limit,
            offset=offset,
        )
        
        if not items:
            items = []
    except Exception as e:
        logger.error(f"Ошибка при поиске стикерсетов для inline-запроса: {e}", exc_info=True)
        items = []
    
    # Формируем результаты
    results: list[InlineQueryResultArticle] = []
    for idx, item in enumerate(items):
        item_id = item.get('id')
        if not item_id:
            logger.warning(f"Пропущен элемент без id: {item}")
            continue
        
        title = item.get('title', 'Без названия')
        description = item.get('description', '')
        preview_url = item.get('previewUrl')
        
        # Формируем ссылку на миниапп
        miniapp_url = f"https://sticker-art-e13nst.amvera.io/miniapp/gallery?setId={item_id}"
        
        results.append(
            InlineQueryResultArticle(
                id=f"set_{idx}_{item_id}",
                title=title,
                description=description,
                input_message_content=InputTextMessageContent(miniapp_url),
                thumb_url=preview_url or None,
            )
        )
    
    # Пагинация: определяем next_offset
    if len(results) == limit:
        next_offset = str(offset + limit)
    else:
        next_offset = ""  # пустая строка, если результатов меньше limit
    
    # Отвечаем на inline-запрос
    await inline_query.answer(
        results=results,
        next_offset=next_offset,
        cache_time=30,
    )

