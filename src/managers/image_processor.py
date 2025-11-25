from PIL import Image, ImageOps
import io
import logging

from src.utils.constants import STICKER_SIZE, STICKER_MAX_SIZE, WEBP_QUALITY

logger = logging.getLogger(__name__)


class ImageProcessor:
    @staticmethod
    def convert_to_webp(image_data, target_size=STICKER_SIZE, quality=WEBP_QUALITY):
        """Конвертирует изображение в WebP по требованиям Telegram"""
        try:
            # Открываем изображение
            image = Image.open(io.BytesIO(image_data))

            # Конвертируем в RGB если нужно
            if image.mode in ('RGBA', 'LA', 'P'):
                # Создаем белый фон для прозрачных изображений
                background = Image.new('RGB', image.size, (255, 255, 255))
                if image.mode == 'P':
                    image = image.convert('RGBA')
                background.paste(image, mask=image.split()[-1] if image.mode == 'RGBA' else None)
                image = background
            elif image.mode != 'RGB':
                image = image.convert('RGB')

            # Изменяем размер с сохранением пропорций
            image.thumbnail(target_size, Image.Resampling.LANCZOS)

            # Создаем квадратное изображение
            if image.size != target_size:
                delta_w = target_size[0] - image.size[0]
                delta_h = target_size[1] - image.size[1]
                padding = (delta_w // 2, delta_h // 2, delta_w - (delta_w // 2), delta_h - (delta_h // 2))
                image = ImageOps.expand(image, padding, (255, 255, 255))

            # Сохраняем в WebP
            output = io.BytesIO()
            image.save(output, format='WEBP', quality=quality, method=6)
            webp_data = output.getvalue()

            # Проверяем размер
            if len(webp_data) > STICKER_MAX_SIZE:
                # Пробуем уменьшить качество
                output = io.BytesIO()
                image.save(output, format='WEBP', quality=70, method=6)
                webp_data = output.getvalue()

                if len(webp_data) > STICKER_MAX_SIZE:
                    raise ValueError(f"Размер файла слишком большой: {len(webp_data)} байт")

            return webp_data

        except Exception as e:
            logger.error(f"Ошибка конвертации: {e}")
            raise

