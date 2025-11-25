#!/usr/bin/env python3
"""
Скрипт для генерации тестовых стикерсетов
Использование: python generate_test_stickersets.py <prefix> <count> <user_id>
Пример: python generate_test_stickersets.py test_set 5 123456789
"""

import sys
import argparse
import logging
import requests
from PIL import Image, ImageDraw, ImageFont
import io
from sticker_manager import StickerManager
from image_processor import ImageProcessor
from config import BOT_TOKEN

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def get_bot_username(bot_token: str) -> str:
    """Получает username бота через API"""
    try:
        url = f"https://api.telegram.org/bot{bot_token}/getMe"
        response = requests.get(url, timeout=10)
        result = response.json()
        
        if result.get('ok'):
            return result['result']['username']
        else:
            logger.error(f"Не удалось получить информацию о боте: {result}")
            return None
    except Exception as e:
        logger.error(f"Ошибка при получении username бота: {e}")
        return None


def generate_test_image(sticker_number: int, set_number: int) -> bytes:
    """Генерирует простое тестовое изображение для стикера"""
    # Создаем изображение 512x512
    img = Image.new('RGB', (512, 512), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)
    
    # Рисуем простой узор
    colors = [
        (255, 100, 100),  # Красный
        (100, 255, 100),  # Зеленый
        (100, 100, 255),  # Синий
        (255, 255, 100),  # Желтый
        (255, 100, 255),  # Пурпурный
    ]
    
    color = colors[sticker_number % len(colors)]
    
    # Рисуем круг
    margin = 50
    draw.ellipse(
        [margin, margin, 512 - margin, 512 - margin],
        fill=color,
        outline=(0, 0, 0),
        width=5
    )
    
    # Добавляем текст
    try:
        # Пробуем использовать системный шрифт
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 60)
    except:
        try:
            font = ImageFont.truetype("arial.ttf", 60)
        except:
            font = ImageFont.load_default()
    
    text = f"S{set_number}\n#{sticker_number}"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    
    position = ((512 - text_width) // 2, (512 - text_height) // 2)
    draw.text(position, text, fill=(255, 255, 255), font=font, stroke_width=2, stroke_fill=(0, 0, 0))
    
    # Сохраняем в байты
    img_bytes = io.BytesIO()
    img.save(img_bytes, format='PNG')
    return img_bytes.getvalue()


def create_test_stickerset(
    sticker_manager: StickerManager,
    image_processor: ImageProcessor,
    user_id: int,
    prefix: str,
    set_number: int,
    bot_username: str,
    stickers_per_set: int = 3
) -> bool:
    """Создает один тестовый стикерсет"""
    short_name = f"{prefix}_{set_number:03d}"
    full_name = f"{short_name}_by_{bot_username}"
    title = f"Test Stickerset {set_number}"
    
    # Проверяем доступность имени
    logger.info(f"Проверяем доступность имени: {full_name}")
    is_available = sticker_manager.is_sticker_set_available(full_name)
    
    if is_available is None:
        logger.error(f"Не удалось проверить доступность имени {full_name}")
        return False
    
    if not is_available:
        logger.warning(f"Имя {full_name} уже занято, пропускаем")
        return False
    
    # Генерируем первый стикер
    logger.info(f"Создаем стикерсет {full_name}...")
    first_image = generate_test_image(1, set_number)
    webp_data = image_processor.convert_to_webp(first_image)
    
    # Создаем стикерсет с первым стикером
    result = sticker_manager.create_new_sticker_set(
        user_id=user_id,
        name=full_name,
        title=title,
        png_sticker=webp_data,
        emojis="😀"
    )
    
    if not result:
        logger.error(f"Не удалось создать стикерсет {full_name}")
        return False
    
    logger.info(f"✅ Стикерсет {full_name} создан")
    
    # Добавляем остальные стикеры
    for i in range(2, stickers_per_set + 1):
        logger.info(f"  Добавляем стикер {i}/{stickers_per_set}...")
        image = generate_test_image(i, set_number)
        webp_data = image_processor.convert_to_webp(image)
        
        emojis = ["😀", "😃", "😄", "😁", "😆"][(i - 1) % 5]
        
        success = sticker_manager.add_sticker_to_set(
            user_id=user_id,
            name=full_name,
            png_sticker=webp_data,
            emojis=emojis
        )
        
        if success:
            logger.info(f"  ✅ Стикер {i} добавлен")
        else:
            logger.warning(f"  ⚠️ Не удалось добавить стикер {i}")
    
    logger.info(f"🎉 Стикерсет {full_name} готов! Ссылка: https://t.me/addstickers/{full_name}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description='Генерация тестовых стикерсетов для Telegram бота'
    )
    parser.add_argument(
        'prefix',
        type=str,
        help='Префикс названия стикерсета (например: test_set)'
    )
    parser.add_argument(
        'count',
        type=int,
        help='Количество стикерсетов для создания'
    )
    parser.add_argument(
        'user_id',
        type=int,
        help='Telegram User ID владельца стикерсетов'
    )
    parser.add_argument(
        '--stickers-per-set',
        type=int,
        default=3,
        help='Количество стикеров в каждом стикерсете (по умолчанию: 3)'
    )
    
    args = parser.parse_args()
    
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не установлен в переменных окружения!")
        sys.exit(1)
    
    if not args.prefix or len(args.prefix) < 3:
        logger.error("Префикс должен содержать минимум 3 символа")
        sys.exit(1)
    
    if args.count < 1:
        logger.error("Количество стикерсетов должно быть больше 0")
        sys.exit(1)
    
    logger.info(f"Начинаем создание {args.count} тестовых стикерсетов с префиксом '{args.prefix}'")
    logger.info(f"User ID: {args.user_id}")
    logger.info(f"Стикеров в каждом наборе: {args.stickers_per_set}")
    
    # Получаем username бота
    logger.info("Получаем информацию о боте...")
    bot_username = get_bot_username(BOT_TOKEN)
    if not bot_username:
        logger.error("Не удалось получить username бота. Проверьте BOT_TOKEN.")
        sys.exit(1)
    logger.info(f"Bot username: @{bot_username}")
    
    sticker_manager = StickerManager(BOT_TOKEN)
    image_processor = ImageProcessor()
    
    created = 0
    failed = 0
    
    for i in range(1, args.count + 1):
        logger.info(f"\n--- Создание стикерсета {i}/{args.count} ---")
        try:
            success = create_test_stickerset(
                sticker_manager,
                image_processor,
                args.user_id,
                args.prefix,
                i,
                bot_username,
                args.stickers_per_set
            )
            if success:
                created += 1
            else:
                failed += 1
        except Exception as e:
            logger.error(f"Ошибка при создании стикерсета {i}: {e}", exc_info=True)
            failed += 1
    
    logger.info(f"\n{'='*50}")
    logger.info(f"Готово! Создано: {created}, Ошибок: {failed}")
    logger.info(f"{'='*50}")


if __name__ == '__main__':
    main()

