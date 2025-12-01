import asyncio
import logging
from logging.handlers import RotatingFileHandler
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler,
    filters, ConversationHandler, ContextTypes
)
from src.config.settings import (
    BOT_TOKEN,
    GALLERY_BASE_URL,
    GALLERY_SERVICE_TOKEN,
    GALLERY_DEFAULT_LANGUAGE,
    LOG_FILE_PATH,
    WEBHOOK_URL,
    WEBHOOK_SECRET_TOKEN,
    WEBHOOK_PATH,
    MINIAPP_GALLERY_URL,
)
from src.services.sticker_service import StickerService
from src.services.image_service import ImageService
from src.services.gallery_service import GalleryService
from src.bot.states import (
    CHOOSING_ACTION,
    WAITING_NEW_TITLE,
    WAITING_STICKER,
    WAITING_EMOJI,
    WAITING_DECISION,
    WAITING_SHORT_NAME,
    WAITING_EXISTING_CHOICE,
    WAITING_PUBLISH_DECISION,
    WAITING_MANAGE_CHOICE,
    WAITING_STICKER_PACK_LINK,
)
from src.bot.handlers.start import start, handle_manage_stickers_menu, handle_back_to_main
from src.bot.handlers.create_set import (
    create_new_set,
    handle_new_set_title,
    handle_emoji_for_create,
    finish_sticker_collection_for_create,
    handle_short_name,
)
from src.bot.handlers.add_existing import (
    add_to_existing,
    show_existing_sets,
    handle_existing_choice,
    handle_existing_choice_text,
    handle_emoji_for_add_existing,
    finish_sticker_collection_for_add_existing,
    prompt_waiting_for_more,
)
from src.bot.handlers.manage_pub import (
    manage_publication,
    show_manage_sets,
    handle_manage_choice,
    handle_manage_choice_text,
    handle_publish_choice,
    handle_publish_choice_text,
)
from src.bot.handlers.sticker_common import handle_sticker
from src.bot.handlers.common import cancel, error_handler
from src.bot.handlers.add_pack_from_sticker import handle_sticker_for_add_pack, handle_add_to_gallery
from src.bot.handlers.inline import handle_inline_query

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
        self.sticker_service = StickerService(BOT_TOKEN)
        self.image_service = ImageService()
        self.gallery_service = GalleryService(
            base_url=GALLERY_BASE_URL,
            service_token=GALLERY_SERVICE_TOKEN,
            default_language=GALLERY_DEFAULT_LANGUAGE,
        )

        self.setup_handlers()
        self._shutdown_event = asyncio.Event()

    @staticmethod
    def _validate_configuration():
        missing = []

        if not BOT_TOKEN:
            missing.append('BOT_TOKEN')
        if not GALLERY_BASE_URL:
            missing.append('GALLERY_BASE_URL')
        if not GALLERY_SERVICE_TOKEN:
            missing.append('GALLERY_SERVICE_TOKEN')
        if not MINIAPP_GALLERY_URL:
            missing.append('MINIAPP_GALLERY_URL')

        if missing:
            raise ValueError(
                f"Не заданы необходимые переменные окружения: {', '.join(missing)}. "
                "Проверь .env или окружение и перезапусти бота."
            )

    def setup_handlers(self):
        # Создаем обертки для обработчиков с передачей сервисов
        async def wrapped_start(update, context):
            return await start(update, context)

        async def wrapped_create_new_set(update, context):
            return await create_new_set(update, context)

        async def wrapped_add_to_existing(update, context):
            return await add_to_existing(update, context)

        async def wrapped_manage_publication(update, context):
            return await manage_publication(update, context)

        async def wrapped_handle_new_set_title(update, context):
            return await handle_new_set_title(update, context)

        async def wrapped_handle_sticker(update, context):
            return await handle_sticker(
                update,
                context,
                self.image_service,
                show_existing_sets_func=lambda u, c, page: show_existing_sets(u, c, page, self.gallery_service)
            )

        async def wrapped_handle_emoji(update, context):
            action = context.user_data.get('action')
            if action == 'create_new':
                return await handle_emoji_for_create(update, context, self.image_service)
            elif action == 'add_existing':
                return await handle_emoji_for_add_existing(
                    update, context, self.sticker_service, self.gallery_service
                )
            return WAITING_STICKER

        async def wrapped_finish_sticker_collection(update, context):
            action = context.user_data.get('action')
            if action == 'create_new':
                return await finish_sticker_collection_for_create(update, context)
            elif action == 'add_existing':
                return await finish_sticker_collection_for_add_existing(update, context)
            return -1

        async def wrapped_prompt_waiting_for_more(update, context):
            return await prompt_waiting_for_more(update, context)

        async def wrapped_handle_short_name(update, context):
            return await handle_short_name(
                update, context, self.sticker_service, self.gallery_service
            )

        async def wrapped_show_existing_sets(update, context, page):
            return await show_existing_sets(update, context, page, self.gallery_service)

        async def wrapped_handle_existing_choice(update, context):
            return await handle_existing_choice(
                update, context, self.sticker_service, self.gallery_service
            )

        async def wrapped_handle_existing_choice_text(update, context):
            return await handle_existing_choice_text(update, context)

        async def wrapped_show_manage_sets(update, context, page):
            return await show_manage_sets(update, context, page, self.gallery_service)

        async def wrapped_handle_manage_choice(update, context):
            return await handle_manage_choice(update, context, self.gallery_service)

        async def wrapped_handle_manage_choice_text(update, context):
            return await handle_manage_choice_text(update, context)

        async def wrapped_handle_publish_choice(update, context):
            return await handle_publish_choice(update, context, self.gallery_service)

        async def wrapped_handle_publish_choice_text(update, context):
            return await handle_publish_choice_text(update, context)

        async def wrapped_handle_manage_stickers_menu(update, context):
            return await handle_manage_stickers_menu(update, context)

        async def wrapped_handle_back_to_main(update, context):
            return await handle_back_to_main(update, context)

        async def wrapped_handle_manage_callback(update, context):
            """Обработчик для callback-кнопок из подменю управления стикерами"""
            query = update.callback_query
            await query.answer()

            data = query.data
            
            # Удаляем сообщение с меню
            try:
                await query.message.delete()
            except:
                pass

            # Создаем синтетический update с message для совместимости
            class SyntheticUpdate:
                def __init__(self, original_update, message):
                    self.effective_user = original_update.effective_user
                    self.effective_chat = original_update.effective_chat
                    self.message = message
                    self.callback_query = None

            synthetic_message = query.message
            synthetic_update = SyntheticUpdate(update, synthetic_message)

            if data == 'manage:create_new':
                return await wrapped_create_new_set(synthetic_update, context)
            elif data == 'manage:add_existing':
                return await wrapped_add_to_existing(synthetic_update, context)
            elif data == 'manage:publication':
                return await wrapped_manage_publication(synthetic_update, context)

            return CHOOSING_ACTION

        async def wrapped_handle_sticker_for_add_pack(update, context):
            return await handle_sticker_for_add_pack(
                update, context, self.gallery_service, self.sticker_service
            )

        async def wrapped_handle_sticker_in_main_menu(update, context):
            """Обработчик стикеров в главном меню"""
            return await handle_sticker_for_add_pack(
                update, context, self.gallery_service, self.sticker_service
            )

        async def wrapped_handle_sticker_before_start(update, context):
            """Обработчик стикеров до начала диалога (/start)"""
            # Обрабатываем стикер так же, как в главном меню
            result = await handle_sticker_for_add_pack(
                update, context, self.gallery_service, self.sticker_service
            )
            return result

        async def wrapped_handle_add_to_gallery(update, context):
            return await handle_add_to_gallery(
                update, context, self.gallery_service
            )

        async def wrapped_handle_inline_query(update, context):
            return await handle_inline_query(
                update, context, self.gallery_service
            )

        conv_handler = ConversationHandler(
            entry_points=[CommandHandler('start', wrapped_start)],
            states={
                CHOOSING_ACTION: [
                    MessageHandler(filters.Regex('^(Создать новый стикерсет)$'), wrapped_create_new_set),
                    MessageHandler(filters.Regex('^(Добавить в существующий)$'), wrapped_add_to_existing),
                    MessageHandler(filters.Regex('^(Управлять публикацией)$'), wrapped_manage_publication),
                    MessageHandler(filters.Sticker.ALL, wrapped_handle_sticker_in_main_menu),
                    CallbackQueryHandler(wrapped_handle_add_to_gallery, pattern='^add_to_gallery:'),
                    CallbackQueryHandler(wrapped_handle_manage_stickers_menu, pattern='^manage_stickers_menu$'),
                    CallbackQueryHandler(wrapped_handle_back_to_main, pattern='^back_to_main$'),
                    CallbackQueryHandler(wrapped_handle_manage_callback, pattern='^manage:(create_new|add_existing|publication)$'),
                ],
                WAITING_NEW_TITLE: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_new_set_title)
                ],
                WAITING_STICKER: [
                    MessageHandler(filters.PHOTO | filters.Document.ALL, wrapped_handle_sticker)
                ],
                WAITING_EMOJI: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_emoji)
                ],
                WAITING_DECISION: [
                    MessageHandler(filters.Regex('^(Готово|Завершить набор)$'), wrapped_finish_sticker_collection),
                    MessageHandler(filters.PHOTO | filters.Document.ALL, wrapped_handle_sticker),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_prompt_waiting_for_more)
                ],
                WAITING_SHORT_NAME: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_short_name)
                ],
                WAITING_EXISTING_CHOICE: [
                    CallbackQueryHandler(wrapped_handle_existing_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_existing_choice_text)
                ],
                WAITING_PUBLISH_DECISION: [
                    CallbackQueryHandler(wrapped_handle_publish_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_publish_choice_text),
                ],
                WAITING_MANAGE_CHOICE: [
                    CallbackQueryHandler(wrapped_handle_manage_choice),
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_manage_choice_text),
                ],
                WAITING_STICKER_PACK_LINK: [
                    MessageHandler(filters.Sticker.ALL, wrapped_handle_sticker_for_add_pack),
                ],
            },
            fallbacks=[CommandHandler('cancel', cancel)],
            allow_reentry=True
        )

        # Добавляем обработчик стикеров для нулевого состояния (до /start)
        # Этот обработчик должен быть добавлен ПЕРЕД ConversationHandler,
        # чтобы перехватывать стикеры до начала диалога
        sticker_handler_before_start = MessageHandler(
            filters.Sticker.ALL,
            wrapped_handle_sticker_before_start
        )
        self.application.add_handler(sticker_handler_before_start)

        self.application.add_handler(conv_handler)
        
        # InlineQueryHandler вне ConversationHandler, на уровне application
        self.application.add_handler(InlineQueryHandler(wrapped_handle_inline_query))
        
        self.application.add_error_handler(error_handler)

    async def run_polling(self):
        """Запуск бота в режиме polling"""
        logger.info("Запуск бота в режиме polling")
        try:
            # Инициализация и запуск
            await self.application.initialize()
            await self.application.start()
            
            # Удаляем webhook перед запуском polling
            logger.info("Удаление webhook перед запуском polling...")
            await self.application.bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook удален")
            
            # Указываем allowed_updates для inline_query
            allowed_updates = ["inline_query", "message", "callback_query"]
            logger.info(f"Starting polling with allowed_updates={allowed_updates}")
            await self.application.updater.start_polling(allowed_updates=allowed_updates)
            
            # После start_polling() polling работает в фоне
            # Просто ждем сигнала остановки
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Ошибка при работе бота в режиме polling: {e}")
            raise
        finally:
            await self._shutdown()
    
    async def run_webhook(self):
        """Запуск бота в режиме webhook"""
        if not WEBHOOK_URL:
            raise ValueError("WEBHOOK_URL не установлен в переменных окружения")
        
        logger.info(f"Запуск бота в режиме webhook: {WEBHOOK_URL}")
        try:
            # Инициализация
            await self.application.initialize()
            await self.application.start()
            
            # Устанавливаем экземпляр бота в webhook endpoint после инициализации
            # чтобы гарантировать, что application полностью готов
            from src.api.routes.webhook import set_bot_instance as set_webhook_bot_instance
            set_webhook_bot_instance(self)
            logger.info("Экземпляр бота установлен в webhook endpoint после инициализации")
            
            # Используем путь из настроек (по умолчанию /webhook)
            # Убеждаемся, что путь начинается с /
            webhook_path = WEBHOOK_PATH if WEBHOOK_PATH.startswith('/') else f'/{WEBHOOK_PATH}'
            full_webhook_url = f"{WEBHOOK_URL.rstrip('/')}{webhook_path}"
            
            # Проверяем наличие секретного токена
            if not WEBHOOK_SECRET_TOKEN:
                logger.warning(
                    "WEBHOOK_SECRET_TOKEN не установлен! "
                    "Webhook будет работать без защиты. Рекомендуется установить токен."
                )
                result = await self.application.bot.set_webhook(
                    url=full_webhook_url,
                    allowed_updates=["inline_query", "message", "callback_query"]  # Явно указываем inline_query
                )
                logger.info(f"Результат установки webhook: {result}, allowed_updates=['inline_query', 'message', 'callback_query']")
            else:
                # Устанавливаем webhook с секретным токеном
                # allowed_updates по умолчанию включает все типы, включая inline_query
                result = await self.application.bot.set_webhook(
                    url=full_webhook_url,
                    secret_token=WEBHOOK_SECRET_TOKEN,
                    allowed_updates=["inline_query", "message", "callback_query"]  # Явно указываем inline_query
                )
                logger.info(
                    f"Webhook установлен: {full_webhook_url} "
                    f"с секретным токеном (первые 10 символов): {WEBHOOK_SECRET_TOKEN[:10]}... "
                    f"allowed_updates=['inline_query', 'message', 'callback_query']"
                )
                logger.info(f"Результат установки webhook: {result}")
            
            # Проверяем информацию о webhook для диагностики
            webhook_info = await self.application.bot.get_webhook_info()
            logger.info(f"Информация о webhook от Telegram: {webhook_info}")
            
            if webhook_info.url != full_webhook_url:
                logger.warning(
                    f"Несоответствие URL webhook! "
                    f"Установлен: {full_webhook_url}, "
                    f"Telegram сообщает: {webhook_info.url}"
                )
            
            # Проверяем наличие ошибок
            if webhook_info.last_error_message:
                logger.error(
                    f"ОШИБКА WEBHOOK! Telegram не может доставить обновления:\n"
                    f"  - Ошибка: {webhook_info.last_error_message}\n"
                    f"  - Дата ошибки: {webhook_info.last_error_date}\n"
                    f"  - Ожидающих обновлений: {webhook_info.pending_update_count}\n"
                    f"  - IP адрес: {webhook_info.ip_address}"
                )
                
                # Если ошибка SSL, даем рекомендации
                if 'SSL' in webhook_info.last_error_message or 'certificate' in webhook_info.last_error_message.lower():
                    logger.error(
                        "⚠️  ПРОБЛЕМА С SSL СЕРТИФИКАТОМ!\n"
                        "Telegram не может проверить SSL сертификат вашего сервера.\n"
                        "Решения:\n"
                        "1. Проверьте настройки SSL на Amvera - сертификат должен быть валидным\n"
                        "2. Убедитесь, что домен правильно настроен в настройках Amvera\n"
                        "3. Проверьте, что промежуточные сертификаты настроены правильно\n"
                        "4. Попробуйте переустановить webhook после исправления SSL"
                    )
            
            if webhook_info.pending_update_count > 0:
                logger.warning(
                    f"ВНИМАНИЕ: {webhook_info.pending_update_count} обновлений ожидают доставки. "
                    "Проверьте логи на наличие ошибок."
                )
            
            # В webhook режиме не нужно запускать отдельный сервер,
            # обновления будут обрабатываться через FastAPI endpoint
            # Просто ждем сигнала остановки
            await self._shutdown_event.wait()
            
        except Exception as e:
            logger.error(f"Ошибка при работе бота в режиме webhook: {e}")
            raise
        finally:
            await self._shutdown()
    
    async def stop(self):
        """Остановка бота (graceful shutdown)"""
        logger.info("Получен сигнал остановки бота")
        self._shutdown_event.set()
    
    async def _shutdown(self):
        """Внутренний метод для завершения работы бота"""
        try:
            if self.application.updater.running:
                await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Бот успешно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")

