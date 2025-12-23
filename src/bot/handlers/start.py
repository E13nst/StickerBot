import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo, ReplyKeyboardRemove
from telegram.ext import ContextTypes

from src.bot.states import CHOOSING_ACTION, WAITING_STICKER_PACK_LINK
from src.config.settings import MINIAPP_GALLERY_URL

logger = logging.getLogger(__name__)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Создает клавиатуру главного меню"""
    keyboard = [
        [
            InlineKeyboardButton(
                "🔍 Найти стикер в галерее",
                web_app=WebAppInfo(
                    url=MINIAPP_GALLERY_URL
                ),
            )
        ],
        [
            InlineKeyboardButton(
                "🛠 Управление стикерами",
                callback_data="manage_stickers_menu",
            )
        ],
        [
            InlineKeyboardButton(
                "📞 Поддержка",
                callback_data="enter_support",
            )
        ],
        [
            InlineKeyboardButton(
                "📢 Telegram-канал",
                url="https://t.me/stixlyofficial",
            )
        ],
    ]
    return InlineKeyboardMarkup(keyboard)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начало диалога"""
    user = update.effective_user
    context.user_data.clear()

    name = user.first_name or "друг"

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

    await update.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode='HTML')

    return CHOOSING_ACTION


async def handle_add_pack_from_sticker(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для кнопки 'Добавить стикерсет в галерею'"""
    try:
        query = update.callback_query
        if not query:
            logger.error("handle_add_pack_from_sticker вызван без callback_query")
            return CHOOSING_ACTION
        
        await query.answer()

        context.user_data.clear()
        context.user_data['action'] = 'add_pack_from_sticker'

        try:
            await query.edit_message_text(
                "Ок, давай добавим стикерсет в галерею.\n\n"
                "Пришли любой стикер из набора, который хочешь добавить.",
                reply_markup=ReplyKeyboardRemove()
            )
        except Exception as e:
            # Если не удалось отредактировать сообщение, отправляем новое
            logger.warning(f"Не удалось отредактировать сообщение: {e}")
            if query.message:
                await query.message.reply_text(
                    "Ок, давай добавим стикерсет в галерею.\n\n"
                    "Пришли любой стикер из набора, который хочешь добавить.",
                    reply_markup=ReplyKeyboardRemove()
                )
            else:
                logger.error("Не удалось отправить сообщение: нет query.message")
                return CHOOSING_ACTION

        return WAITING_STICKER_PACK_LINK
    except Exception as e:
        logger.error(f"Ошибка в handle_add_pack_from_sticker: {e}", exc_info=True)
        if update.callback_query:
            try:
                await update.callback_query.answer("Произошла ошибка. Попробуй ещё раз.", show_alert=True)
            except:
                pass
        return CHOOSING_ACTION


async def handle_manage_stickers_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для кнопки 'Управление стикерами' - показывает подменю"""
    query = update.callback_query
    await query.answer()

    keyboard = [
        [
            InlineKeyboardButton(
                "Создать новый стикерсет",
                callback_data="manage:create_new"
            )
        ],
        [
            InlineKeyboardButton(
                "Добавить в существующий",
                callback_data="manage:add_existing"
            )
        ],
        [
            InlineKeyboardButton(
                "Управлять публикацией",
                callback_data="manage:publication"
            )
        ],
        [
            InlineKeyboardButton(
                "Назад в главное меню",
                callback_data="back_to_main"
            )
        ],
    ]

    await query.edit_message_text(
        "Выбери действие:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return CHOOSING_ACTION


async def handle_back_to_main(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик для кнопки 'Назад в главное меню'"""
    query = update.callback_query
    await query.answer()
    
    user = update.effective_user
    context.user_data.clear()
    
    name = user.first_name or "друг"
    
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
    
    try:
        await query.edit_message_text(text, reply_markup=main_menu_keyboard(), parse_mode='HTML')
    except Exception as e:
        logger.warning(f"Не удалось отредактировать сообщение: {e}")
        if query.message:
            await query.message.reply_text(text, reply_markup=main_menu_keyboard(), parse_mode='HTML')

    return CHOOSING_ACTION
