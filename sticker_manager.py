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

    def create_new_sticker_set(self, user_id: int, name: str, title: str,
                               png_sticker: bytes, emojis: str) -> bool:
        """Создает новый стикерсет"""
        try:
            url = f"{self.base_url}/createNewStickerSet"

            files = {
                'png_sticker': ('sticker.webp', png_sticker, 'image/webp')
            }

            data = {
                'user_id': user_id,
                'name': name,
                'title': title,
                'emojis': emojis
            }

            response = requests.post(url, data=data, files=files)
            result = response.json()

            if result.get('ok'):
                return True
            else:
                logger.error(f"Ошибка создания стикерсета: {result}")
                return False

        except Exception as e:
            logger.error(f"Ошибка при создании стикерсета: {e}")
            return False

    def add_sticker_to_set(self, user_id: int, name: str,
                           png_sticker: bytes, emojis: str) -> bool:
        """Добавляет стикер в существующий стикерсет"""
        try:
            url = f"{self.base_url}/addStickerToSet"

            files = {
                'png_sticker': ('sticker.webp', png_sticker, 'image/webp')
            }

            data = {
                'user_id': user_id,
                'name': name,
                'emojis': emojis
            }

            response = requests.post(url, data=data, files=files)
            result = response.json()

            return result.get('ok', False)

        except Exception as e:
            logger.error(f"Ошибка добавления стикера: {e}")
            return False