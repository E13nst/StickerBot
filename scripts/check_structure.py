#!/usr/bin/env python3
"""
Скрипт для проверки структуры проекта после рефакторинга
"""

import sys
import os

# Добавляем корневую директорию в путь
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def check_imports():
    """Проверка всех основных импортов"""
    errors = []
    
    try:
        from src.bot.bot import StickerBot
        print("✅ StickerBot импортирован")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта StickerBot: {e}")
    
    try:
        from src.api.server import app
        print("✅ API сервер импортирован")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта API сервера: {e}")
    
    try:
        from src.config.settings import BOT_TOKEN, GALLERY_BASE_URL
        from src.config.manager import ConfigManager
        print("✅ Конфигурация импортирована")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта конфигурации: {e}")
    
    try:
        from src.services.sticker_service import StickerService
        from src.services.image_service import ImageService
        from src.services.gallery_service import GalleryService
        print("✅ Сервисы импортированы")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта сервисов: {e}")
    
    try:
        from src.managers.sticker_manager import StickerManager
        from src.managers.image_processor import ImageProcessor
        from src.managers.gallery_client import GalleryClient
        print("✅ Менеджеры импортированы")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта менеджеров: {e}")
    
    try:
        from src.bot.handlers.start import start
        from src.bot.handlers.create_set import create_new_set
        from src.bot.handlers.add_existing import add_to_existing
        from src.bot.handlers.manage_pub import manage_publication
        from src.bot.handlers.common import cancel, error_handler
        print("✅ Обработчики импортированы")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта обработчиков: {e}")
    
    try:
        from src.bot.states import CHOOSING_ACTION, WAITING_STICKER
        print("✅ Состояния импортированы")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта состояний: {e}")
    
    try:
        from src.utils.constants import STICKER_SIZE, STICKER_MAX_SIZE
        print("✅ Константы импортированы")
    except Exception as e:
        errors.append(f"❌ Ошибка импорта констант: {e}")
    
    if errors:
        print("\n❌ Обнаружены ошибки:")
        for error in errors:
            print(f"  {error}")
        return False
    else:
        print("\n✅ Все импорты успешны!")
        return True


def check_structure():
    """Проверка структуры директорий"""
    required_dirs = [
        'src',
        'src/bot',
        'src/bot/handlers',
        'src/services',
        'src/managers',
        'src/api',
        'src/api/routes',
        'src/config',
        'src/utils',
        'scripts',
        'data',
    ]
    
    missing = []
    for dir_path in required_dirs:
        if not os.path.exists(dir_path):
            missing.append(dir_path)
    
    if missing:
        print("❌ Отсутствуют директории:")
        for dir_path in missing:
            print(f"  - {dir_path}")
        return False
    else:
        print("✅ Структура директорий корректна")
        return True


if __name__ == '__main__':
    print("Проверка структуры проекта...\n")
    
    structure_ok = check_structure()
    print()
    imports_ok = check_imports()
    
    if structure_ok and imports_ok:
        print("\n🎉 Все проверки пройдены успешно!")
        sys.exit(0)
    else:
        print("\n❌ Обнаружены проблемы")
        sys.exit(1)

