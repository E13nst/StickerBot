"""Утилиты для постобработки изображений"""
import io
import logging
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)


def create_placeholder_image(size: tuple = (512, 512), text: str = "Generating...") -> bytes:
    """
    Создать placeholder изображение для отображения во время генерации
    
    Args:
        size: Размер изображения (по умолчанию 512x512)
        text: Текст для отображения
        
    Returns:
        Байты PNG изображения
    """
    try:
        # Создаем изображение с прозрачным фоном
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        draw = ImageDraw.Draw(img)
        
        # Пробуем использовать системный шрифт, fallback на default
        try:
            # Пробуем найти шрифт (для разных ОС)
            font_size = 40
            try:
                # Windows
                font = ImageFont.truetype("arial.ttf", font_size)
            except:
                try:
                    # Linux
                    font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", font_size)
                except:
                    # macOS или fallback
                    font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", font_size)
        except:
            # Используем default font
            font = ImageFont.load_default()
        
        # Рисуем текст по центру
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        position = ((size[0] - text_width) // 2, (size[1] - text_height) // 2)
        
        # Рисуем текст (белый с небольшой прозрачностью)
        draw.text(position, text, fill=(255, 255, 255, 200), font=font)
        
        # Сохраняем в PNG
        output = io.BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()
        
    except Exception as e:
        logger.error(f"Error creating placeholder image: {e}", exc_info=True)
        # Fallback: простое прозрачное изображение
        img = Image.new("RGBA", size, (0, 0, 0, 0))
        output = io.BytesIO()
        img.save(output, format="PNG")
        return output.getvalue()


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

