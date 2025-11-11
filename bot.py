import asyncio
import logging
import html
from logging.handlers import RotatingFileHandler
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
    ConversationHandler, ContextTypes
)
from config import (
    BOT_TOKEN,
    ADMIN_IDS,
    GALLERY_BASE_URL,
    GALLERY_SERVICE_TOKEN,
    GALLERY_DEFAULT_LANGUAGE,
    LOG_FILE_PATH,
)
from gallery_client import GalleryClient
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
    WAITING_EXISTING_CHOICE,
) = range(7)

PAGE_PREV_LABEL = '⬅️ Назад'
PAGE_NEXT_LABEL = '➡️ Вперед'
CANCEL_LABEL = '⛔️ Отмена'

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(),
        RotatingFileHandler(LOG_FILE_PATH, maxBytes=1_000_000, backupCount=3)
    ]
)

logger = logging.getLogger(__name__)


class StickerBot:
    def __init__(self):
        self._validate_configuration()
        self.application = Application.builder().token(BOT_TOKEN).build()
        self.sticker_manager = StickerManager(BOT_TOKEN)
        self.image_processor = ImageProcessor()
        self.gallery_client = GalleryClient(
            base_url=GALLERY_BASE_URL,
            service_token=GALLERY_SERVICE_TOKEN,
            default_language=GALLERY_DEFAULT_LANGUAGE,
        )

        self.setup_handlers()

    @staticmethod
    def _validate_configuration():
        missing = []

        if not BOT_TOKEN:
            missing.append('BOT_TOKEN')
        if not GALLERY_BASE_URL:
            missing.append('GALLERY_BASE_URL')
        if not GALLERY_SERVICE_TOKEN:
            missing.append('GALLERY_SERVICE_TOKEN')

        if missing:
            raise ValueError(
                f"Не заданы необходимые переменные окружения: {', '.join(missing)}. "
                "Проверь .env или окружение и перезапусти бота."
            )

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
                WAITING_EXISTING_CHOICE: [
                    CallbackQueryHandler(self.handle_existing_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_existing_choice_text)
                ],
            },
            fallbacks=[CommandHandler('cancel', self.cancel)],
            allow_reentry=True
        )

        self.application.add_handler(conv_handler)
        self.application.add_error_handler(self.error_handler)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Начало диалога"""
        user = update.message.from_user
        context.user_data.clear()

        reply_keyboard = [['Создать новый стикерсет', 'Добавить в существующий']]

        await update.message.reply_text(
            f"Привет, {user.first_name}! Я помогу тебе собрать стикерсет.\n"
            "Выбирай, что будем делать:",
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
            "Давай придумаем название для нового набора стикеров.",
            reply_markup=ReplyKeyboardRemove()
        )

        context.user_data.clear()
        context.user_data.update({
            'action': 'create_new',
            'stickers': []
        })
        return WAITING_NEW_TITLE

    async def add_to_existing(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Добавление стикера в существующий стикерсет"""
        await update.message.reply_text(
            "Добавляем стикер в существующий стикерсет. Сначала выберем подходящий набор 👇",
            reply_markup=ReplyKeyboardRemove()
        )

        context.user_data.clear()
        context.user_data['action'] = 'add_existing'
        return await self.show_existing_sets(update, context, page=0)

    async def handle_new_set_title(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка пользовательского названия нового стикерсета"""
        user_id = update.effective_user.id
        title = update.message.text.strip()

        if not title:
            await update.message.reply_text("Название не может быть пустым. Попробуй ещё раз.")
            return WAITING_NEW_TITLE

        context.user_data['title'] = title

        await update.message.reply_text(
            "Теперь пришли будущий стикер — файл в формате PNG, JPG или WebP. "
            "Рекомендуемое разрешение 512×512. Для лучшего качества отправь изображение как файл (без сжатия), "
            "а не как фотографию.\n\n"
            "Важно: пожалуйста, не загружай изображения, защищённые авторскими правами.",
            reply_markup=ReplyKeyboardRemove()
        )

        return WAITING_STICKER

    async def handle_sticker(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка присланного изображения"""
        user_data = context.user_data

        if 'action' not in user_data:
            await update.message.reply_text("Что-то пошло не так. Запусти процесс заново командой /start.")
            context.user_data.clear()
            return ConversationHandler.END

        try:
            # Получаем файл изображения
            if update.message and update.message.photo:
                photo_file = await update.message.photo[-1].get_file()
            elif update.message and update.message.document:
                photo_file = await update.message.document.get_file()
            else:
                await update.message.reply_text("Пришли, пожалуйста, изображение.")
                return WAITING_STICKER

            # Скачиваем изображение
            image_data = await photo_file.download_as_bytearray()

            # Для добавления в существующий набор убедимся, что набор выбран
            if user_data.get('action') == 'add_existing' and not user_data.get('selected_set'):
                await update.message.reply_text(
                    "Сначала выбери набор из списка, затем пришли изображение."
                )
                return await self.show_existing_sets(update, context, page=user_data.get('existing_page', 0))

            # Конвертируем в WebP
            webp_data = self.image_processor.convert_to_webp(bytes(image_data))

            # Сохраняем во временные данные пользователя
            user_data['current_webp'] = webp_data

            await update.message.reply_text(
                "Пришли смайл, который подходит к этому стикеру.",
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
        emoji = update.message.text
        user_data = context.user_data
        action = user_data.get('action')

        if not action or 'current_webp' not in user_data:
            await update.message.reply_text(
                "Не получилось сопоставить эмодзи с картинкой. Попробуй отправить стикер ещё раз."
            )
            return WAITING_STICKER

        if action == 'create_new':
            stickers = user_data.setdefault('stickers', [])
            stickers.append({
                'webp_data': user_data['current_webp'],
                'emoji': emoji
            })
            user_data.pop('current_webp', None)

            count = len(stickers)

            await update.message.reply_text(
                f"Стикер добавлен! Теперь в наборе {count} шт. "
                "Хочешь добавить ещё один — просто отправь файл в формате PNG, JPG или WebP.\n"
                "Когда закончишь, нажми кнопку «Готово».",
                reply_markup=ReplyKeyboardMarkup(
                    [['Готово']],
                    resize_keyboard=True,
                    one_time_keyboard=False
                )
            )

            return WAITING_DECISION

        if action == 'add_existing':
            user_data['emoji'] = emoji

            selected = user_data.get('selected_set')
            if not selected:
                await update.message.reply_text(
                    "Не удалось найти выбранный набор. Попробуй выбрать его снова."
                )
                return await self.show_existing_sets(update, context, page=user_data.get('existing_page', 0))

            success = await asyncio.to_thread(
                self.sticker_manager.add_sticker_to_set,
                user_id=update.effective_user.id,
                name=selected.get('name'),
                png_sticker=user_data.get('current_webp'),
                emojis=emoji
            )

            if success:
                title = selected.get('title') or selected.get('name')
                url = selected.get('url') or f"https://t.me/addstickers/{selected.get('name')}"
                added_count = user_data.get('added_count', 0) + 1
                user_data['added_count'] = added_count
                user_data.pop('current_webp', None)
                user_data.pop('emoji', None)

                await update.message.reply_text(
                    f'✅ Стикер успешно добавлен в набор <a href="{html.escape(url, quote=True)}">'
                    f'{html.escape(title)}</a>!',
                    reply_markup=ReplyKeyboardMarkup(
                        [['Готово']],
                        resize_keyboard=True,
                        one_time_keyboard=False
                    ),
                    parse_mode='HTML'
                )
                return WAITING_DECISION

            else:
                await update.message.reply_text(
                    "Не получилось добавить стикер. Попробуй снова или выбери другой набор.",
                    reply_markup=ReplyKeyboardRemove()
                )

            return await self.show_existing_sets(update, context, page=user_data.get('existing_page', 0))

        await update.message.reply_text("Не удалось обработать эмодзи. Попробуй ещё раз.")
        return WAITING_STICKER

    async def finish_sticker_collection(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Завершение добавления стикеров"""
        user_data = context.user_data
        action = user_data.get('action')

        if action == 'add_existing':
            context.user_data.clear()
            await update.message.reply_text(
                "Готово! Если захочешь добавить ещё, просто отправь /start.",
                reply_markup=ReplyKeyboardRemove()
            )
            return ConversationHandler.END

        if action == 'create_new':
            stickers = user_data.get('stickers', [])

            if not stickers:
                await update.message.reply_text(
                    "В наборе пока нет ни одного стикера. Сначала добавь хотя бы один."
                )
                return WAITING_STICKER

            await update.message.reply_text(
                "Теперь выбери короткое название, которое будет использоваться в адресе набора. "
                "Я сделаю ссылку, которой ты сможешь поделиться с друзьями и подписчиками.",
                reply_markup=ReplyKeyboardRemove()
            )

            return WAITING_SHORT_NAME

        context.user_data.clear()
        await update.message.reply_text(
            "Процесс не найден. Начни заново с /start.",
            reply_markup=ReplyKeyboardRemove()
        )
        return ConversationHandler.END

    async def prompt_waiting_for_more(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Подсказка пользователю, если ожидается файл или завершение"""
        message = "Чтобы продолжить, отправь файл следующего стикера или нажми кнопку «Готово», когда закончишь."
        user_data = context.user_data
        use_html = False
        if user_data.get('action') == 'add_existing':
            selected = user_data.get('selected_set')
            if selected:
                title = selected.get('title') or selected.get('name')
                url = selected.get('url') or f"https://t.me/addstickers/{selected.get('name')}"
                message = (
                    f'Добавляем в набор <a href="{html.escape(url, quote=True)}">{html.escape(title)}</a>.\n'
                    "Отправь следующий файл или нажми «Готово», когда закончишь."
                )
                use_html = True

        await update.message.reply_text(
            message,
            reply_markup=ReplyKeyboardMarkup(
                [['Готово']],
                resize_keyboard=True,
                one_time_keyboard=False
            ),
            parse_mode='HTML' if use_html else None
        )
        return WAITING_DECISION

    async def show_existing_sets(self, update: Update, context: ContextTypes.DEFAULT_TYPE, page: int) -> int:
        """Отображение списка существующих наборов пользователя"""
        user_id = update.effective_user.id
        user_data = context.user_data

        result = await asyncio.to_thread(
            self.gallery_client.get_user_sticker_sets,
            user_id=user_id,
            language=GALLERY_DEFAULT_LANGUAGE,
            page=page,
            size=10,
            sort='createdAt',
            direction='DESC',
            short_info=True
        )

        if result is None:
            await update.message.reply_text(
                "Не получилось загрузить список твоих наборов. Попробуй позже или начни заново с /start.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END

        items = result.get('content') or []
        if not items:
            await update.message.reply_text(
                "Похоже, у тебя пока нет наборов. Создай новый, а затем возвращайся, чтобы добавить в него стикер.",
                reply_markup=ReplyKeyboardRemove()
            )
            context.user_data.clear()
            return ConversationHandler.END

        current_page = result.get('page', page) or 0
        total_pages = result.get('totalPages', 1) or 1

        user_data['existing_sets'] = items
        user_data['existing_page'] = current_page
        user_data['existing_total_pages'] = total_pages
        user_data.pop('selected_set', None)

        text = (
            f"Выбери набор, куда добавить стикер.\n"
            f"Страница {current_page + 1} из {total_pages}"
        )

        keyboard = self._build_existing_sets_keyboard(items, current_page, total_pages)

        if update.callback_query:
            query = update.callback_query
            await query.edit_message_text(text=text, reply_markup=keyboard)
        else:
            await update.message.reply_text(text, reply_markup=keyboard)

        return WAITING_EXISTING_CHOICE

    def _build_existing_sets_keyboard(self, items, page, total_pages):
        """Формирует inline-клавиатуру выбора набора"""
        buttons = []

        row = []
        for index, item in enumerate(items):
            title = item.get('title') or item.get('name')
            row.append(
                InlineKeyboardButton(
                    text=title,
                    callback_data=f"set:{index}"
                )
            )
            if len(row) == 2:
                buttons.append(row)
                row = []
        if row:
            buttons.append(row)

        nav_buttons = []
        if page > 0:
            nav_buttons.append(InlineKeyboardButton(PAGE_PREV_LABEL, callback_data='page:prev'))
        if page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton(PAGE_NEXT_LABEL, callback_data='page:next'))
        if nav_buttons:
            buttons.append(nav_buttons)

        buttons.append([InlineKeyboardButton(CANCEL_LABEL, callback_data='action:cancel')])

        return InlineKeyboardMarkup(buttons)

    async def handle_existing_choice(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Обработка выбора существующего набора"""
        query = update.callback_query
        data = query.data
        user_data = context.user_data

        if not user_data or user_data.get('action') != 'add_existing':
            await query.answer()
            await query.edit_message_text(
                "Процесс добавления стикера не найден. Начни заново с /start."
            )
            context.user_data.clear()
            return ConversationHandler.END

        current_page = user_data.get('existing_page', 0)
        total_pages = user_data.get('existing_total_pages', 1)

        if data == 'action:cancel':
            await query.answer("Отменяем добавление.")
            await query.edit_message_text("Ок, отменяем. Если передумаешь — /start.")
            context.user_data.clear()
            return ConversationHandler.END

        if data == 'page:next':
            if current_page < total_pages - 1:
                await query.answer("Следующая страница")
                return await self.show_existing_sets(update, context, page=current_page + 1)
            await query.answer("Это последняя страница", show_alert=True)
            return WAITING_EXISTING_CHOICE

        if data == 'page:prev':
            if current_page > 0:
                await query.answer("Предыдущая страница")
                return await self.show_existing_sets(update, context, page=current_page - 1)
            await query.answer("Это первая страница", show_alert=True)
            return WAITING_EXISTING_CHOICE

        if data.startswith('set:'):
            index = int(data.split(':', 1)[1])
            sets = user_data.get('existing_sets', [])
            if 0 <= index < len(sets):
                target_set = sets[index]
                user_data['selected_set'] = target_set

                title = target_set.get('title') or target_set.get('name')
                url = target_set.get('url') or f"https://t.me/addstickers/{target_set.get('name')}"

                await query.answer(f"Выбрано: {title}")
                await query.edit_message_text(
                    f'Набор <a href="{html.escape(url, quote=True)}">{html.escape(title)}</a> выбран.\n'
                    "Теперь отправь изображение для стикера.",
                    parse_mode='HTML'
                )
                return WAITING_STICKER

        await query.answer("Не удалось обработать выбор", show_alert=True)
        return WAITING_EXISTING_CHOICE

    async def handle_existing_choice_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Подсказка, если пользователь отправил текст вместо использования кнопок"""
        await update.message.reply_text(
            "Пожалуйста, выбери набор с помощью кнопок ниже."
        )
        return WAITING_EXISTING_CHOICE


    async def handle_short_name(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Проверка короткого имени и создание стикерсета"""
        short_name = update.message.text.strip()
        user_data = context.user_data

        if not user_data or user_data.get('action') != 'create_new':
            await update.message.reply_text("Процесс создания набора не найден. Начни заново с /start.")
            return ConversationHandler.END

        if not re.fullmatch(r'[A-Za-z0-9_]{3,64}', short_name):
            await update.message.reply_text(
                "Имя может содержать только латинские буквы, цифры и подчёркивание. "
                "Минимум 3 символа. Попробуй другое."
            )
            return WAITING_SHORT_NAME

        full_name = f"{short_name}_by_{context.bot.username}"
        stickers = user_data.get('stickers', [])
        title = user_data.get('title')

        availability = await asyncio.to_thread(
            self.sticker_manager.is_sticker_set_available,
            full_name
        )

        if availability is None:
            await update.message.reply_text(
                "Не получилось проверить доступность имени. Попробуй позже или введи другое."
            )
            return WAITING_SHORT_NAME

        if not availability:
            await update.message.reply_text(
                "Такое короткое имя уже занято. Придумай другое."
            )
            return WAITING_SHORT_NAME

        if not stickers or not title:
            await update.message.reply_text("Недостаточно данных для создания стикерсета. Начни заново с /start.")
            context.user_data.clear()
            return ConversationHandler.END

        first_sticker = stickers[0]

        created = await asyncio.to_thread(
            self.sticker_manager.create_new_sticker_set,
            user_id=update.effective_user.id,
            name=full_name,
            title=title,
            png_sticker=first_sticker['webp_data'],
            emojis=first_sticker['emoji']
        )

        if not created:
            await update.message.reply_text(
                "Не получилось создать стикерсет. Попробуй выбрать другое короткое имя или начни заново."
            )
            return WAITING_SHORT_NAME

        failed_additions = 0
        for sticker in stickers[1:]:
            added = await asyncio.to_thread(
                self.sticker_manager.add_sticker_to_set,
                user_id=update.effective_user.id,
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
                "Ты можешь закинуть их вручную позже."
            )

        gallery_saved = False
        if self.gallery_client.is_configured():
            gallery_saved = await asyncio.to_thread(
                self.gallery_client.save_sticker_set,
                user_id=update.effective_user.id,
                sticker_set_link=sticker_set_link,
                title=title,
                is_public=False,
                language=GALLERY_DEFAULT_LANGUAGE,
            )

            if not gallery_saved:
                logger.warning(
                    "Не удалось сохранить стикерсет в галерее для пользователя %s",
                    update.effective_user.id
                )

        if gallery_saved:
            message += "\n\n✅ Я добавил этот набор в твою галерею."

        await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

        context.user_data.clear()
        return ConversationHandler.END

    async def cancel(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
        """Отмена диалога"""
        context.user_data.clear()

        await update.message.reply_text(
            "Диалог отменен. Используй /start чтобы начать заново.",
            reply_markup=ReplyKeyboardRemove()
        )

        return ConversationHandler.END

    async def error_handler(self, update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Глобальный обработчик ошибок"""
        logger.exception("Unhandled exception while processing update %s", update, exc_info=context.error)

        try:
            if update:
                message = getattr(update, 'effective_message', None)
                if message:
                    await message.reply_text("Ой, что-то пошло не так. Попробуй ещё раз чуть позже.")
                    return
                callback = getattr(update, 'callback_query', None)
                if callback:
                    await callback.answer("Случилась ошибка. Попробуй снова.", show_alert=True)
        except Exception as notify_error:
            logger.error("Failed to notify user about error: %s", notify_error)

    def run(self):
        """Запуск бота"""
        self.application.run_polling()


if __name__ == '__main__':
    bot = StickerBot()
    bot.run()