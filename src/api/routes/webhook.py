import json
import logging
import secrets
from fastapi import Request, HTTPException

from src.config.settings import WEBHOOK_SECRET_TOKEN, WEBHOOK_IP_CHECK_ENABLED
from src.api.middleware.telegram_ip_check import verify_telegram_ip

logger = logging.getLogger(__name__)

# Глобальная переменная для хранения экземпляра бота
bot_instance = None


def set_bot_instance(instance):
    """Установить экземпляр бота"""
    global bot_instance
    bot_instance = instance


async def telegram_webhook(request: Request):
    """
    Защищенный webhook endpoint для получения обновлений от Telegram
    
    Использует:
    1. Secret token проверку (обязательно)
    2. Rate limiting (защита от DoS)
    3. IP-адреса проверку (опционально, если WEBHOOK_IP_CHECK_ENABLED=true)
    """
    client_ip = request.client.host if request.client else "unknown"
    
    # Получаем секретный токен из заголовка напрямую
    x_telegram_bot_api_secret_token = request.headers.get("X-Telegram-Bot-Api-Secret-Token")
    
    logger.info(f"telegram_webhook вызван от IP: {client_ip}, заголовок токена: {'есть' if x_telegram_bot_api_secret_token else 'нет'}")
    
    # Опциональная проверка IP-адреса Telegram
    if WEBHOOK_IP_CHECK_ENABLED:
        logger.info(f"Проверка IP-адреса включена, проверяем IP: {client_ip}")
        await verify_telegram_ip(request)
        logger.info(f"Проверка IP-адреса пройдена для: {client_ip}")
    
    # Проверка секретного токена (ОБЯЗАТЕЛЬНО)
    if not WEBHOOK_SECRET_TOKEN:
        logger.error("WEBHOOK_SECRET_TOKEN не настроен! Webhook небезопасен!")
        raise HTTPException(
            status_code=500,
            detail="Webhook secret token not configured"
        )
    
    if not x_telegram_bot_api_secret_token:
        logger.warning(f"Попытка доступа к webhook без токена от IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Missing secret token")
    
    # Убеждаемся, что токен - строка
    if not isinstance(x_telegram_bot_api_secret_token, str):
        logger.warning(f"Токен в заголовке имеет неверный тип от IP: {client_ip}")
        raise HTTPException(status_code=401, detail="Invalid token format")
    
    # Сравниваем токен из заголовка с сохраненным токеном
    # Используем secrets.compare_digest для защиты от timing attacks
    if not secrets.compare_digest(x_telegram_bot_api_secret_token, WEBHOOK_SECRET_TOKEN):
        logger.warning(
            f"Неверный секретный токен webhook от IP: {client_ip}, "
            f"получен токен: {x_telegram_bot_api_secret_token[:10] if len(x_telegram_bot_api_secret_token) > 10 else 'короткий'}..."
        )
        raise HTTPException(status_code=401, detail="Invalid secret token")
    
    # Токен верный - обрабатываем обновление
    if not bot_instance:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Получено обновление от IP {client_ip}, но bot_instance не установлен")
        return {"ok": False, "error": "Bot not initialized"}
    
    if not bot_instance.application:
        client_ip = request.client.host if request.client else "unknown"
        logger.warning(f"Получено обновление от IP {client_ip}, но application не инициализирован")
        return {"ok": False, "error": "Bot application not initialized"}
    
    try:
        body = await request.body()
        client_ip = request.client.host if request.client else "unknown"
        
        logger.info(f"Обработка webhook обновления от IP: {client_ip}, размер: {len(body)} байт")
        
        data = json.loads(body)
        
        # ЛОГ RAW UPDATE BODY
        logger.info(f"RAW UPDATE BODY: {data}")
        
        if not isinstance(data, dict):
            logger.error(f"Неверный формат обновления от IP {client_ip}")
            return {"ok": False, "error": "Invalid update format"}
        
        from telegram import Update
        update = Update.de_json(data, bot_instance.application.bot)
        
        # ЛОГ ПЕРЕД process_update
        logger.info(
            f"UPDATE PROCESSED: update_id={update.update_id}, "
            f"has_inline={bool(update.inline_query)}, "
            f"has_webapp={bool(update.web_app_query)}, "
            f"has_message={bool(update.message)}, "
            f"has_callback={bool(update.callback_query)}"
        )
        
        # КРИТИЧНО: Отправляем ответ сразу, обработку делаем в фоне через очередь
        # Это предотвращает таймауты Telegram (503 ошибки)
        # Telegram требует ответ в течение 60 секунд, но лучше ответить сразу
        try:
            # Ставим update в очередь для асинхронной обработки
            await bot_instance.application.update_queue.put(update)
            logger.info(
                f"Webhook обновление принято и поставлено в очередь от IP: {client_ip}, "
                f"update_id={update.update_id}"
            )
        except Exception as queue_error:
            logger.error(
                f"Ошибка при добавлении update в очередь от IP {client_ip}: {queue_error}",
                exc_info=True
            )
            # Если очередь недоступна, обрабатываем синхронно (но это нежелательно)
            await bot_instance.application.process_update(update)
            logger.warning(f"Update обработан синхронно из-за ошибки очереди")
        
        # Возвращаем ответ сразу (критично для предотвращения 503)
        return {"ok": True}
        
    except json.JSONDecodeError as e:
        client_ip = request.client.host if request.client else "unknown"
        logger.error(f"Ошибка парсинга JSON в webhook от IP {client_ip}: {e}")
        return {"ok": False, "error": "Invalid JSON"}
    except Exception as e:
        client_ip = request.client.host if request.client else "unknown"
        logger.error(
            f"Ошибка обработки webhook обновления от IP {client_ip}: {e}",
            exc_info=True
        )
        return {"ok": False, "error": str(e)}

