import logging
from typing import Tuple

from src.managers.image_processor import ImageProcessor
from src.utils.constants import STICKER_SIZE, WEBP_QUALITY

logger = logging.getLogger(__name__)


class ImageService:
    """Сервис для обработки изображений"""
    
    def __init__(self):
        self.processor = ImageProcessor()
    
    def convert_to_webp(
        self,
        image_data: bytes,
        target_size: Tuple[int, int] = STICKER_SIZE,
        quality: int = WEBP_QUALITY
    ) -> bytes:
        """Конвертирует изображение в WebP по требованиям Telegram"""
        return self.processor.convert_to_webp(
            image_data=image_data,
            target_size=target_size,
            quality=quality
        )

