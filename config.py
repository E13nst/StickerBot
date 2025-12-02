import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')
ADMIN_IDS = list(map(int, os.getenv('ADMIN_IDS', '').split(','))) if os.getenv('ADMIN_IDS') else []

# Внешняя галерея стикеров
GALLERY_BASE_URL = os.getenv('GALLERY_BASE_URL')
GALLERY_SERVICE_TOKEN = os.getenv('GALLERY_SERVICE_TOKEN')
GALLERY_DEFAULT_LANGUAGE = os.getenv('GALLERY_DEFAULT_LANGUAGE', 'ru')

# Логи
LOG_FILE_PATH = os.getenv('LOG_FILE_PATH', 'bot.log')

# Требования Telegram для стикеров
STICKER_SIZE = (512, 512)
STICKER_MAX_SIZE = 512 * 1024  # 512KB
WEBP_QUALITY = 85

# Webhook и API настройки
SERVICE_BASE_URL = os.getenv('SERVICE_BASE_URL')
WEBHOOK_PATH = os.getenv('WEBHOOK_PATH', '/webhook')
API_TOKEN = os.getenv('API_TOKEN')
API_PORT = int(os.getenv('API_PORT', '80'))
CONFIG_PATH = os.getenv('CONFIG_PATH')