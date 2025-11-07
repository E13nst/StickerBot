import logging
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)
from config import BOT_TOKEN, ADMIN_IDS
from image_processor import ImageProcessor
from sticker_manager import StickerManager

# Состояния диалога
CHOOSING_ACTION, WAITING_STICKER, WAITING_EMOJI, WAITING_TITLE = range(4)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

logger = logging.getLogger(__name__)


class StickerBot:
    def __init__(self):
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.sticker_manager = StickerManager(BOT_TOKEN)
        self.image_processor = ImageProcessor()
        self.user_data = {}

        self.setup_handlers()

    def setup_handlers(self):
        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', self.start)],
            states={
                CHOOSING_ACTION: [
                    MessageHandler(filters.Regex('^(Создать новый стикерсет)$'), self.create_new_set),
                    MessageHandler(filters.Regex('^(Добавить в существующий)$'), self.add_to_existing),
                ],
                WAITING_STICKER: [
                    MessageHandler(filters.PHOTO | filters.Document.ALL, self.handle_sticker)
                ],
                WAITING_EMOJI: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_emoji)
                ],
                WAITING_TITLE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_title)
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)]
        )

        self.application.add_handler(conv_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало диалога"""
        user = update.message.from_user

        reply_keyboard = [['Создать новый стикерсет', 'Добавить в существующий']]

        await update.message.reply_text(
            f"Привет, {user.first_name}! Я помогу тебе создать стикерсет.\n"
            "Выбери действие:",
            reply_markup=ReplyKeyboardMarkup(
                reply_keyboard,
                one_time_keyboard=True,
                input_field_placeholder='Что будем делать?'
            )
        )

        return CHOOSING_ACTION

    async def create_new_set(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Создание нового стикерсета"""
        await update.message.reply_text(
            "Отлично! Создаем новый стикерсет.\n"
            "Пришли мне изображение для первого стикера:",
            reply_markup=ReplyKeyboardRemove()
        )

        self.user_data[update.effective_user.id] = {'action': 'create_new'}
        return WAITING_STICKER

    async def add_to_existing(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Добавление стикера в существующий стикерсет"""
        await update.message.reply_text(
            "Добавляем стикер в существующий стикерсет.\n"
            "Пришли мне изображение для нового стикера:",
            reply_markup=ReplyKeyboardRemove()
        )

        self.user_data[update.effective_user.id] = {'action': 'add_existing'}
        return WAITING_STICKER

    async def handle_sticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка присланного изображения"""
        user_id = update.effective_user.id

        try:
            # Получаем файл изображения
            if update.message and update.message.photo:
                photo_file = await update.message.photo[-1].get_file()
            elif update.message and update.message.document:
                photo_file = await update.message.document.get_file()
            else:
                await update.message.reply_text("Пожалуйста, пришли изображение.")
                return WAITING_STICKER

            # Скачиваем изображение
            image_data = await photo_file.download_as_bytearray()

            # Конвертируем в WebP
            webp_data = self.image_processor.convert_to_webp(bytes(image_data))

            # Сохраняем во временные данные пользователя
            if user_id not in self.user_data:
                self.user_data[user_id] = {}

            self.user_data[user_id]['webp_data'] = webp_data

            await update.message.reply_text(
                "Отлично! Теперь отправь эмодзи, которое будет ассоциироваться с этим стикером (например, 😊):"
            )

            return WAITING_EMOJI

        except Exception as e:
            logger.error(f"Ошибка обработки изображения: {e}")
            await update.message.reply_text(
                "Произошла ошибка при обработке изображения. Попробуй другое изображение."
            )
            return WAITING_STICKER

    async def handle_emoji(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка эмодзи"""
        user_id = update.effective_user.id
        emoji = update.message.text

        self.user_data[user_id]['emoji'] = emoji

        if self.user_data[user_id]['action'] == 'create_new':
            await update.message.reply_text(
                "Теперь придумай название для твоего стикерсета (только латинские буквы, цифры и подчеркивания):"
            )
            return WAITING_TITLE
        else:
            # Для существующего стикерсета запрашиваем название
            await update.message.reply_text(
                "Введи название существующего стикерсета:"
            )
            return WAITING_TITLE

    async def handle_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка названия стикерсета"""
        user_id = update.effective_user.id
        title_or_name = update.message.text

        try:
            user_data = self.user_data[user_id]
            webp_data = user_data['webp_data']
            emoji = user_data['emoji']

            if user_data['action'] == 'create_new':
                # Создаем новый стикерсет
                sticker_set_name = f"{title_or_name}_by_{context.bot.username}"

                success = self.sticker_manager.create_new_sticker_set(
                    user_id=user_id,
                    name=sticker_set_name,
                    title=title_or_name,
                    png_sticker=webp_data,
                    emojis=emoji
                )

                if success:
                    sticker_set_link = f"https://t.me/addstickers/{sticker_set_name}"
                    await update.message.reply_text(
                        f"🎉 Стикерсет успешно создан!\n"
                        f"Название: {title_or_name}\n"
                        f"Эмодзи: {emoji}\n\n"
                        f"Добавить набор: {sticker_set_link}\n"
                        f"Теперь ты можешь добавить больше стикеров командой /start"
                    )
                else:
                    await update.message.reply_text(
                        "Не удалось создать стикерсет. Попробуй еще раз."
                    )

            else:
                # Добавляем в существующий стикерсет
                success = self.sticker_manager.add_sticker_to_set(
                    user_id=user_id,
                    name=title_or_name,
                    png_sticker=webp_data,
                    emojis=emoji
                )

                if success:
                    await update.message.reply_text(
                        f"✅ Стикер успешно добавлен в стикерсет!\n"
                        f"Эмодзи: {emoji}"
                    )
                else:
                    await update.message.reply_text(
                        "Не удалось добавить стикер. Проверь название стикерсета."
                    )

            # Очищаем данные пользователя
            if user_id in self.user_data:
                del self.user_data[user_id]

            return ConversationHandler.END

        except Exception as e:
            logger.error(f"Ошибка создания стикерсета: {e}")
            await update.message.reply_text(
                "Произошла ошибка. Попробуй начать заново с /start"
            )
            return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена диалога"""
        user_id = update.effective_user.id
        if user_id in self.user_data:
            del self.user_data[user_id]

        await update.message.reply_text(
            "Диалог отменен. Используй /start чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove()
        )

        return ConversationHandler.END

    def run(self):
        """Запуск бота"""
        self.application.run_polling()


if __name__ == '__main__':
    bot = StickerBot()
    bot.run()