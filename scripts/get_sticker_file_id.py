"""
Скрипт для получения file_id стикера из Telegram
Использование:
1. Отправьте стикер боту в личные сообщения
2. Запустите этот скрипт с вашим BOT_TOKEN
3. Скрипт покажет file_id последнего стикера, отправленного боту
"""
import asyncio
import os
import sys
from pathlib import Path

# Добавляем корневую директорию в путь
root_dir = Path(__file__).parent.parent
sys.path.insert(0, str(root_dir))

from telegram import Bot
from telegram.ext import Application, MessageHandler, filters, ContextTypes

BOT_TOKEN = os.getenv('BOT_TOKEN')
if not BOT_TOKEN:
    print("Ошибка: BOT_TOKEN не установлен в переменных окружения")
    sys.exit(1)

sticker_file_id = None

async def handle_sticker(update, context: ContextTypes.DEFAULT_TYPE):
    """Обработчик для получения file_id стикера"""
    global sticker_file_id
    if update.message and update.message.sticker:
        sticker_file_id = update.message.sticker.file_id
        print(f"\n✅ Получен file_id стикера:")
        print(f"PLACEHOLDER_STICKER_FILE_ID={sticker_file_id}")
        print(f"\nДобавьте эту строку в ваш .env файл")
        await update.message.reply_text(f"File ID получен: {sticker_file_id[:20]}...")
        # Останавливаем бота после получения file_id
        context.application.stop_running()

async def main():
    """Запуск бота для получения file_id"""
    print("Бот запущен. Отправьте стикер боту в личные сообщения...")
    print("После получения стикера скрипт автоматически остановится.")
    
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(MessageHandler(filters.Sticker.ALL, handle_sticker))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    # Ждем получения стикера
    try:
        await asyncio.sleep(300)  # Ждем до 5 минут
    except KeyboardInterrupt:
        pass
    finally:
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        
        if sticker_file_id:
            print(f"\n✅ File ID сохранен: {sticker_file_id}")
        else:
            print("\n❌ Стикер не был получен. Убедитесь, что вы отправили стикер боту.")

if __name__ == "__main__":
    asyncio.run(main())








