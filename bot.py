import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    Application, CommandHandler, MessageHandler, filters,
    ConversationHandler, ContextTypes
)
from config import BOT_TOKEN, ADMIN_IDS
from image_processor import ImageProcessor
from sticker_manager import StickerManager

# Состояния диалога
(
    CHOOSING_ACTION,
    WAITING_NEW_TITLE,
    WAITING_STICKER,
    WAITING_EMOJI,
    WAITING_DECISION,
    WAITING_SHORT_NAME,
    WAITING_EXISTING_NAME,
) = range(7)

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
                WAITING_NEW_TITLE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_new_set_title)
                ],
                WAITING_STICKER: [
                    MessageHandler(filters.PHOTO | filters.Document.ALL, self.handle_sticker)
                ],
                WAITING_EMOJI: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_emoji)
                ],
                WAITING_DECISION: [
                    MessageHandler(filters.Regex('^(Готово|Завершить набор)$'), self.finish_sticker_collection),
                    MessageHandler(filters.PHOTO | filters.Document.ALL, self.handle_sticker),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.prompt_waiting_for_more)
                ],
                WAITING_SHORT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_short_name)
                ],
                WAITING_EXISTING_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_existing_set_name)
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
            "Пожалуйста, выберите название для нового набора стикеров.",
            reply_markup=ReplyKeyboardRemove()
        )

        self.user_data[update.effective_user.id] = {
            'action': 'create_new',
            'stickers': []
        }
        return WAITING_NEW_TITLE

    async def add_to_existing(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Добавление стикера в существующий стикерсет"""
        await update.message.reply_text(
            "Добавляем стикер в существующий стикерсет.\n"
            "Пришли мне изображение для нового стикера:",
            reply_markup=ReplyKeyboardRemove()
        )

        self.user_data[update.effective_user.id] = {'action': 'add_existing'}
        return WAITING_STICKER

    async def handle_new_set_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка пользовательского названия нового стикерсета"""
        user_id = update.effective_user.id
        title = update.message.text.strip()

        if not title:
            await update.message.reply_text("Название не может быть пустым. Попробуйте еще раз.")
            return WAITING_NEW_TITLE

        user_data = self.user_data.get(user_id, {})
        user_data['title'] = title
        self.user_data[user_id] = user_data

        await update.message.reply_text(
            "Теперь пришлите, пожалуйста, будущий стикер — файл в формате PNG, JPG или WebP. "
            "Рекомендуемое разрешение 512×512. Для лучшего качества отправьте изображение как файл (без сжатия), "
            "а не как фотографию.\n\n"
            "Внимание: не загружайте изображения, защищённые авторскими правами.",
            reply_markup=ReplyKeyboardRemove()
        )

        return WAITING_STICKER

    async def handle_sticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка присланного изображения"""
        user_id = update.effective_user.id

        if user_id not in self.user_data or 'action' not in self.user_data[user_id]:
            await update.message.reply_text("Что-то пошло не так. Запустите процесс заново командой /start.")
            return ConversationHandler.END

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

            self.user_data[user_id]['current_webp'] = webp_data

            await update.message.reply_text(
                "Пожалуйста, пришлите смайл, который соответствует этому стикеру.",
                reply_markup=ReplyKeyboardRemove()
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
        user_data = self.user_data.get(user_id, {})
        action = user_data.get('action')

        if not action or 'current_webp' not in user_data:
            await update.message.reply_text(
                "Не удалось сопоставить эмодзи с изображением. Попробуйте отправить стикер заново."
            )
            return WAITING_STICKER

        if action == 'create_new':
            stickers = user_data.setdefault('stickers', [])
            stickers.append({
                'webp_data': user_data['current_webp'],
                'emoji': emoji
            })
            user_data.pop('current_webp', None)
            self.user_data[user_id] = user_data

            count = len(stickers)

            await update.message.reply_text(
                f"Стикер добавлен. Количество стикеров в наборе: {count}. "
                "Чтобы добавить еще один стикер, отправьте мне соответствующий файл в формате PNG, JPG или WebP.\n"
                "Когда закончите, нажмите кнопку «Готово».",
                reply_markup=ReplyKeyboardMarkup(
                    [['Готово']],
                    resize_keyboard=True,
                    one_time_keyboard=False
                )
            )

            return WAITING_DECISION

        if action == 'add_existing':
            user_data['emoji'] = emoji
            self.user_data[user_id] = user_data

            await update.message.reply_text(
                "Введи название существующего стикерсета:",
                reply_markup=ReplyKeyboardRemove()
            )
            return WAITING_EXISTING_NAME

        await update.message.reply_text("Не удалось обработать эмодзи. Попробуйте снова.")
        return WAITING_STICKER

    async def finish_sticker_collection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Запрос короткого имени для нового стикерсета"""
        user_id = update.effective_user.id
        user_data = self.user_data.get(user_id, {})
        stickers = user_data.get('stickers', [])

        if not stickers:
            await update.message.reply_text(
                "В наборе пока нет ни одного стикера. Сначала добавьте хотя бы один стикер."
            )
            return WAITING_STICKER

        await update.message.reply_text(
            "Пожалуйста, выберите короткое название, которое будет использоваться в адресе вашего набора. "
            "Я создам ссылку, которой вы сможете поделиться с друзьями и подписчиками.",
            reply_markup=ReplyKeyboardRemove()
        )

        return WAITING_SHORT_NAME

    async def prompt_waiting_for_more(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Подсказка пользователю, если ожидается файл или завершение"""
        await update.message.reply_text(
            "Чтобы продолжить, отправьте файл следующего стикера или нажмите кнопку «Готово», когда закончите.",
            reply_markup=ReplyKeyboardMarkup(
                [['Готово']],
                resize_keyboard=True,
                one_time_keyboard=False
            )
        )
        return WAITING_DECISION

    async def handle_short_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Проверка короткого имени и создание стикерсета"""
        user_id = update.effective_user.id
        short_name = update.message.text.strip()
        user_data = self.user_data.get(user_id)

        if not user_data or user_data.get('action') != 'create_new':
            await update.message.reply_text("Процесс создания набора не найден. Начните заново с /start.")
            return ConversationHandler.END

        if not re.fullmatch(r'[A-Za-z0-9_]{3,64}', short_name):
            await update.message.reply_text(
                "Название может содержать только латинские буквы, цифры и символ подчёркивания. "
                "Минимум 3 символа. Попробуйте другое имя."
            )
            return WAITING_SHORT_NAME

        full_name = f"{short_name}_by_{context.bot.username}"
        stickers = user_data.get('stickers', [])
        title = user_data.get('title')

        availability = self.sticker_manager.is_sticker_set_available(full_name)

        if availability is None:
            await update.message.reply_text(
                "Не удалось проверить доступность имени. Попробуйте позже или введите другое название."
            )
            return WAITING_SHORT_NAME

        if not availability:
            await update.message.reply_text(
                "Такое короткое название уже занято. Пожалуйста, предложите другое."
            )
            return WAITING_SHORT_NAME

        if not stickers or not title:
            await update.message.reply_text("Недостаточно данных для создания стикерсета. Начните заново с /start.")
            self.user_data.pop(user_id, None)
            return ConversationHandler.END

        first_sticker = stickers[0]

        created = self.sticker_manager.create_new_sticker_set(
            user_id=user_id,
            name=full_name,
            title=title,
            png_sticker=first_sticker['webp_data'],
            emojis=first_sticker['emoji']
        )

        if not created:
            await update.message.reply_text(
                "Не удалось создать стикерсет. Попробуйте выбрать другое короткое название или начать заново."
            )
            return WAITING_SHORT_NAME

        failed_additions = 0
        for sticker in stickers[1:]:
            added = self.sticker_manager.add_sticker_to_set(
                user_id=user_id,
                name=full_name,
                png_sticker=sticker['webp_data'],
                emojis=sticker['emoji']
            )
            if not added:
                failed_additions += 1

        sticker_set_link = f"https://t.me/addstickers/{full_name}"
        message = (
            "🎉 Стикерсет успешно создан!\n"
            f"Название: {title}\n"
            f"Короткое имя: {short_name}\n"
            f"Добавить набор: {sticker_set_link}"
        )

        if failed_additions:
            message += (
                f"\n\n⚠️ Не удалось добавить {failed_additions} стикеров. "
                "Вы можете добавить их вручную позже."
            )

        await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

        self.user_data.pop(user_id, None)
        return ConversationHandler.END

    async def handle_existing_set_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Добавление стикера в существующий набор"""
        user_id = update.effective_user.id
        set_name = update.message.text.strip()
        user_data = self.user_data.get(user_id, {})

        if not set_name or 'current_webp' not in user_data or 'emoji' not in user_data:
            await update.message.reply_text(
                "Не удалось добавить стикер. Попробуйте начать заново с /start."
            )
            self.user_data.pop(user_id, None)
            return ConversationHandler.END

        success = self.sticker_manager.add_sticker_to_set(
            user_id=user_id,
            name=set_name,
            png_sticker=user_data['current_webp'],
            emojis=user_data['emoji']
        )

        if success:
            await update.message.reply_text(
                f"✅ Стикер успешно добавлен в стикерсет!\nЭмодзи: {user_data['emoji']}",
                reply_markup=ReplyKeyboardRemove()
            )
        else:
            await update.message.reply_text(
                "Не удалось добавить стикер. Проверь название стикерсета.",
                reply_markup=ReplyKeyboardRemove()
            )

        self.user_data.pop(user_id, None)
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