"""Rate limiting middleware для защиты от DoS атак"""
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Создаем экземпляр limiter для использования в приложении
limiter = Limiter(key_func=get_remote_address)

__all__ = ['limiter', '_rate_limit_exceeded_handler', 'RateLimitExceeded']

