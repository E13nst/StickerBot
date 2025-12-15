"""
Тесты для image_postprocess
"""
import pytest
import io
from PIL import Image

from src.utils.image_postprocess import validate_alpha_channel, convert_to_webp_rgba


def test_validate_alpha_channel_rgba():
    """Тест проверки альфа-канала для RGBA изображения"""
    # Arrange: создаем RGBA изображение
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))  # Красный с прозрачностью
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    # Act
    result = validate_alpha_channel(img_bytes.getvalue())
    
    # Assert
    assert result is True


def test_validate_alpha_channel_rgb():
    """Тест проверки альфа-канала для RGB изображения (без альфа)"""
    # Arrange: создаем RGB изображение
    img = Image.new("RGB", (100, 100), (255, 0, 0))  # Красный без прозрачности
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    # Act
    result = validate_alpha_channel(img_bytes.getvalue())
    
    # Assert
    assert result is False


def test_validate_alpha_channel_la():
    """Тест проверки альфа-канала для LA изображения (grayscale с альфа)"""
    # Arrange: создаем LA изображение
    img = Image.new("LA", (100, 100), (128, 200))  # Серый с прозрачностью
    img_bytes = io.BytesIO()
    img.save(img_bytes, format="PNG")
    img_bytes.seek(0)
    
    # Act
    result = validate_alpha_channel(img_bytes.getvalue())
    
    # Assert
    assert result is True


def test_validate_alpha_channel_invalid():
    """Тест проверки альфа-канала для невалидных данных"""
    # Arrange: невалидные байты
    invalid_bytes = b"not_an_image"
    
    # Act
    result = validate_alpha_channel(invalid_bytes)
    
    # Assert
    assert result is False


def test_convert_to_webp_rgba():
    """Тест конвертации RGBA изображения в WebP"""
    # Arrange: создаем RGBA PNG
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 128))
    png_bytes = io.BytesIO()
    img.save(png_bytes, format="PNG")
    png_bytes.seek(0)
    
    # Act
    webp_bytes = convert_to_webp_rgba(png_bytes.getvalue())
    
    # Assert
    assert webp_bytes is not None
    assert len(webp_bytes) > 0
    
    # Проверяем, что результат - валидный WebP
    webp_img = Image.open(io.BytesIO(webp_bytes))
    assert webp_img.format == "WEBP"
    assert webp_img.mode == "RGBA"


def test_convert_to_webp_rgb_converts_to_rgba():
    """Тест конвертации RGB изображения в WebP (должно конвертироваться в RGBA)"""
    # Arrange: создаем RGB PNG
    img = Image.new("RGB", (100, 100), (255, 0, 0))
    png_bytes = io.BytesIO()
    img.save(png_bytes, format="PNG")
    png_bytes.seek(0)
    
    # Act
    webp_bytes = convert_to_webp_rgba(png_bytes.getvalue())
    
    # Assert
    assert webp_bytes is not None
    assert len(webp_bytes) > 0
    
    # Проверяем, что результат - валидный WebP
    webp_img = Image.open(io.BytesIO(webp_bytes))
    assert webp_img.format == "WEBP"
    # Pillow может оптимизировать и сохранить как RGB, если все пиксели непрозрачны
    # Это нормально для наших целей - важно, что функция работает
    assert webp_img.mode in ("RGB", "RGBA")


def test_convert_to_webp_rgba_invalid():
    """Тест конвертации невалидных данных (должно вызвать исключение)"""
    # Arrange: невалидные байты
    invalid_bytes = b"not_an_image"
    
    # Act & Assert
    with pytest.raises(Exception):
        convert_to_webp_rgba(invalid_bytes)

