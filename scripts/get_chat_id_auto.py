"""
Автоматический скрипт для получения chat_id группы
Просто отправьте сообщение в группу и запустите скрипт
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
    print("ВАЖНО: Перед запуском скрипта:")
    print("1. Добавьте бота в группу как администратора")
    print("2. Включите Topics (Темы) в настройках группы")
    print("3. Отправьте ЛЮБОЕ сообщение в группу (например: 'test' или 'hello')")
    print()
    print("Затем запустите этот скрипт снова.")
    print()
    print("Получаю обновления...")
    print()
    
    try:
        # Проверяем и удаляем webhook
        webhook_info = await bot.get_webhook_info()
        if webhook_info.url:
            print(f"Удаляю webhook: {webhook_info.url}")
            await bot.delete_webhook(drop_pending_updates=True)
            print("Webhook удален\n")
    except Exception as e:
        print(f"Предупреждение при проверке webhook: {e}\n")
    
    try:
        # Получаем последние обновления
        updates = await bot.get_updates(limit=100, timeout=10)
        
        groups_found = []
        private_chats = []
        
        for update in updates:
            if update.message:
                chat = update.message.chat
                chat_id = chat.id
                
                if chat.type in ['group', 'supergroup']:
                    # Проверяем, не добавляли ли уже эту группу
                    if chat_id not in [g['id'] for g in groups_found]:
                        groups_found.append({
                            'id': chat_id,
                            'title': chat.title,
                            'type': chat.type,
                            'username': chat.username,
                            'last_message': update.message.text[:50] if update.message.text else "медиа"
                        })
                elif chat.type == 'private':
                    if chat_id not in [c['id'] for c in private_chats]:
                        private_chats.append({
                            'id': chat_id,
                            'name': chat.first_name or "Неизвестно"
                        })
        
        if groups_found:
            print("=" * 60)
            print("НАЙДЕННЫЕ ГРУППЫ:")
            print("=" * 60)
            print()
            
            for i, group in enumerate(groups_found, 1):
                print(f"{i}. {group['title']}")
                print(f"   Chat ID: {group['id']}")
                print(f"   Тип: {group['type']}")
                if group['username']:
                    print(f"   Username: @{group['username']}")
                print(f"   Последнее сообщение: {group['last_message']}")
                print()
            
            print("=" * 60)
            print("СКОПИРУЙТЕ Chat ID в .env файл:")
            print("=" * 60)
            print()
            print(f"SUPPORT_CHAT_ID={groups_found[0]['id']}")
            print()
            print("=" * 60)
            
            if len(groups_found) > 1:
                print(f"\nНайдено {len(groups_found)} групп. Используйте Chat ID нужной группы.")
        else:
            print("Группы не найдены!")
            print()
            print("Убедитесь, что:")
            print("1. Бот добавлен в группу как администратор")
            print("2. В группу отправлено хотя бы одно сообщение")
            print("3. Бот имеет права на чтение сообщений")
            print()
            print("Попробуйте:")
            print("- Отправить еще одно сообщение в группу")
            print("- Подождать несколько секунд")
            print("- Запустить скрипт снова")
            
            if private_chats:
                print()
                print("Найдены личные чаты (не группы):")
                for chat in private_chats:
                    print(f"  - {chat['name']} (ID: {chat['id']})")
    
    except Exception as e:
        print(f"\nОШИБКА: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\nПрервано пользователем")

