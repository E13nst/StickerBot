"""Утилита для валидации Telegram WebApp initData"""
import hmac
import hashlib
import time
import logging
from typing import Dict, Optional
from urllib.parse import parse_qsl

logger = logging.getLogger(__name__)


class TelegramAuthError(Exception):
    """Ошибка валидации Telegram auth данных"""
    pass


def validate_telegram_init_data(
    init_data: str,
    bot_token: str,
    max_age_seconds: int = 3600
) -> Dict:
    """
    Валидация Telegram WebApp initData согласно официальной документации.
    
    Алгоритм валидации:
    1. Парсинг query string из initData
    2. Извлечение параметра hash
    3. Построение data_check_string (отсортированные пары key=value через \n)
    4. Создание secret_key: HMAC_SHA256(bot_token, "WebAppData")
    5. Создание hash: HMAC_SHA256(secret_key, data_check_string)
    6. Сравнение с переданным hash
    7. Проверка auth_date (не старше max_age_seconds)
    
    Args:
        init_data: Строка initData из Telegram.WebApp.initData
        bot_token: Токен бота
        max_age_seconds: Максимальный возраст данных в секундах (по умолчанию 1 час)
        
    Returns:
        Dict с распарсенными данными (user, auth_date и т.д.)
        
    Raises:
        TelegramAuthError: Если валидация не прошла
    """
    if not init_data:
        raise TelegramAuthError("initData is empty")
    
    if not bot_token:
        raise TelegramAuthError("bot_token is required")
    
    try:
        # Парсим query string
        parsed_data = dict(parse_qsl(init_data))
        
        if not parsed_data:
            raise TelegramAuthError("Failed to parse initData")
        
        # Извлекаем hash
        received_hash = parsed_data.pop('hash', None)
        if not received_hash:
            raise TelegramAuthError("Missing hash in initData")
        
        # Проверяем auth_date
        auth_date_str = parsed_data.get('auth_date')
        if not auth_date_str:
            raise TelegramAuthError("Missing auth_date in initData")
        
        try:
            auth_date = int(auth_date_str)
        except ValueError:
            raise TelegramAuthError("Invalid auth_date format")
        
        # Проверяем возраст данных
        current_time = int(time.time())
        if current_time - auth_date > max_age_seconds:
            age = current_time - auth_date
            raise TelegramAuthError(
                f"initData is too old: {age} seconds (max: {max_age_seconds})"
            )
        
        # Строим data_check_string (отсортированные пары key=value через \n)
        data_check_pairs = [f"{key}={value}" for key, value in sorted(parsed_data.items())]
        data_check_string = '\n'.join(data_check_pairs)
        
        # Создаем secret_key: HMAC-SHA256(bot_token, "WebAppData")
        secret_key = hmac.new(
            key="WebAppData".encode(),
            msg=bot_token.encode(),
            digestmod=hashlib.sha256
        ).digest()
        
        # Создаем hash: HMAC-SHA256(secret_key, data_check_string)
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()
        
        # Сравниваем хеши (используем hmac.compare_digest для защиты от timing attacks)
        if not hmac.compare_digest(calculated_hash, received_hash):
            logger.warning(
                f"Hash mismatch: received={received_hash[:20]}..., "
                f"calculated={calculated_hash[:20]}..."
            )
            raise TelegramAuthError("Hash validation failed")
        
        # Парсим user данные если есть
        user_json = parsed_data.get('user')
        if user_json:
            import json
            try:
                parsed_data['user'] = json.loads(user_json)
            except json.JSONDecodeError:
                logger.warning(f"Failed to parse user JSON: {user_json[:100]}")
        
        logger.info(
            f"initData validated successfully: "
            f"auth_date={auth_date}, age={current_time - auth_date}s"
        )
        
        return parsed_data
        
    except TelegramAuthError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error validating initData: {e}", exc_info=True)
        raise TelegramAuthError(f"Validation error: {str(e)}")


def extract_user_id(validated_data: Dict) -> Optional[int]:
    """
    Извлекает user_id из валидированных данных.
    
    Args:
        validated_data: Результат validate_telegram_init_data()
        
    Returns:
        user_id или None если не найден
    """
    user = validated_data.get('user')
    if isinstance(user, dict):
        user_id = user.get('id')
        if user_id is not None:
            try:
                return int(user_id)
            except (ValueError, TypeError):
                pass
    return None
