import requests
import json
import logging
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)


class StickerManager:
    def __init__(self, bot_token: str):
        self.bot_token = bot_token
        self.base_url = f"https://api.telegram.org/bot{bot_token}"

    def get_user_sticker_sets(self, user_id: int) -> List[Dict]:
        """Получает список стикерсетов пользователя"""
        try:
            url = f"{self.base_url}/getCustomEmojiStickers"
            # Это упрощенный вариант - в реальности нужно использовать getUserProfilePhotos
            # или хранить созданные стикерсеты в базе данных
            return []
        except Exception as e:
            logger.error(f"Ошибка получения стикерсетов: {e}")
            return []

    def is_sticker_set_available(self, name: str) -> Optional[bool]:
        """Проверяет, доступно ли короткое имя стикерсета"""
        try:
            url = f"{self.base_url}/getStickerSet"
            response = requests.get(url, params={'name': name}, timeout=10)
            result = response.json()

            if result.get('ok'):
                return False

            description = result.get('description', '')
            if 'STICKERSET_INVALID' in description.upper():
                return True

            return False
        except Exception as e:
            logger.error(f"Ошибка проверки имени стикерсета: {e}")
            return None

    def create_new_sticker_set(self, user_id: int, name: str, title: str,
                               png_sticker: bytes, emojis: str) -> Optional[Dict]:
        """Создает новый стикерсет и возвращает ответ API"""
        try:
            url = f"{self.base_url}/createNewStickerSet"

            files = {
                'png_sticker': ('sticker.png', png_sticker, 'image/png')
            }

            data = {
                'user_id': user_id,
                'name': name,
                'title': title,
                'emojis': emojis
            }

            response = requests.post(url, data=data, files=files, timeout=30)
            result = response.json()

            if result.get('ok'):
                return result
            else:
                logger.error(f"Ошибка создания стикерсета: {result}")
                return None

        except Exception as e:
            logger.error(f"Ошибка при создании стикерсета: {e}")
            return None

    def add_sticker_to_set(self, user_id: int, name: str,
                           png_sticker: bytes, emojis: str) -> bool:
        """Добавляет стикер в существующий стикерсет"""
        try:
            url = f"{self.base_url}/addStickerToSet"

            # Определяем MIME-тип по содержимому файла
            # WebP файлы начинаются с RIFF...WEBP
            if png_sticker.startswith(b'RIFF') and b'WEBP' in png_sticker[:12]:
                mime_type = 'image/webp'
                file_name = 'sticker.webp'
            else:
                mime_type = 'image/png'
                file_name = 'sticker.png'

            files = {
                'png_sticker': (file_name, png_sticker, mime_type)
            }

            data = {
                'user_id': user_id,
                'name': name,
                'emojis': emojis
            }

            logger.debug(f"Отправка запроса addStickerToSet: name={name}, user_id={user_id}, emojis={emojis}, file_size={len(png_sticker)}")

            response = requests.post(url, data=data, files=files, timeout=30)
            result = response.json()

            if not result.get('ok', False):
                logger.error(f"Ошибка добавления стикера в набор {name}: {result.get('description', 'Unknown error')}")
            else:
                logger.info(f"Стикер успешно добавлен в набор {name}")

            return result.get('ok', False)

        except Exception as e:
            logger.error(f"Ошибка добавления стикера: {e}", exc_info=True)
            return False

