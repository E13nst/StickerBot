"""Middleware для проверки IP-адресов Telegram"""
import ipaddress
import logging
from fastapi import HTTPException, Request, Depends

logger = logging.getLogger(__name__)

# Официальные IP-диапазоны Telegram
# Актуальный список: https://core.telegram.org/bots/webhooks#the-short-version
TELEGRAM_IP_RANGES = [
    "149.154.160.0/20",  # Основной диапазон
    "91.108.4.0/22",     # Дополнительный диапазон
]


def is_telegram_ip(ip: str) -> bool:
    """
    Проверяет, принадлежит ли IP-адрес диапазонам Telegram
    
    Args:
        ip: IP-адрес для проверки
        
    Returns:
        True если IP принадлежит Telegram, False иначе
    """
    try:
        ip_obj = ipaddress.ip_address(ip)
        for ip_range in TELEGRAM_IP_RANGES:
            if ip_obj in ipaddress.ip_network(ip_range, strict=False):
                return True
        return False
    except ValueError:
        logger.warning(f"Неверный формат IP-адреса: {ip}")
        return False


async def verify_telegram_ip(request: Request) -> bool:
    """
    Dependency функция для проверки IP-адреса Telegram
    
    Проверяет, что запрос приходит с IP-адреса Telegram.
    Если IP не из Telegram, выбрасывает HTTPException(403).
    
    Args:
        request: FastAPI Request объект
        
    Returns:
        True если IP валиден
        
    Raises:
        HTTPException: 403 если IP не из Telegram
    """
    client_ip = request.client.host if request.client else None
    
    if not client_ip:
        logger.warning("Не удалось определить IP-адрес клиента")
        raise HTTPException(status_code=403, detail="Unable to determine client IP")
    
    if not is_telegram_ip(client_ip):
        logger.warning(f"Запрос к webhook от неавторизованного IP: {client_ip}")
        raise HTTPException(
            status_code=403, 
            detail="Forbidden: IP not from Telegram"
        )
    
    return True

