import asyncio
import logging
import re
from typing import Optional, Dict, Any, List
from telegram import Update, InlineQueryResultCachedSticker
from telegram.ext import ContextTypes

logger = logging.getLogger(__name__)


def parse_inline_query(query: str) -> Dict[str, Any]:
    """
    Парсит inline-запрос, извлекая emoji, категории и текст
    
    Returns:
        dict с полями:
            - emoji: первый найденный emoji (или None)
            - category_keys: список категорий (слова с префиксом # без #), может быть пустым
            - text: остальной текст без emoji и #категорий
    """
    if not query:
        return {"emoji": None, "category_keys": [], "text": ""}
    
    # Поиск emoji (юникод диапазоны для основных emoji)
    emoji_pattern = re.compile(
        "["
        "\U0001F600-\U0001F64F"  # Emoticons
        "\U0001F300-\U0001F5FF"  # Symbols & Pictographs
        "\U0001F680-\U0001F6FF"  # Transport & Map Symbols
        "\U0001F1E0-\U0001F1FF"  # Flags
        "\U00002702-\U000027B0"  # Dingbats
        "\U000024C2-\U0001F251"  # Enclosed characters
        "]+",
        flags=re.UNICODE
    )
    emoji_match = emoji_pattern.search(query)
    emoji = emoji_match.group(0) if emoji_match else None
    
    # Поиск всех категорий (слова с префиксом #)
    category_pattern = re.compile(r"#(\w+)", re.UNICODE)
    category_matches = category_pattern.findall(query)
    category_keys = list(category_matches) if category_matches else []
    
    # Убираем emoji и все #категории из текста
    text = query
    if emoji:
        text = text.replace(emoji, "", 1)  # Убираем первый emoji
    
    # Убираем все #категории из текста
    text = category_pattern.sub("", text)
    
    text = re.sub(r"\s+", " ", text.strip())  # Нормализуем пробелы
    
    return {
        "emoji": emoji,
        "category_keys": category_keys,
        "text": text
    }


async def handle_inline_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service
) -> None:
    """Обработчик inline-запросов для поиска стикеров"""
    inline_query = update.inline_query
    
    if inline_query is None:
        return
    
    query = (inline_query.query or "").strip()
    
    # Парсинг offset из строки в int с fallback = 0
    offset_str = inline_query.offset or "0"
    try:
        offset = int(offset_str)
    except (ValueError, TypeError):
        offset = 0
        logger.warning(f"Не удалось распарсить offset '{offset_str}', используем 0")
    
    limit = 20  # размер страницы для inline-результатов
    
    # Защита от пустого запроса
    if not query:
        logger.info("Пустой inline-запрос пропущен")
        await inline_query.answer(
            results=[],
            cache_time=5,
            is_personal=True,
            next_offset=""
        )
        return
    
    # Парсим запрос
    parsed = parse_inline_query(query)
    
    # Проверка: если пустой запрос (нет текста, категорий и emoji)
    if not parsed["text"] and not parsed["category_keys"] and not parsed["emoji"]:
        logger.info("Пустой inline-запрос пропущен (нет текста, категорий и emoji)")
        await inline_query.answer(
            results=[],
            cache_time=5,
            is_personal=True,
            next_offset=""
        )
        return
    
    # Формируем payload для поиска
    query_payload = {
        "query_text": parsed["text"],
        "emoji": parsed["emoji"],
        "category_keys": parsed["category_keys"],
        "limit": limit,
        "offset": offset,
    }
    
    # Вызов галереи в отдельном потоке, как в других хэндлерах
    try:
        items = await asyncio.to_thread(
            gallery_service.search_stickers_inline,
            query_payload=query_payload,
            limit=limit,
            offset=offset,
        )
        
        if not items:
            items = []
    except Exception as e:
        logger.error(f"Ошибка при поиске стикеров для inline-запроса: {e}", exc_info=True)
        items = []
    
    # Формируем результаты
    results: list[InlineQueryResultCachedSticker] = []
    for idx, item in enumerate(items):
        # Поддержка разных форматов: stickerFileId или file_id
        file_id = item.get("stickerFileId") or item.get("file_id")
        
        if not file_id:
            logger.warning(f"Пропущен элемент без file_id: {item}")
            continue
        
        results.append(
            InlineQueryResultCachedSticker(
                id=f"st_{offset + idx}_{file_id}",
                sticker_file_id=file_id,
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
        cache_time=5,
        is_personal=True,
        next_offset=next_offset,
    )

