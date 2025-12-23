"""
Простой способ получить chat_id группы:
1. Добавьте бота в группу как администратора
2. Отправьте любое сообщение в группу (например, "test")
3. Запустите этот скрипт
4. Скрипт покажет chat_id группы из последнего сообщения
"""
import asyncio
import os
import sys
from pathlib import Path
from dotenv import load_dotenv
from telegram import Bot

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

if not BOT_TOKEN:
    print("ОШИБКА: BOT_TOKEN не найден!")
    sys.exit(1)


async def main():
    bot = Bot(token=BOT_TOKEN)
    
    print("=" * 60)
    print("Получение Chat ID группы")
    print("=" * 60)
    print()
    print("Инструкция:")
    print("1. Добавьте бота в группу как администратора")
    print("2. Включите Topics (Темы) в настройках группы")
    print("3. Отправьте любое сообщение в группу (например: 'test')")
    print("4. Подождите 2-3 секунды после отправки сообщения")
    print()
    print("Получаю обновления (это может занять несколько секунд)...")
    print()
    
    print("\nПроверяю webhook...")
    try:
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            print(f"Удаляю webhook: {webhook_info.url}")
            await bot.delete_webhook(drop_pending_updates=True)
    except Exception as e:
        print(f"Предупреждение при проверке webhook: {e}")
    
    print("\nПолучаю обновления...")
    
    try:
        updates = await bot.get_updates(limit=100, timeout=5)
        
        groups_found = []
        
        for update in updates:
            if update.message and update.message.chat.type in ['group', 'supergroup']:
                chat = update.message.chat
                chat_id = chat.id
                
                # Проверяем, не добавляли ли уже эту группу
                if chat_id not in [g['id'] for g in groups_found]:
                    groups_found.append({
                        'id': chat_id,
                        'title': chat.title,
                        'type': chat.type,
                        'username': chat.username
                    })
        
        if groups_found:
            print("\n" + "=" * 60)
            print("НАЙДЕННЫЕ ГРУППЫ:")
            print("=" * 60)
            print()
            
            for i, group in enumerate(groups_found, 1):
                print(f"{i}. {group['title']}")
                print(f"   Chat ID: {group['id']}")
                print(f"   Тип: {group['type']}")
                if group['username']:
                    print(f"   Username: @{group['username']}")
                print()
            
            print("=" * 60)
            print("Скопируйте Chat ID в .env файл:")
            print(f"SUPPORT_CHAT_ID={groups_found[0]['id']}")
            print("=" * 60)
        else:
            print("\nГруппы не найдены!")
            print("\nУбедитесь, что:")
            print("1. Бот добавлен в группу")
            print("2. В группу отправлено сообщение")
            print("3. Бот имеет права на чтение сообщений")
            print("\nПопробуйте отправить еще одно сообщение в группу и запустить скрипт снова.")
    
    except Exception as e:
        print(f"\nОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")

