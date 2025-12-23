import logging
import re
from typing import Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from src.bot.states import CHOOSING_ACTION, SUPPORT_MODE
from src.config.settings import SUPPORT_CHAT_ID, SUPPORT_ENABLED, SUPPORT_USE_TOPICS
from src.utils.support_storage import SupportStorage

logger = logging.getLogger(__name__)

# Инициализируем хранилище
storage = SupportStorage()


async def enter_support_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Вход в режим поддержки"""
    if not SUPPORT_ENABLED or not SUPPORT_CHAT_ID:
        text = "📞 Функция поддержки временно недоступна."
        if update.callback_query:
            await update.callback_query.answer()
            await update.callback_query.edit_message_text(text)
        else:
            await update.message.reply_text(text)
        return CHOOSING_ACTION
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("◀️ Назад в меню", callback_data="exit_support")]
    ])
    
    text = (
        "📞 *Режим поддержки*\n\n"
        "Напишите ваш вопрос, и наша команда ответит в ближайшее время.\n\n"
        "Вы можете отправить:\n"
        "• Текстовое сообщение\n"
        "• Фото\n"
        "• Документ\n"
        "• Голосовое сообщение\n"
        "• Видео\n"
        "• Стикер\n\n"
        "Для выхода используйте кнопку ниже или /cancel."
    )
    
    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(
            text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    else:
        await update.message.reply_text(
            text,
            reply_markup=keyboard,
            parse_mode='Markdown'
        )
    
    # Очищаем контекст пользователя
    context.user_data['support_mode'] = True
    
    return SUPPORT_MODE


async def exit_support_mode(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Выход из режима поддержки"""
    query = update.callback_query
    await query.answer()
    
    # Очищаем флаг режима поддержки
    context.user_data.pop('support_mode', None)
    
    # Возвращаем в главное меню
    from src.bot.handlers.start import start
    
    # Создаём синтетический update с message для совместимости
    class SyntheticUpdate:
        def __init__(self, original_update):
            self.effective_user = original_update.effective_user
            self.effective_chat = original_update.effective_chat
            self.message = original_update.callback_query.message
            self.callback_query = None
    
    synthetic_update = SyntheticUpdate(update)
    
    # Удаляем текущее сообщение
    try:
        await query.message.delete()
    except:
        pass
    
    # Отправляем новое сообщение с главным меню
    user = update.effective_user
    name = user.first_name or "друг"
    
    from src.bot.handlers.start import main_menu_keyboard
    
    text = (
        f"Йо, {name}!\n"
        "Ты в зоне Stixly — наше комьюнити собирает самую большую галерею стикеров.\n\n"
        "<b>Сейчас ты можешь:</b>\n"
        "• Найти стикер в галерее\n"
        "• Добавить стикерсет в галерею (+10 ART)\n"
        "<i>Дальше — умный поиск, конструктор стикеров и AI-инструменты.</i>\n\n"
        "ART — это внутренняя валюта за вклад в Stixly.\n"
        "Зарабатывай ART и продвигайся по турнирной таблице.\n\n"
        "<b>Начни сейчас, отправив любой стикер и заработай ART!</b>\n\n"
        "❓ Помощь: /help | 📞 Поддержка: /support\n"
    )
    
    await query.message.reply_text(
        text,
        reply_markup=main_menu_keyboard(),
        parse_mode='HTML'
    )
    
    return CHOOSING_ACTION


async def get_or_create_user_topic(context: ContextTypes.DEFAULT_TYPE, user_id: int, user_name: str) -> Optional[int]:
    """Получить или создать тему для пользователя"""
    if not SUPPORT_USE_TOPICS:
        return None
    
    # Проверяем, есть ли уже тема для этого пользователя
    existing_topic = storage.get_user_topic(user_id)
    if existing_topic:
        logger.info(f"Используем существующую тему {existing_topic} для пользователя {user_id}")
        return existing_topic
    
    # Создаём новую тему
    try:
        topic_name = f"Поддержка: {user_name} (ID: {user_id})"
        logger.info(f"Создаём новую тему: {topic_name}")
        
        forum_topic = await context.bot.create_forum_topic(
            chat_id=int(SUPPORT_CHAT_ID),
            name=topic_name
        )
        
        topic_id = forum_topic.message_thread_id
        
        # Сохраняем тему в хранилище
        storage.save_user_topic(user_id, topic_id)
        
        logger.info(f"Создана тема {topic_id} для пользователя {user_id}")
        return topic_id
        
    except TelegramError as e:
        logger.error(f"Ошибка создания темы для пользователя {user_id}: {e}")
        return None


async def forward_to_support(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Пересылка сообщения в чат поддержки"""
    if not SUPPORT_ENABLED or not SUPPORT_CHAT_ID:
        return SUPPORT_MODE
    
    user = update.effective_user
    message = update.message
    
    if not message:
        return SUPPORT_MODE
    
    try:
        # Получаем или создаём тему для пользователя
        topic_id = await get_or_create_user_topic(
            context,
            user.id,
            user.full_name or f"User {user.id}"
        )
        
        # Формируем информацию о пользователе
        user_info = (
            f"👤 Пользователь: {user.full_name or 'Неизвестный'}\n"
            f"🆔 ID: {user.id}\n"
            f"📛 Username: @{user.username if user.username else 'нет'}\n"
        )
        
        # Отправляем информацию о пользователе в поддержку
        info_msg = await context.bot.send_message(
            chat_id=int(SUPPORT_CHAT_ID),
            text=user_info + "\n📩 Сообщение:",
            message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
        )
        
        # Пересылаем оригинальное сообщение
        forwarded = None
        
        if message.text:
            forwarded = await context.bot.send_message(
                chat_id=int(SUPPORT_CHAT_ID),
                text=message.text,
                message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
            )
        elif message.photo:
            forwarded = await context.bot.send_photo(
                chat_id=int(SUPPORT_CHAT_ID),
                photo=message.photo[-1].file_id,
                caption=message.caption,
                message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
            )
        elif message.document:
            forwarded = await context.bot.send_document(
                chat_id=int(SUPPORT_CHAT_ID),
                document=message.document.file_id,
                caption=message.caption,
                message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
            )
        elif message.voice:
            forwarded = await context.bot.send_voice(
                chat_id=int(SUPPORT_CHAT_ID),
                voice=message.voice.file_id,
                caption=message.caption,
                message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
            )
        elif message.video:
            forwarded = await context.bot.send_video(
                chat_id=int(SUPPORT_CHAT_ID),
                video=message.video.file_id,
                caption=message.caption,
                message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
            )
        elif message.sticker:
            forwarded = await context.bot.send_sticker(
                chat_id=int(SUPPORT_CHAT_ID),
                sticker=message.sticker.file_id,
                message_thread_id=topic_id if SUPPORT_USE_TOPICS else None
            )
        
        if forwarded:
            # Сохраняем связь для ответа
            storage.save_mapping(
                support_msg_id=forwarded.message_id,
                user_id=user.id,
                topic_id=topic_id if topic_id else 0
            )
        
        # Подтверждаем пользователю
        await message.reply_text(
            "✅ Ваше сообщение передано в поддержку. Ответим в ближайшее время."
        )
        
    except Exception as e:
        logger.error(f"Ошибка пересылки в поддержку: {e}", exc_info=True)
        await message.reply_text("⚠️ Не удалось отправить сообщение в поддержку. Попробуйте позже.")
    
    return SUPPORT_MODE


async def forward_to_user(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Пересылка ответа из чата поддержки обратно пользователю"""
    if not SUPPORT_ENABLED or not SUPPORT_CHAT_ID:
        return
    
    message = update.message
    
    # Проверяем, что сообщение из чата поддержки и является ответом
    if str(message.chat.id) != str(SUPPORT_CHAT_ID):
        return
    
    if not message.reply_to_message:
        return
    
    try:
        # Получаем информацию о связанном сообщении
        replied_msg_id = message.reply_to_message.message_id
        
        # Пытаемся получить данные из хранилища
        support_data = storage.get_mapping(replied_msg_id)
        
        if not support_data:
            # Fallback: пытаемся извлечь user_id из текста сообщения
            user_id = extract_user_id_from_message(message.reply_to_message)
            if not user_id:
                await message.reply_text("❌ Не удалось определить пользователя для ответа.")
                return
            support_data = {'user_id': user_id}
        
        user_id = support_data['user_id']
        
        # Создаём inline-кнопку для перехода в поддержку
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📞 Связаться с поддержкой", callback_data="enter_support")]
        ])
        
        # Отправляем ответ пользователю
        if message.text:
            await context.bot.send_message(
                chat_id=user_id,
                text=f"👨‍💼 *Поддержка:*\n\n{message.text}",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        elif message.photo:
            await context.bot.send_photo(
                chat_id=user_id,
                photo=message.photo[-1].file_id,
                caption=f"👨‍💼 *Поддержка:*\n\n{message.caption}" if message.caption else "👨‍💼 *Поддержка*",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        elif message.document:
            await context.bot.send_document(
                chat_id=user_id,
                document=message.document.file_id,
                caption=f"👨‍💼 *Поддержка:*\n\n{message.caption}" if message.caption else "👨‍💼 *Поддержка*",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        elif message.voice:
            await context.bot.send_voice(
                chat_id=user_id,
                voice=message.voice.file_id,
                caption=f"👨‍💼 *Поддержка:*\n\n{message.caption}" if message.caption else "👨‍💼 *Поддержка*",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        elif message.video:
            await context.bot.send_video(
                chat_id=user_id,
                video=message.video.file_id,
                caption=f"👨‍💼 *Поддержка:*\n\n{message.caption}" if message.caption else "👨‍💼 *Поддержка*",
                parse_mode='Markdown',
                reply_markup=keyboard
            )
        elif message.sticker:
            await context.bot.send_sticker(
                chat_id=user_id,
                sticker=message.sticker.file_id,
                reply_markup=keyboard
            )
            # Отправляем дополнительное сообщение с подписью
            await context.bot.send_message(
                chat_id=user_id,
                text="👨‍💼 *Поддержка*",
                parse_mode='Markdown'
            )
        
        # Подтверждаем в чате поддержки
        await message.reply_text("✅ Ответ отправлен пользователю.")
        
    except TelegramError as e:
        logger.error(f"Ошибка отправки ответа пользователю: {e}", exc_info=True)
        await message.reply_text(f"❌ Ошибка отправки: {str(e)}")
    except Exception as e:
        logger.error(f"Неожиданная ошибка в forward_to_user: {e}", exc_info=True)
        await message.reply_text(f"❌ Произошла ошибка: {str(e)}")


def extract_user_id_from_message(message) -> Optional[int]:
    """Извлекает user_id из текста сообщения поддержки (резервный метод)"""
    if message.text and "ID:" in message.text:
        match = re.search(r'ID:\s*(\d+)', message.text)
        if match:
            return int(match.group(1))
    return None

