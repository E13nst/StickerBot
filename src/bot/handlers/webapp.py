"""Handlers для обработки данных от MiniApp через WebApp Query"""
import logging
import json
from typing import Optional
from telegram import Update, InlineQueryResultCachedSticker, InlineQueryResultArticle, InputTextMessageContent
from telegram.ext import ContextTypes
from telegram.error import TelegramError

logger = logging.getLogger(__name__)


async def handle_webapp_query(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """
    Обработчик ответов от MiniApp через WebApp Query.
    
    Ожидает данные в формате JSON:
    {
        "file_id": "...",  # Обязательно: file_id стикера
        "chat_id": "...",  # Опционально: для fallback отправки
        "inline_message_id": "..."  # Опционально: для обновления inline сообщения
    }
    """
    # Безопасное получение web_app_query (может отсутствовать в некоторых версиях библиотеки)
    web_app_query = getattr(update, 'web_app_query', None)
    
    if not web_app_query:
        logger.warning("handle_webapp_query вызван, но web_app_query is None или отсутствует")
        return
    
    if not web_app_query.from_user:
        logger.error("web_app_query.from_user is None, cannot process query")
        return
    
    query_id = web_app_query.query_id
    user_id = web_app_query.from_user.id
    username = web_app_query.from_user.username or "без username"
    
    logger.info(
        f"[handle_webapp_query] WebApp query получен: query_id={query_id}, "
        f"user_id={user_id}, username={username}"
    )
    
    # Парсим данные от MiniApp
    try:
        data_str = web_app_query.data
        if not data_str:
            logger.error(f"[handle_webapp_query] Empty data from MiniApp for query_id={query_id}")
            return
        
        data = json.loads(data_str)
        logger.info(
            f"[handle_webapp_query] Данные от MiniApp получены: "
            f"query_id={query_id}, data_length={len(data_str)}, "
            f"data_preview={data_str[:100]}..."
        )
        logger.debug(f"[handle_webapp_query] Parsed data: {data}")
        
        file_id = data.get("file_id")
        chat_id = data.get("chat_id")
        inline_message_id = data.get("inline_message_id")
        
        if not file_id:
            logger.error(f"[handle_webapp_query] Missing file_id in data from MiniApp: {data}")
            return
        
        # Формируем результат для answerWebAppQuery
        result = InlineQueryResultCachedSticker(
            id="webapp_result_1",
            sticker_file_id=file_id
        )
        
        # Отправляем результат через answerWebAppQuery
        try:
            logger.info(
                f"[handle_webapp_query] Вызываю answerWebAppQuery для query_id={query_id}, "
                f"file_id={file_id[:20]}..."
            )
            await context.bot.answer_web_app_query(
                web_app_query_id=query_id,
                result=result
            )
            logger.info(
                f"[handle_webapp_query] SUCCESS: answerWebAppQuery выполнен успешно. "
                f"query_id={query_id}, file_id={file_id[:20]}..., "
                f"result_id={result.id}"
            )
            return
            
        except TelegramError as e:
            error_msg = str(e)
            logger.warning(
                f"[handle_webapp_query] Failed to answer webapp query: {error_msg}. "
                f"query_id={query_id}, user_id={user_id}"
            )
            
            # Обработка устаревших query: отправляем контент напрямую в личные сообщения
            if "too old" in error_msg.lower() or "expired" in error_msg.lower() or "invalid" in error_msg.lower():
                logger.info(
                    f"[handle_webapp_query] Query expired, sending sticker directly to user {user_id}"
                )
                try:
                    # Используем chat_id из данных или user_id как fallback
                    # chat_id может быть строкой или int, конвертируем в int если возможно
                    if chat_id:
                        try:
                            target_chat_id = int(chat_id) if isinstance(chat_id, str) and chat_id.isdigit() else chat_id
                        except (ValueError, AttributeError):
                            target_chat_id = user_id
                    else:
                        target_chat_id = user_id
                    
                    await context.bot.send_sticker(
                        chat_id=target_chat_id,
                        sticker=file_id
                    )
                    logger.info(
                        f"[handle_webapp_query] SUCCESS: Sent sticker directly to chat {target_chat_id} "
                        f"as fallback for expired query"
                    )
                except Exception as send_error:
                    logger.error(
                        f"[handle_webapp_query] ERROR: Failed to send sticker as fallback: {send_error}",
                        exc_info=True
                    )
            else:
                # Другие ошибки - логируем и не обрабатываем
                logger.error(
                    f"[handle_webapp_query] ERROR: Unexpected error in answerWebAppQuery: {error_msg}",
                    exc_info=True
                )
    
    except json.JSONDecodeError as e:
        logger.error(
            f"[handle_webapp_query] ERROR: Failed to parse JSON data from MiniApp: {e}. "
            f"Raw data: {web_app_query.data[:200] if web_app_query.data else 'None'}",
            exc_info=True
        )
    
    except Exception as e:
        logger.error(
            f"[handle_webapp_query] ERROR: Unexpected exception: {e}",
            exc_info=True
        )
