import asyncio
import logging
import json
from logging.handlers import RotatingFileHandler
from pathlib import Path
from datetime import datetime
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler, InlineQueryHandler,
    filters, ConversationHandler, ContextTypes
)

# #region agent log
DEBUG_LOG_PATH = Path(__file__).parent.parent.parent / '.cursor' / 'debug.log'
def _debug_log(location, message, data=None, hypothesis_id=None):
    try:
        DEBUG_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "timestamp": int(datetime.now().timestamp() * 1000),
            "location": location,
            "message": message,
            "data": data or {},
            "sessionId": "debug-session",
            "runId": "run1",
            "hypothesisId": hypothesis_id
        }
        with open(DEBUG_LOG_PATH, 'a', encoding='utf-8') as f:
            f.write(json.dumps(entry, ensure_ascii=False) + '\n')
    except Exception:
        pass
# #endregion
from src.config.settings import (
    BOT_TOKEN,
    GALLERY_BASE_URL,
    GALLERY_SERVICE_TOKEN,
    GALLERY_DEFAULT_LANGUAGE,
    LOG_FILE_PATH,
    SERVICE_BASE_URL,
    WEBHOOK_SECRET_TOKEN,
    WEBHOOK_PATH,
    MINIAPP_GALLERY_URL,
    WAVESPEED_API_KEY,
    FREE_DAILY_LIMIT,
    PREMIUM_DAILY_LIMIT,
    FREE_MAX_PER_10MIN,
    PREMIUM_MAX_PER_10MIN,
    COOLDOWN_SECONDS,
    PREMIUM_USER_IDS,
    PLACEHOLDER_STICKER_FILE_ID,
    PLACEHOLDER_STICKER_PATH,
    ADMIN_IDS,
    STICKERSET_CACHE_SIZE,
    STICKERSET_CACHE_TTL_DAYS,
    STICKERSET_CACHE_CLEANUP_INTERVAL_HOURS,
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
from src.bot.handlers.generation import handle_generate_callback, handle_regenerate_callback

# Импорты для WaveSpeed generation
from src.managers.wavespeed_client import WaveSpeedClient
from src.utils.in_memory_limits import PromptStore, RateLimiter
from src.utils.quota import (
    UserPlanResolver,
    DailyQuotaStore,
    RollingWindowStore,
    QuotaManager,
    Plan,
    QuotaConfig,
)
from src.utils.stickerset_cache import AsyncStickerSetCache

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
        # #region agent log
        _debug_log("bot/bot.py:__init__:entry", "Начало __init__ StickerBot", {}, "J")
        # #endregion
        try:
            # #region agent log
            _debug_log("bot/bot.py:__init__:before_validate", "Перед валидацией конфигурации", {}, "J")
            # #endregion
            self._validate_configuration()
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_validate", "Валидация конфигурации пройдена", {}, "J")
            # #endregion
            
            # #region agent log
            _debug_log("bot/bot.py:__init__:before_application", "Перед созданием Application", {}, "J")
            # #endregion
            self.application = Application.builder().token(BOT_TOKEN).build()
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_application", "Application создан", {}, "J")
            # #endregion
            
            # #region agent log
            _debug_log("bot/bot.py:__init__:before_services", "Перед созданием сервисов", {}, "J")
            # #endregion
            self.sticker_service = StickerService(BOT_TOKEN)
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_sticker_service", "StickerService создан", {}, "J")
            # #endregion
            self.image_service = ImageService()
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_image_service", "ImageService создан", {}, "J")
            # #endregion
            self.gallery_service = GalleryService(
                base_url=GALLERY_BASE_URL,
                service_token=GALLERY_SERVICE_TOKEN,
                default_language=GALLERY_DEFAULT_LANGUAGE,
            )
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_gallery_service", "GalleryService создан", {}, "J")
            # #endregion
            
            # Инициализация кэша стикерсетов
            self.stickerset_cache = AsyncStickerSetCache(
                max_size=STICKERSET_CACHE_SIZE,
                ttl_days=STICKERSET_CACHE_TTL_DAYS,
                cleanup_interval_hours=STICKERSET_CACHE_CLEANUP_INTERVAL_HOURS
            )
            logger.info("StickerSet cache initialized")

            # Инициализация компонентов для WaveSpeed generation
            # #region agent log
            _debug_log("bot/bot.py:__init__:before_generation", "Перед инициализацией компонентов генерации", {}, "J")
            # #endregion
            self._init_generation_components()
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_generation", "Компоненты генерации инициализированы", {}, "J")
            # #endregion

            # #region agent log
            _debug_log("bot/bot.py:__init__:before_handlers", "Перед setup_handlers", {}, "J")
            # #endregion
            self.setup_handlers()
            # #region agent log
            _debug_log("bot/bot.py:__init__:after_handlers", "Handlers настроены", {}, "J")
            # #endregion
            self._shutdown_event = asyncio.Event()
            # #region agent log
            _debug_log("bot/bot.py:__init__:success", "StickerBot инициализирован успешно", {}, "J")
            # #endregion
        except Exception as e:
            # #region agent log
            _debug_log("bot/bot.py:__init__:error", "Ошибка в __init__", {"error": str(e), "type": type(e).__name__}, "J")
            # #endregion
            raise
    
    def _init_generation_components(self):
        """Инициализация компонентов для генерации"""
        # PromptStore
        self.prompt_store = PromptStore()
        
        # RateLimiter
        self.rate_limiter = RateLimiter()
        
        # UserPlanResolver
        self.user_plan_resolver = UserPlanResolver(PREMIUM_USER_IDS)
        
        # DailyQuotaStore
        self.daily_quota_store = DailyQuotaStore()
        
        # RollingWindowStore
        self.rolling_window_store = RollingWindowStore()
        
        # QuotaConfigs
        configs = {
            Plan.FREE: QuotaConfig(
                daily_limit=FREE_DAILY_LIMIT,
                max_per_10min=FREE_MAX_PER_10MIN,
                cooldown_seconds=COOLDOWN_SECONDS,
                max_active=1,
            ),
            Plan.PREMIUM: QuotaConfig(
                daily_limit=PREMIUM_DAILY_LIMIT,
                max_per_10min=PREMIUM_MAX_PER_10MIN,
                cooldown_seconds=COOLDOWN_SECONDS,
                max_active=1,
            ),
        }
        
        # QuotaManager
        self.quota_manager = QuotaManager(
            rate_limiter=self.rate_limiter,
            daily_store=self.daily_quota_store,
            rolling_store=self.rolling_window_store,
            resolver=self.user_plan_resolver,
            configs=configs,
        )
        
        # WaveSpeedClient (если API key есть)
        self.wavespeed_client = None
        if WAVESPEED_API_KEY:
            try:
                self.wavespeed_client = WaveSpeedClient(WAVESPEED_API_KEY)
                logger.info("WaveSpeed generation enabled")
            except Exception as e:
                logger.error(f"Failed to initialize WaveSpeedClient: {e}")
        
        # Сохраняем в bot_data для доступа из handlers
        self.application.bot_data["prompt_store"] = self.prompt_store
        self.application.bot_data["quota_manager"] = self.quota_manager
        self.application.bot_data["wavespeed_client"] = self.wavespeed_client
        self.application.bot_data["sticker_service"] = self.sticker_service
        # placeholder_sticker_file_id будет загружен при старте бота

    @staticmethod
    def _validate_configuration():
        # #region agent log
        _debug_log("bot/bot.py:_validate_configuration:entry", "Начало валидации конфигурации", {}, "I")
        # #endregion
        missing = []

        # #region agent log
        _debug_log("bot/bot.py:_validate_configuration:checking", "Проверка переменных окружения", {
            "BOT_TOKEN": bool(BOT_TOKEN),
            "GALLERY_BASE_URL": bool(GALLERY_BASE_URL),
            "GALLERY_SERVICE_TOKEN": bool(GALLERY_SERVICE_TOKEN),
            "MINIAPP_GALLERY_URL": bool(MINIAPP_GALLERY_URL)
        }, "I")
        # #endregion

        if not BOT_TOKEN:
            missing.append('BOT_TOKEN')
        if not GALLERY_BASE_URL:
            missing.append('GALLERY_BASE_URL')
        if not GALLERY_SERVICE_TOKEN:
            missing.append('GALLERY_SERVICE_TOKEN')
        if not MINIAPP_GALLERY_URL:
            missing.append('MINIAPP_GALLERY_URL')

        if missing:
            # #region agent log
            _debug_log("bot/bot.py:_validate_configuration:missing", "Отсутствуют переменные окружения", {"missing": missing}, "I")
            # #endregion
            raise ValueError(
                f"Не заданы необходимые переменные окружения: {', '.join(missing)}. "
                "Проверь .env или окружение и перезапусти бота."
            )
        # #region agent log
        _debug_log("bot/bot.py:_validate_configuration:success", "Валидация конфигурации успешна", {}, "I")
        # #endregion

    def setup_handlers(self):
        # Создаем обертки для обработчиков с передачей сервисов
        async def wrapped_start(update, context):
            return await start(update, context)

        async def wrapped_create_new_set(update, context):
            return await create_new_set(update, context)

        async def wrapped_add_to_existing(update, context):
            return await add_to_existing(update, context, self.gallery_service)

        async def wrapped_manage_publication(update, context):
            return await manage_publication(update, context, self.gallery_service)

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
                update, context, self.gallery_service, self.sticker_service, self.stickerset_cache
            )

        async def wrapped_handle_sticker_in_main_menu(update, context):
            """Обработчик стикеров в главном меню"""
            return await handle_sticker_for_add_pack(
                update, context, self.gallery_service, self.sticker_service, self.stickerset_cache
            )

        async def wrapped_handle_sticker_before_start(update, context):
            """Обработчик стикеров до начала диалога (/start)"""
            user_data = context.user_data
            
            # Не обрабатываем стикеры, если пользователь в процессе создания или обновления стикерпака
            action = user_data.get('action')
            if action in ('create_new', 'add_existing'):
                # Пропускаем обработку, пусть ConversationHandler обработает
                return -1
            
            # Также проверяем, есть ли признаки активного процесса
            if user_data.get('selected_set') or user_data.get('current_webp'):
                return -1
            
            # Обрабатываем стикер так же, как в главном меню
            result = await handle_sticker_for_add_pack(
                update, context, self.gallery_service, self.sticker_service, self.stickerset_cache
            )
            return result

        async def wrapped_handle_add_to_gallery(update, context):
            logger.info(f"wrapped_handle_add_to_gallery called with callback_data: {update.callback_query.data if update.callback_query else 'None'}")
            return await handle_add_to_gallery(
                update, context, self.gallery_service, self.stickerset_cache
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
                    MessageHandler(filters.PHOTO | filters.Document.ALL | filters.Sticker.ALL, wrapped_handle_sticker)
                ],
                WAITING_EMOJI: [
                    MessageHandler(filters.TEXT & ~filters.COMMAND, wrapped_handle_emoji)
                ],
                WAITING_DECISION: [
                    MessageHandler(filters.Regex('^(Готово|Завершить набор)$'), wrapped_finish_sticker_collection),
                    MessageHandler(filters.PHOTO | filters.Document.ALL | filters.Sticker.ALL, wrapped_handle_sticker),
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
            fallbacks=[
                CommandHandler('cancel', cancel),
                # Добавляем обработчик кнопки в fallbacks, чтобы он срабатывал в любом состоянии
                CallbackQueryHandler(wrapped_handle_add_to_gallery, pattern='^add_to_gallery:'),
            ],
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
        
        # Обработчик кнопки "Добавить в галерею" на уровне application,
        # чтобы он срабатывал независимо от состояния ConversationHandler
        add_to_gallery_handler = CallbackQueryHandler(
            wrapped_handle_add_to_gallery,
            pattern='^add_to_gallery:'
        )
        self.application.add_handler(add_to_gallery_handler)
        
        # InlineQueryHandler вне ConversationHandler, на уровне application
        self.application.add_handler(InlineQueryHandler(wrapped_handle_inline_query))
        
        # Handlers для генерации (вне ConversationHandler)
        if self.wavespeed_client:
            gen_handler = CallbackQueryHandler(
                handle_generate_callback,
                pattern='^gen:'
            )
            self.application.add_handler(gen_handler)
            
            regen_handler = CallbackQueryHandler(
                handle_regenerate_callback,
                pattern='^regen:'
            )
            self.application.add_handler(regen_handler)
        
        self.application.add_error_handler(error_handler)

    async def _load_placeholder_sticker(self):
        """Загрузить placeholder стикер и сохранить file_id"""
        from pathlib import Path
        from telegram import InputFile
        
        logger.info("Loading placeholder sticker...")
        
        if PLACEHOLDER_STICKER_FILE_ID:
            # Используем существующий file_id
            self.application.bot_data["placeholder_sticker_file_id"] = PLACEHOLDER_STICKER_FILE_ID
            logger.info(f"Using existing placeholder sticker file_id from config: {PLACEHOLDER_STICKER_FILE_ID[:20]}...")
            # Проверяем, что file_id сохранен
            loaded_file_id = self.application.bot_data.get("placeholder_sticker_file_id")
            if loaded_file_id:
                logger.info(f"Successfully set placeholder sticker file_id: {loaded_file_id[:20]}...")
            else:
                logger.error("Failed to set placeholder sticker file_id in bot_data")
            return
        
        # Загружаем файл в Telegram
        sticker_path = Path(PLACEHOLDER_STICKER_PATH)
        logger.info(f"Checking placeholder sticker file at: {sticker_path}")
        logger.info(f"Absolute path: {sticker_path.absolute()}")
        
        if not sticker_path.exists():
            logger.warning(f"Placeholder sticker file not found: {sticker_path}. Absolute path: {sticker_path.absolute()}")
            self.application.bot_data["placeholder_sticker_file_id"] = None
            return
        
        try:
            # Читаем файл
            logger.info(f"Reading sticker file: {sticker_path}")
            with open(sticker_path, 'rb') as f:
                sticker_bytes = f.read()
            logger.info(f"Sticker file read successfully, size: {len(sticker_bytes)} bytes")
            
            # Для загрузки стикера нужен стикерсет и user_id
            # Используем первого админа, если есть
            if not ADMIN_IDS:
                logger.warning("No admin IDs configured, cannot load placeholder sticker. Set PLACEHOLDER_STICKER_FILE_ID manually.")
                self.application.bot_data["placeholder_sticker_file_id"] = None
                return
            
            user_id = ADMIN_IDS[0]
            logger.info(f"Using admin user_id: {user_id} for placeholder sticker upload")
            
            # Создаем временный стикерсет для placeholder
            # Имя стикерсета должно быть уникальным, используем timestamp
            import time
            sticker_set_name = f"stixly_placeholder_{int(time.time())}_by_{self.application.bot.username}"
            logger.info(f"Creating placeholder sticker set: {sticker_set_name}")
            
            # Создаем стикерсет с placeholder стикером
            sticker_file = InputFile(sticker_bytes, filename="placeholder.webp")
            try:
                logger.info("Calling create_new_sticker_set...")
                await self.application.bot.create_new_sticker_set(
                    user_id=user_id,
                    name=sticker_set_name,
                    title="STIXLY Placeholder",
                    sticker=sticker_file,
                    emoji="⏳"
                )
                logger.info("Sticker set created successfully")
                
                # Получаем file_id из стикерсета
                logger.info(f"Getting sticker set: {sticker_set_name}")
                sticker_set = await self.application.bot.get_sticker_set(sticker_set_name)
                if sticker_set.stickers:
                    file_id = sticker_set.stickers[0].file_id
                    self.application.bot_data["placeholder_sticker_file_id"] = file_id
                    logger.info(f"Placeholder sticker loaded, file_id: {file_id[:20]}...")
                else:
                    logger.error("Placeholder sticker set created but no stickers found")
                    self.application.bot_data["placeholder_sticker_file_id"] = None
            except Exception as create_error:
                error_type = type(create_error).__name__
                error_msg = str(create_error)
                logger.error(
                    f"Failed to create placeholder sticker set: {error_type}: {error_msg}",
                    exc_info=True
                )
                
                # Даем рекомендации в зависимости от типа ошибки
                if "STICKERSET_INVALID" in error_msg or "name" in error_msg.lower():
                    logger.warning(
                        "Sticker set name might be invalid. Try setting PLACEHOLDER_STICKER_FILE_ID manually "
                        "by uploading the sticker to Telegram and getting its file_id."
                    )
                elif "user" in error_msg.lower() or "USER" in error_msg:
                    logger.warning(
                        f"User-related error. Make sure admin user_id {user_id} has interacted with the bot "
                        "and can create sticker sets. Alternatively, set PLACEHOLDER_STICKER_FILE_ID manually."
                    )
                else:
                    logger.warning(
                        "To fix this, you can manually upload the placeholder sticker to Telegram, "
                        "get its file_id, and set PLACEHOLDER_STICKER_FILE_ID in your .env file."
                    )
                
                self.application.bot_data["placeholder_sticker_file_id"] = None
        except FileNotFoundError as file_error:
            logger.error(
                f"Placeholder sticker file not found: {file_error}. "
                f"Expected path: {PLACEHOLDER_STICKER_PATH}. "
                "Set PLACEHOLDER_STICKER_FILE_ID manually or ensure the file exists."
            )
            self.application.bot_data["placeholder_sticker_file_id"] = None
        except PermissionError as perm_error:
            logger.error(
                f"Permission denied reading placeholder sticker file: {perm_error}. "
                "Check file permissions or set PLACEHOLDER_STICKER_FILE_ID manually."
            )
            self.application.bot_data["placeholder_sticker_file_id"] = None
        except Exception as e:
            error_type = type(e).__name__
            error_msg = str(e)
            logger.error(
                f"Failed to load placeholder sticker: {error_type}: {error_msg}",
                exc_info=True
            )
            logger.warning(
                "Placeholder sticker loading failed. Inline query will use text fallback. "
                "To fix: set PLACEHOLDER_STICKER_FILE_ID in .env with a valid sticker file_id."
            )
            self.application.bot_data["placeholder_sticker_file_id"] = None
        
        # Проверяем результат загрузки
        loaded_file_id = self.application.bot_data.get("placeholder_sticker_file_id")
        if loaded_file_id:
            logger.info(f"Successfully loaded placeholder sticker, file_id: {loaded_file_id[:20]}...")
        else:
            logger.error("Failed to load placeholder sticker - file_id is None. Inline query will use text fallback.")

    async def run_polling(self):
        """Запуск бота в режиме polling"""
        logger.info("Запуск бота в режиме polling")
        try:
            # Инициализация и запуск
            await self.application.initialize()
            await self.application.start()
            
            # Загружаем placeholder стикер
            await self._load_placeholder_sticker()
            
            # Проверяем, что placeholder_file_id сохранен
            placeholder_file_id = self.application.bot_data.get("placeholder_sticker_file_id")
            if placeholder_file_id:
                logger.info(f"Placeholder sticker ready: file_id={placeholder_file_id[:20]}...")
            else:
                logger.warning(
                    "Placeholder sticker not loaded. Inline query will use text fallback. "
                    "To fix: set PLACEHOLDER_STICKER_FILE_ID in .env or ensure "
                    f"PLACEHOLDER_STICKER_PATH points to a valid file: {PLACEHOLDER_STICKER_PATH}"
                )
            
            # Запускаем фоновую задачу очистки кэша
            await self.stickerset_cache.start_cleanup_task()
            logger.info("Sticker set cache cleanup task started")
            
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
        if not SERVICE_BASE_URL:
            raise ValueError("SERVICE_BASE_URL не установлен в переменных окружения")
        
        logger.info(f"Запуск бота в режиме webhook: {SERVICE_BASE_URL}")
        try:
            # Инициализация
            await self.application.initialize()
            await self.application.start()
            
            # Загружаем placeholder стикер
            await self._load_placeholder_sticker()
            
            # Проверяем, что placeholder_file_id сохранен
            placeholder_file_id = self.application.bot_data.get("placeholder_sticker_file_id")
            if placeholder_file_id:
                logger.info(f"Placeholder sticker ready: file_id={placeholder_file_id[:20]}...")
            else:
                logger.warning(
                    "Placeholder sticker not loaded. Inline query will use text fallback. "
                    "To fix: set PLACEHOLDER_STICKER_FILE_ID in .env or ensure "
                    f"PLACEHOLDER_STICKER_PATH points to a valid file: {PLACEHOLDER_STICKER_PATH}"
                )
            
            # Запускаем фоновую задачу очистки кэша
            await self.stickerset_cache.start_cleanup_task()
            logger.info("Sticker set cache cleanup task started")
            
            # Устанавливаем экземпляр бота в webhook endpoint после инициализации
            # чтобы гарантировать, что application полностью готов
            from src.api.routes.webhook import set_bot_instance as set_webhook_bot_instance
            set_webhook_bot_instance(self)
            logger.info("Экземпляр бота установлен в webhook endpoint после инициализации")
            
            # Используем путь из настроек (по умолчанию /webhook)
            # Убеждаемся, что путь начинается с /
            webhook_path = WEBHOOK_PATH if WEBHOOK_PATH.startswith('/') else f'/{WEBHOOK_PATH}'
            full_webhook_url = f"{SERVICE_BASE_URL.rstrip('/')}{webhook_path}"
            
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
            # Останавливаем фоновую задачу кэша
            if self.stickerset_cache:
                try:
                    await self.stickerset_cache.stop_cleanup_task()
                    logger.info("Sticker set cache cleanup task stopped")
                except Exception as e:
                    logger.warning(f"Error stopping cache cleanup task: {e}")
            
            # Закрываем WaveSpeedClient если есть
            if self.wavespeed_client:
                try:
                    await self.wavespeed_client.close()
                except Exception as e:
                    logger.warning(f"Error closing WaveSpeedClient: {e}")
            
            if self.application.updater.running:
                await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            logger.info("Бот успешно остановлен")
        except Exception as e:
            logger.error(f"Ошибка при остановке бота: {e}")

