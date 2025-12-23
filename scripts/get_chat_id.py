"""
Скрипт для получения chat_id группы/чата
Использование:
1. Добавьте бота в группу
2. Отправьте любое сообщение в группу
3. Запустите этот скрипт: python scripts/get_chat_id.py
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from telegram import Bot

# Загружаем переменные окружения
load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print("ОШИБКА: BOT_TOKEN не найден в переменных окружения!")
    print("Убедитесь, что файл .env существует и содержит BOT_TOKEN")
    sys.exit(1)


async def get_chat_ids():
    """Получить все chat_id из последних обновлений"""
    bot = Bot(token=BOT_TOKEN)
    
    print("Проверяю webhook...")
    
    try:
        # Проверяем и удаляем webhook, если он активен
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            print(f"Найден активный webhook: {webhook_info.url}")
            print("Удаляю webhook для получения обновлений...")
            await bot.delete_webhook(drop_pending_updates=True)
            print("Webhook удален")
        
        print("\nПолучаю последние обновления...")
        
        # Получаем последние обновления
        updates = await bot.get_updates(limit=10)
        
        if not updates:
            print("Нет обновлений. Убедитесь, что:")
            print("   1. Бот добавлен в группу")
            print("   2. В группу отправлено хотя бы одно сообщение")
            print("   3. Бот имеет права на чтение сообщений")
            return
        
        print("\nНайденные чаты:\n")
        
        seen_chats = set()
        
        for update in updates:
            if update.message:
                chat = update.message.chat
                chat_id = chat.id
                
                if chat_id not in seen_chats:
                    seen_chats.add(chat_id)
                    
                    chat_type = chat.type
                    chat_title = chat.title or "Личные сообщения"
                    chat_username = chat.username or "нет"
                    
                    print(f"  {chat_title}")
                    print(f"     Тип: {chat_type}")
                    print(f"     Chat ID: {chat_id}")
                    print(f"     Username: @{chat_username}")
                    
                    if chat_type in ['group', 'supergroup']:
                        print(f"     [ГРУППА] Используйте этот ID в SUPPORT_CHAT_ID")
                    
                    print()
        
        if not seen_chats:
            print("Не найдено чатов в обновлениях")
        
    except Exception as e:
        print(f"Ошибка при получении обновлений: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    import sys
    import io
    
    # Настройка кодировки для Windows
    if sys.platform == 'win32':
        sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
        sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
    
    print("=" * 50)
    print("Получение Chat ID для Telegram бота")
    print("=" * 50)
    print()
    
    asyncio.run(get_chat_ids())
    
    print("\n" + "=" * 50)
    print("Совет: Скопируйте нужный Chat ID в .env файл:")
    print("   SUPPORT_CHAT_ID=-1001234567890")
    print("=" * 50)

