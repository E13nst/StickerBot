from PIL import Image, ImageOps
import io
import logging

from src.utils.constants import STICKER_SIZE, STICKER_MAX_SIZE, WEBP_QUALITY

logger = logging.getLogger(__name__)


class ImageProcessor:
    @staticmethod
    def convert_to_webp(image_data, target_size=STICKER_SIZE, quality=WEBP_QUALITY):
        """Конвертирует изображение в WebP по требованиям Telegram с сохранением альфа-канала"""
        try:
            # Открываем изображение
            image = Image.open(io.BytesIO(image_data))

            # Определяем, есть ли альфа-канал в исходном изображении
            has_alpha = image.mode in ('RGBA', 'LA') or (image.mode == 'P' and 'transparency' in image.info)

            # Конвертируем в RGBA для сохранения прозрачности, если она есть
            if has_alpha:
                if image.mode == 'P':
                    image = image.convert('RGBA')
                elif image.mode == 'LA':
                    # LA -> RGBA
                    image = image.convert('RGBA')
                elif image.mode != 'RGBA':
                    image = image.convert('RGBA')
            else:
                # Если альфа-канала нет, конвертируем в RGB
                if image.mode != 'RGB':
                    image = image.convert('RGB')

            # Изменяем размер с сохранением пропорций
            image.thumbnail(target_size, Image.Resampling.LANCZOS)

            # Создаем квадратное изображение
            if image.size != target_size:
                delta_w = target_size[0] - image.size[0]
                delta_h = target_size[1] - image.size[1]
                padding = (delta_w // 2, delta_h // 2, delta_w - (delta_w // 2), delta_h - (delta_h // 2))
                
                # Используем прозрачный фон для RGBA, белый для RGB
                if image.mode == 'RGBA':
                    fill_color = (0, 0, 0, 0)  # Прозрачный фон
                else:
                    fill_color = (255, 255, 255)  # Белый фон для RGB
                
                image = ImageOps.expand(image, padding, fill_color)

            # Сохраняем в WebP с сохранением альфа-канала
            output = io.BytesIO()
            save_kwargs = {
                'format': 'WEBP',
                'method': 6,
            }
            
            if image.mode == 'RGBA':
                # Для RGBA используем lossy с качеством для сохранения альфа-канала
                save_kwargs['quality'] = quality
                save_kwargs['lossless'] = False
            else:
                # Для RGB используем обычное сжатие
                save_kwargs['quality'] = quality
                save_kwargs['lossless'] = False
            
            image.save(output, **save_kwargs)
            webp_data = output.getvalue()

            # Проверяем размер
            if len(webp_data) > STICKER_MAX_SIZE:
                # Пробуем уменьшить качество
                output = io.BytesIO()
                if image.mode == 'RGBA':
                    # Для RGBA пробуем уменьшить качество
                    save_kwargs['quality'] = 70
                    save_kwargs['lossless'] = False
                else:
                    save_kwargs['quality'] = 70
                
                image.save(output, **save_kwargs)
                webp_data = output.getvalue()

                if len(webp_data) > STICKER_MAX_SIZE:
                    # Последняя попытка: lossless для RGBA (может быть меньше для простых изображений)
                    if image.mode == 'RGBA':
                        output = io.BytesIO()
                        image.save(output, format='WEBP', lossless=True, method=6)
                        webp_data = output.getvalue()
                    
                    if len(webp_data) > STICKER_MAX_SIZE:
                        raise ValueError(f"Размер файла слишком большой: {len(webp_data)} байт")

            return webp_data

        except Exception as e:
            logger.error(f"Ошибка конвертации: {e}")
            raise

