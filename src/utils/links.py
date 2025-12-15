"""
Утилиты для работы со ссылками, включая deep links для MiniApp
"""
import base64


def create_miniapp_deeplink(bot_username: str, web_app_url: str) -> str:
    """
    Создает deep link для открытия MiniApp из текстовой ссылки в Telegram.
    
    Формат: https://t.me/{bot_username}?startapp={base64url_encoded_url}
    
    Параметр startapp может содержать только символы A-Z, a-z, 0-9, _ и -.
    Поэтому URL кодируется в base64url формате.
    
    При клике на такую ссылку в личном чате Telegram откроет MiniApp напрямую,
    минуя встроенный браузер. Параметр будет доступен в MiniApp через window.Telegram.WebApp.startParam.
    
    Args:
        bot_username: Имя бота без символа @ (например, "mybot")
        web_app_url: URL MiniApp (например, "https://example.com/miniapp?param=value")
    
    Returns:
        Deep link строка для открытия MiniApp
        
    Example:
        >>> create_miniapp_deeplink("mybot", "https://example.com/miniapp?set_id=123")
        'https://t.me/mybot?startapp=aHR0cHM6Ly9leGFtcGxlLmNvbS9taW5pYXBwP3NldF9pZD0xMjM'
    """
    # Кодируем URL в base64url (base64 с заменой + на -, / на _, и удалением =)
    encoded_bytes = base64.urlsafe_b64encode(web_app_url.encode('utf-8'))
    encoded_str = encoded_bytes.decode('ascii').rstrip('=')
    return f"https://t.me/{bot_username}?startapp={encoded_str}"


def decode_miniapp_start_param(start_param: str) -> str:
    """
    Декодирует параметр startapp из base64url обратно в URL.
    
    Args:
        start_param: Закодированный параметр из startapp
        
    Returns:
        Декодированный URL
        
    Example:
        >>> decode_miniapp_start_param("aHR0cHM6Ly9leGFtcGxlLmNvbS9taW5pYXBwP3NldF9pZD0xMjM")
        'https://example.com/miniapp?set_id=123'
    """
    # Добавляем padding если нужно
    padding = 4 - len(start_param) % 4
    if padding != 4:
        start_param += '=' * padding
    
    decoded_bytes = base64.urlsafe_b64decode(start_param.encode('ascii'))
    return decoded_bytes.decode('utf-8')


def create_miniapp_deeplink_simple(bot_username: str, params: str) -> str:
    """
    Создает deep link для открытия MiniApp с простыми параметрами.
    
    Используется когда нужно передать только параметры (например, set_id=2326),
    а не полный URL. Параметры должны содержать только разрешенные символы
    (A-Z, a-z, 0-9, _, -) или быть закодированы в base64url.
    
    Формат: https://t.me/{bot_username}?startapp={params}
    
    Args:
        bot_username: Имя бота без символа @ (например, "mybot")
        params: Параметры для передачи в MiniApp (например, "set_id=2326" или "2326")
                Если параметры содержат недопустимые символы, они будут закодированы в base64url
    
    Returns:
        Deep link строка для открытия MiniApp
        
    Example:
        >>> create_miniapp_deeplink_simple("mybot", "set_id=2326")
        'https://t.me/mybot?startapp=set_id=2326'
        >>> create_miniapp_deeplink_simple("mybot", "2326")
        'https://t.me/mybot?startapp=2326'
    """
    # Проверяем, содержат ли параметры только разрешенные символы
    allowed_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_-=')
    if all(c in allowed_chars for c in params):
        # Параметры уже в правильном формате
        return f"https://t.me/{bot_username}?startapp={params}"
    else:
        # Кодируем в base64url если есть недопустимые символы
        encoded_bytes = base64.urlsafe_b64encode(params.encode('utf-8'))
        encoded_str = encoded_bytes.decode('ascii').rstrip('=')
        return f"https://t.me/{bot_username}?startapp={encoded_str}"

