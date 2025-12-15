"""Утилиты для постобработки изображений"""
import io
import logging
from typing import Optional
from PIL import Image

logger = logging.getLogger(__name__)


def validate_alpha_channel(image_bytes: bytes) -> bool:
    """
    Проверить наличие альфа-канала в изображении
    
    Args:
        image_bytes: Байты изображения
        
    Returns:
        True если есть альфа-канал (RGBA, LA или transparency в palette)
    """
    try:
        img = Image.open(io.BytesIO(image_bytes))
        
        # Проверяем режим изображения
        if img.mode in ("RGBA", "LA"):
            return True
        
        # Для palette изображений проверяем transparency
        if img.mode == "P" and img.info.get("transparency") is not None:
            return True
        
        return False
    except Exception as e:
        logger.warning(f"Error validating alpha channel: {e}")
        return False


def convert_to_webp_rgba(image_bytes: bytes) -> bytes:
    """
    Конвертировать изображение в WebP с сохранением альфа-канала
    
    Args:
        image_bytes: Байты исходного изображения
        
    Returns:
        Байты WebP изображения
        
    Raises:
        Exception при ошибке конвертации
    """
    try:
        # Открываем изображение
        img = Image.open(io.BytesIO(image_bytes))
        
        # Конвертируем в RGBA для гарантии наличия альфа-канала
        if img.mode != "RGBA":
            img = img.convert("RGBA")
        
        # Сохраняем в WebP с lossless сжатием и сохранением альфа
        output = io.BytesIO()
        img.save(
            output,
            format="WEBP",
            lossless=True,
            method=6,
        )
        
        webp_bytes = output.getvalue()
        logger.debug(f"Converted image to WebP: {len(image_bytes)} -> {len(webp_bytes)} bytes")
        return webp_bytes
        
    except Exception as e:
        logger.error(f"Error converting to WebP: {e}", exc_info=True)
        raise

