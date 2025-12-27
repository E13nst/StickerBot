"""
Временный скрипт для добавления команды /get_chat_id в бота
Эта команда покажет chat_id группы, когда её вызвать в группе
"""
import asyncio
import os
from dotenv import load_dotenv
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes

load_dotenv()

BOT_TOKEN = os.getenv('BOT_TOKEN')

async def get_chat_id_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Команда для получения chat_id группы"""
    chat = update.effective_chat
    
    if chat.type in ['group', 'supergroup']:
        message = (
            f"📋 Информация о группе:\n\n"
            f"Название: {chat.title}\n"
            f"Chat ID: `{chat.id}`\n"
            f"Тип: {chat.type}\n"
            f"Username: @{chat.username if chat.username else 'нет'}\n\n"
            f"✅ Скопируйте Chat ID в .env файл:\n"
            f"`SUPPORT_CHAT_ID={chat.id}`"
        )
        await update.message.reply_text(message, parse_mode='Markdown')
    else:
        await update.message.reply_text(
            "Эта команда работает только в группах. "
            "Добавьте бота в группу и вызовите команду там."
        )

async def main():
    print("=" * 60)
    print("Добавление временной команды /get_chat_id")
    print("=" * 60)
    print()
    print("Инструкция:")
    print("1. Этот скрипт запустит бота с командой /get_chat_id")
    print("2. Добавьте бота в группу")
    print("3. В группе отправьте: /get_chat_id")
    print("4. Бот покажет Chat ID группы")
    print("5. Нажмите Ctrl+C для остановки")
    print()
    print("Запускаю бота...")
    print()
    
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("get_chat_id", get_chat_id_command))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling()
    
    print("Бот запущен! Отправьте /get_chat_id в группе.")
    print("Нажмите Ctrl+C для остановки.")
    print()
    
    try:
        await asyncio.Event().wait()
    except KeyboardInterrupt:
        print("\nОстанавливаю бота...")
        await application.updater.stop()
        await application.stop()
        await application.shutdown()
        print("Бот остановлен.")

if __name__ == "__main__":
    asyncio.run(main())





