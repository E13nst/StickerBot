import logging
import hashlib
from typing import List, Optional, Union
from telegram import Update, InlineQueryResultCachedSticker, InlineQueryResultArticle, InputTextMessageContent, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from src.config.settings import WAVESPEED_API_KEY, WAVESPEED_INLINE_CACHE_TIME
from src.utils.prompt_validator import validate_prompt

logger = logging.getLogger(__name__)

INLINE_LIMIT = 20
TELEGRAM_MAX_RESULTS = 50  # Максимальное количество результатов в inline query


def _get_stable_gen_id(raw_query: str, variant: str = "default") -> str:
    """Генерирует стабильный ID для generate result на основе raw_query"""
    # Используем короткий хеш для стабильности (<= 64 байт)
    if not raw_query:
        # Для пустого query используем короткий фиксированный ID
        variant_map = {
            "hint": "gen_hint_",
            "unavailable": "gen_off_",
            "rejected": "gen_reject_",
            "valid": "gen_ready_"
        }
        prefix = variant_map.get(variant, "gen_")
        return f"{prefix}empty"
    
    # Короткий хеш от raw_query (первые 10 hex символов sha256)
    query_hash = hashlib.sha256(raw_query.encode('utf-8')).hexdigest()[:10]
    
    # Префиксы по variant
    variant_map = {
        "hint": "gen_hint_",
        "unavailable": "gen_off_",
        "rejected": "gen_reject_",
        "valid": "gen_ready_"
    }
    prefix = variant_map.get(variant, "gen_")
    
    result_id = f"{prefix}{query_hash}"
    # Проверка длины (должно быть <= 64 байт, но мы используем короткий хеш)
    if len(result_id) > 64:
        result_id = result_id[:64]
    
    return result_id


def build_generate_result(
    raw_query: str,
    prompt_store,
    generation_enabled: bool,
    placeholder_file_id: Optional[str] = None
) -> Optional[Union[InlineQueryResultArticle, InlineQueryResultCachedSticker]]:
    """
    Строит результат генерации для inline query.
    НЕ отправляет ответ в Telegram, только возвращает InlineQueryResultArticle или InlineQueryResultCachedSticker.
    """
    # Вариант A: генерация выключена
    if not generation_enabled:
        return InlineQueryResultArticle(
            id=_get_stable_gen_id(raw_query, "unavailable"),
            title="Generation temporarily unavailable",
            description="Try again later",
            input_message_content=InputTextMessageContent(
                "🎨 STIXLY generation is temporarily unavailable."
            ),
        )
    
    # Вариант B: query пустой или короткий
    if not raw_query or len(raw_query) < 3:
        return InlineQueryResultArticle(
            id=_get_stable_gen_id(raw_query, "hint"),
            title="Generate sticker (STIXLY)",
            description="Type a prompt to generate",
            input_message_content=InputTextMessageContent(
                "🎨 Type a prompt to generate a sticker with @stixlybot"
            ),
        )
    
    # Вариант C: валидация prompt
    is_valid, error_msg = validate_prompt(raw_query)
    
    if not is_valid:
        # Prompt невалиден - показываем ошибку без кнопки
        return InlineQueryResultArticle(
            id=_get_stable_gen_id(raw_query, "rejected"),
            title="Prompt rejected",
            description=error_msg or "Try a different prompt",
            input_message_content=InputTextMessageContent(
                f"❌ Prompt rejected: {error_msg or 'Invalid prompt'}"
            ),
        )
    
    # Prompt валиден - создаем результат с кнопкой Generate
    prompt_hash = prompt_store.store_prompt(raw_query)
    description = raw_query[:60] + "..." if len(raw_query) > 60 else raw_query
    message_text = f"🎨 STIXLY generation: {raw_query[:200]}"
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Generate",
            callback_data=f"gen:{prompt_hash}"
        )
    ]])
    
    # Если есть placeholder_file_id, используем InlineQueryResultCachedSticker
    if placeholder_file_id:
        return InlineQueryResultCachedSticker(
            id=_get_stable_gen_id(raw_query, "valid"),
            sticker_file_id=placeholder_file_id,
            reply_markup=keyboard,
        )
    else:
        # Fallback на старый вариант (текст)
        return InlineQueryResultArticle(
            id=_get_stable_gen_id(raw_query, "valid"),
            title="Generate sticker (STIXLY)",
            description=description,
            input_message_content=InputTextMessageContent(message_text),
            reply_markup=keyboard,
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
    
    # Проверяем, включена ли генерация
    wavespeed_client = context.bot_data.get("wavespeed_client")
    prompt_store = context.bot_data.get("prompt_store")
    
    generation_enabled = bool(WAVESPEED_API_KEY and wavespeed_client and prompt_store)
    
    # Получаем placeholder_file_id из bot_data
    placeholder_file_id = context.bot_data.get("placeholder_sticker_file_id")
    if placeholder_file_id:
        logger.debug(f"Placeholder file_id from bot_data: {placeholder_file_id[:20]}...")
    else:
        logger.warning("Placeholder file_id not found in bot_data - will use text fallback")
    
    # Строим результат генерации с placeholder_file_id
    gen_result = build_generate_result(
        raw_query, 
        prompt_store, 
        generation_enabled,
        placeholder_file_id=placeholder_file_id
    )
    
    # Логируем тип результата для диагностики
    if gen_result:
        result_type = type(gen_result).__name__
        logger.debug(f"Generated result type: {result_type}")
        if isinstance(gen_result, InlineQueryResultCachedSticker):
            logger.info("Using InlineQueryResultCachedSticker for generation result")
        elif isinstance(gen_result, InlineQueryResultArticle):
            logger.warning("Falling back to InlineQueryResultArticle - placeholder sticker not available")
    
    # Парсинг offset
    offset_str = inline_query.offset or "0"
    try:
        offset = int(offset_str)
    except ValueError:
        offset = 0
    
    # Вычисляем effective_search_limit: резервируем слот для generate-результата
    # Мы только уменьшаем поиск, когда INLINE_LIMIT может превысить лимит Telegram (50) с учетом gen_slot.
    # При INLINE_LIMIT=20 сохраняем полные 20 результатов поиска (20+1=21 < 50).
    gen_slot = 1 if gen_result else 0
    effective_search_limit = min(INLINE_LIMIT, TELEGRAM_MAX_RESULTS - gen_slot)
    if effective_search_limit <= 0:
        effective_search_limit = 0
    
    # Строим результаты поиска с учетом effective_search_limit
    search_results = await build_search_results(
        inline_query, raw_query, gallery_service, offset, limit=effective_search_limit
    )
    
    # Дополнительная защита: обрезаем search_results до effective_search_limit
    # (на случай, если gallery_service вернул больше, чем запрошено)
    if len(search_results) > effective_search_limit:
        search_results = search_results[:effective_search_limit]
    
    # Объединяем: генерация всегда первой
    results = []
    if gen_result:
        results.append(gen_result)
    results.extend(search_results)
    
    # Проверка: итоговый список не должен превышать TELEGRAM_MAX_RESULTS
    # (но это не должно произойти, т.к. мы уже ограничили search_results)
    if len(results) > TELEGRAM_MAX_RESULTS:
        # Если по какой-то причине все равно превысили, обрезаем только search_results
        max_search = TELEGRAM_MAX_RESULTS - gen_slot
        results = [gen_result] + search_results[:max_search] if gen_result else search_results[:max_search]
    
    # Пагинация: next_offset считается ТОЛЬКО по search_results с учетом effective_search_limit
    search_count = len(search_results)
    if effective_search_limit > 0 and search_count == effective_search_limit:
        next_offset = str(offset + effective_search_limit)
    else:
        next_offset = ""
    
    # Отвечаем на inline-запрос ОДИН раз
    try:
        await inline_query.answer(
            results,
            cache_time=WAVESPEED_INLINE_CACHE_TIME,
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

