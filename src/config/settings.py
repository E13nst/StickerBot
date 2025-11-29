import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []

# Внешняя галерея стикеров
GALLERY_BASE_URL = os.getenv('GALLERY_BASE_URL')
GALLERY_SERVICE_TOKEN = os.getenv('GALLERY_SERVICE_TOKEN')
GALLERY_DEFAULT_LANGUAGE = os.getenv('GALLERY_DEFAULT_LANGUAGE', 'ru')
MINIAPP_GALLERY_URL = os.getenv('MINIAPP_GALLERY_URL')

# Логи
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'bot.log')

# Webhook и API настройки
SERVICE_BASE_URL = os.getenv('SERVICE_BASE_URL')
WEBHOOK_SECRET_TOKEN = os.getenv('WEBHOOK_SECRET_TOKEN')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')
WEBHOOK_RATE_LIMIT = os.getenv('WEBHOOK_RATE_LIMIT', '100/minute')
WEBHOOK_IP_CHECK_ENABLED = os.getenv('WEBHOOK_IP_CHECK_ENABLED', 'false').lower() == 'true'
API_TOKEN = os.getenv('API_TOKEN')
API_PORT = int(os.getenv('API_PORT', '80'))
CONFIG_PATH = os.getenv('CONFIG_PATH')

