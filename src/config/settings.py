import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Определяем корень проекта (3 уровня выше от src/config/settings.py)
PROJECT_ROOT = Path(__file__).parent.parent.parent

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []

# Внешняя галерея стикеров
GALLERY_BASE_URL = os.getenv('GALLERY_BASE_URL')
GALLERY_SERVICE_TOKEN = os.getenv('GALLERY_SERVICE_TOKEN')
GALLERY_DEFAULT_LANGUAGE = os.getenv('GALLERY_DEFAULT_LANGUAGE', 'ru')
MINIAPP_GALLERY_URL = os.getenv('MINIAPP_GALLERY_URL')

# Логи
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'logs/bot.log')
# Создаем директорию для логов, если она не существует
_log_path = Path(LOG_FILE_PATH)
if not _log_path.is_absolute():
    _log_path = PROJECT_ROOT / _log_path
_log_dir = _log_path.parent
if _log_dir != PROJECT_ROOT:
    _log_dir.mkdir(parents=True, exist_ok=True)
# Обновляем LOG_FILE_PATH на абсолютный путь для использования в RotatingFileHandler
LOG_FILE_PATH = str(_log_path)

# Webhook и API настройки
SERVICE_BASE_URL = os.getenv('SERVICE_BASE_URL')
WEBHOOK_SECRET_TOKEN = os.getenv('WEBHOOK_SECRET_TOKEN')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')
WEBHOOK_RATE_LIMIT = os.getenv('WEBHOOK_RATE_LIMIT', '100/minute')
WEBHOOK_IP_CHECK_ENABLED = os.getenv('WEBHOOK_IP_CHECK_ENABLED', 'false').lower() == 'true'
API_TOKEN = os.getenv('API_TOKEN')
API_PORT = int(os.getenv('API_PORT', '80'))
CONFIG_PATH = os.getenv('CONFIG_PATH')

# WaveSpeed API для inline generation
WAVESPEED_API_KEY = os.getenv('WAVESPEED_API_KEY')
WAVESPEED_MAX_POLL_SECONDS = int(os.getenv('WAVESPEED_MAX_POLL_SECONDS', '30'))
WAVESPEED_INLINE_CACHE_TIME = int(os.getenv('WAVESPEED_INLINE_CACHE_TIME', '5'))
WAVESPEED_BG_REMOVE_ENABLED = os.getenv('WAVESPEED_BG_REMOVE_ENABLED', '1') == '1'

# Quota limits
FREE_DAILY_LIMIT = int(os.getenv('FREE_DAILY_LIMIT', '20'))
PREMIUM_DAILY_LIMIT = int(os.getenv('PREMIUM_DAILY_LIMIT', '200'))
FREE_MAX_PER_10MIN = int(os.getenv('FREE_MAX_PER_10MIN', '6'))
PREMIUM_MAX_PER_10MIN = int(os.getenv('PREMIUM_MAX_PER_10MIN', '30'))
COOLDOWN_SECONDS = float(os.getenv('COOLDOWN_SECONDS', '15.0'))
PREMIUM_USER_IDS = (
    set(map(int, os.getenv('PREMIUM_USER_IDS', '').split(',')))
    if os.getenv('PREMIUM_USER_IDS')
    else set()
)
QUOTA_TIMEZONE = os.getenv('QUOTA_TIMEZONE', 'UTC')

# Placeholder sticker для inline query
PLACEHOLDER_STICKER_FILE_ID = os.getenv('PLACEHOLDER_STICKER_FILE_ID')
# По умолчанию используем файл из static/ относительно корня проекта
_default_placeholder_path = str(PROJECT_ROOT / 'static' / 'stixly_ai.webp')
PLACEHOLDER_STICKER_PATH = os.getenv('PLACEHOLDER_STICKER_PATH', _default_placeholder_path)

# Sticker set cache settings
STICKERSET_CACHE_SIZE = int(os.getenv('STICKERSET_CACHE_SIZE', '5000'))
STICKERSET_CACHE_TTL_DAYS = int(os.getenv('STICKERSET_CACHE_TTL_DAYS', '7'))
STICKERSET_CACHE_CLEANUP_INTERVAL_HOURS = int(os.getenv('STICKERSET_CACHE_CLEANUP_INTERVAL_HOURS', '1'))

# Настройки поддержки
SUPPORT_CHAT_ID = os.getenv('SUPPORT_CHAT_ID')  # ID группы поддержки
SUPPORT_ENABLED = os.getenv('SUPPORT_ENABLED', 'true').lower() == 'true'
SUPPORT_USE_TOPICS = os.getenv('SUPPORT_USE_TOPICS', 'true').lower() == 'true'

