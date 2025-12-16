"""Handlers для inline generation через WaveSpeed"""
import asyncio
import io
import logging
import time
import random
from typing import Optional, Union
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputMediaDocument, InputFile
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from src.config.settings import (
    WAVESPEED_MAX_POLL_SECONDS,
    WAVESPEED_BG_REMOVE_ENABLED,
)
from src.services.sticker_service import StickerService

logger = logging.getLogger(__name__)


def log_task_exception(task: asyncio.Task):
    """Callback для логирования исключений фоновой задачи"""
    try:
        exc = task.exception()
        if exc:
            logger.exception("Generation task failed", exc_info=exc)
    except Exception as e:
        logger.error(f"Error in task exception callback: {e}")


async def save_sticker_to_user_set(
    user_id: int,
    user_username: Optional[str],
    bot_username: str,
    png_bytes: bytes,
    sticker_service: StickerService,
    context: ContextTypes.DEFAULT_TYPE,
) -> Optional[str]:
    """Сохраняет PNG стикер в стикерсет пользователя и возвращает file_id"""
    logger.info(f"[save_sticker_to_user_set] START: user_id={user_id}, username={user_username}, "
                f"bot_username={bot_username}, png_size={len(png_bytes)} bytes")
    try:
        # Формируем имя стикерсета из username пользователя
        if user_username:
            short_name = user_username
            logger.debug(f"[save_sticker_to_user_set] Using username as short_name: {short_name}")
        else:
            short_name = f"user_{user_id}"
            logger.debug(f"[save_sticker_to_user_set] No username, using fallback: {short_name}")
        
        full_name = f"{short_name}_by_{bot_username}"
        logger.info(f"[save_sticker_to_user_set] Sticker set name: {full_name}")
        
        # Проверяем существование стикерсета
        logger.debug(f"[save_sticker_to_user_set] Checking sticker set availability: {full_name}")
        availability = await asyncio.to_thread(
            sticker_service.is_sticker_set_available,
            full_name
        )
        logger.debug(f"[save_sticker_to_user_set] Availability check result: {availability}")
        
        if availability is None:
            logger.warning(f"[save_sticker_to_user_set] Could not check sticker set availability for {full_name}, trying to create")
            # Пробуем создать новый
            availability = True
        
        # Создаем или добавляем стикер
        if availability:
            # Стикерсет не существует - создаем новый
            logger.info(f"[save_sticker_to_user_set] Creating new sticker set: {full_name}")
            result = await asyncio.to_thread(
                sticker_service.create_new_sticker_set,
                user_id=user_id,
                name=full_name,
                title="STIXLY Generated",
                png_sticker=png_bytes,
                emojis="🎨"
            )
            
            if not result:
                logger.error(f"[save_sticker_to_user_set] Failed to create sticker set: {full_name}")
                return None
            logger.info(f"[save_sticker_to_user_set] Sticker set created successfully: {full_name}")
        else:
            # Стикерсет существует - добавляем стикер
            logger.info(f"[save_sticker_to_user_set] Adding sticker to existing set: {full_name}")
            success = await asyncio.to_thread(
                sticker_service.add_sticker_to_set,
                user_id=user_id,
                name=full_name,
                png_sticker=png_bytes,
                emojis="🎨"
            )
            
            if not success:
                logger.error(f"[save_sticker_to_user_set] Failed to add sticker to set: {full_name}")
                return None
            logger.info(f"[save_sticker_to_user_set] Sticker added successfully to: {full_name}")
        
        # Получаем file_id стикера из стикерсета
        logger.debug(f"[save_sticker_to_user_set] Fetching sticker set to get file_id: {full_name}")
        try:
            sticker_set = await context.bot.get_sticker_set(full_name)
            logger.debug(f"[save_sticker_to_user_set] Sticker set fetched, stickers count: {len(sticker_set.stickers) if sticker_set.stickers else 0}")
            if not sticker_set.stickers:
                logger.error(f"[save_sticker_to_user_set] Sticker set {full_name} has no stickers")
                return None
            
            # Возвращаем file_id последнего стикера (только что добавленного)
            sticker_file_id = sticker_set.stickers[-1].file_id
            logger.info(f"[save_sticker_to_user_set] SUCCESS: Saved sticker to {full_name}, "
                       f"file_id: {sticker_file_id[:20]}..., total stickers: {len(sticker_set.stickers)}")
            return sticker_file_id
            
        except Exception as e:
            logger.error(f"[save_sticker_to_user_set] ERROR: Failed to get sticker set {full_name}: {e}", exc_info=True)
            return None
            
    except Exception as e:
        logger.error(f"[save_sticker_to_user_set] ERROR: Exception in save_sticker_to_user_set: {e}", exc_info=True)
        return None


async def handle_generate_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Обработчик callback_query для генерации (паттерн ^gen:)"""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Парсим prompt_hash
    if not callback_data.startswith("gen:"):
        logger.warning(f"Invalid callback_data: {callback_data}")
        return
    
    prompt_hash = callback_data[4:]  # Убираем "gen:"
    
    # Получаем компоненты из bot_data
    prompt_store = context.bot_data.get("prompt_store")
    quota_manager = context.bot_data.get("quota_manager")
    wavespeed_client = context.bot_data.get("wavespeed_client")
    
    if not all([prompt_store, quota_manager, wavespeed_client]):
        logger.error("Missing required components in bot_data")
        await query.answer("Service temporarily unavailable", show_alert=True)
        return
    
    # Получаем user prompt
    user_prompt = prompt_store.get_prompt(prompt_hash)
    if not user_prompt:
        await query.answer("Expired, rerun inline", show_alert=True)
        return
    
    # Атомарная проверка квот
    now = time.time()
    ok, message, retry_after = await quota_manager.try_consume(user_id, now)
    
    if not ok:
        # Показываем сообщение об ошибке
        if retry_after:
            await query.answer(f"{message} (wait {int(retry_after)}s)", show_alert=True)
        else:
            await query.answer(message, show_alert=True)
        return
    
    # Используем промпт пользователя напрямую
    final_prompt = user_prompt
    
    # Быстро отвечаем
    await query.answer("Generating…")
    
    # Placeholder уже отправлен как стикер в inline query результате
    # Не нужно отправлять placeholder здесь - сразу запускаем генерацию
    # Если сообщение было отправлено как текст (fallback), то оно останется текстом
    # и будет обновлено на финальное изображение в run_generation_and_update_message
    
    # Запускаем фоновую задачу
    task = context.application.create_task(
        run_generation_and_update_message(
            user_id=user_id,
            prompt_hash=prompt_hash,
            final_prompt=final_prompt,
            query=query,
            context=context,
        )
    )
    task.add_done_callback(log_task_exception)


async def handle_regenerate_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    """Обработчик callback_query для регенерации (паттерн ^regen:)"""
    query = update.callback_query
    if not query:
        return
    
    await query.answer()
    
    user_id = query.from_user.id
    callback_data = query.data
    
    # Парсим prompt_hash
    if not callback_data.startswith("regen:"):
        logger.warning(f"Invalid callback_data: {callback_data}")
        return
    
    prompt_hash = callback_data[6:]  # Убираем "regen:"
    
    # Получаем компоненты из bot_data
    prompt_store = context.bot_data.get("prompt_store")
    quota_manager = context.bot_data.get("quota_manager")
    wavespeed_client = context.bot_data.get("wavespeed_client")
    
    if not all([prompt_store, quota_manager, wavespeed_client]):
        logger.error("Missing required components in bot_data")
        await query.answer("Service temporarily unavailable", show_alert=True)
        return
    
    # Получаем user prompt
    user_prompt = prompt_store.get_prompt(prompt_hash)
    if not user_prompt:
        await query.answer("Expired, rerun inline", show_alert=True)
        return
    
    # Атомарная проверка квот
    now = time.time()
    ok, message, retry_after = await quota_manager.try_consume(user_id, now)
    
    if not ok:
        if retry_after:
            await query.answer(f"{message} (wait {int(retry_after)}s)", show_alert=True)
        else:
            await query.answer(message, show_alert=True)
        return
    
    # Используем промпт пользователя напрямую (тот же промпт, но новый seed)
    final_prompt = user_prompt
    
    # Быстро отвечаем
    await query.answer("Regenerating…")
    
    # Placeholder уже отправлен как стикер в inline query результате
    # Не нужно отправлять placeholder здесь - сразу запускаем генерацию
    # Если сообщение было отправлено как текст (fallback), то оно останется текстом
    # и будет обновлено на финальное изображение в run_generation_and_update_message
    
    # Запускаем фоновую задачу (с новым seed=-1)
    task = context.application.create_task(
        run_generation_and_update_message(
            user_id=user_id,
            prompt_hash=prompt_hash,
            final_prompt=final_prompt,
            query=query,
            context=context,
            seed=-1,  # Новый случайный seed
        )
    )
    task.add_done_callback(log_task_exception)


async def run_generation_and_update_message(
    user_id: int,
    prompt_hash: str,
    final_prompt: str,
    query,
    context: ContextTypes.DEFAULT_TYPE,
    seed: int = -1,
) -> None:
    """Фоновая задача для генерации и обновления сообщения (2-stage pipeline: flux -> bg-remover)"""
    quota_manager = context.bot_data.get("quota_manager")
    wavespeed_client = context.bot_data.get("wavespeed_client")
    
    # Общий deadline для обеих стадий
    overall_deadline = time.time() + WAVESPEED_MAX_POLL_SECONDS
    poll_interval_base = 1.5
    
    try:
        # Stage 1: Flux-schnell генерация
        logger.info(f"Generation: Starting flux-schnell generation for user {user_id}, prompt_hash={prompt_hash[:8]}...")
        flux_request_id = await wavespeed_client.submit_flux_schnell(
            final_prompt, seed=seed, output_format="png"
        )
        logger.info(f"Generation: Flux request submitted: request_id={flux_request_id}")
        
        # Polling flux result
        flux_image_url = None
        poll_count = 0
        start_poll_time = time.time()
        
        while time.time() < overall_deadline:
            poll_count += 1
            elapsed = time.time() - start_poll_time
            await asyncio.sleep(poll_interval_base + random.uniform(-0.3, 0.3))
            
            logger.debug(f"Generation: Polling flux result #{poll_count} (elapsed: {elapsed:.1f}s, request_id={flux_request_id})")
            result = await wavespeed_client.get_prediction_result(flux_request_id)
            
            if not result:
                logger.debug(f"Generation: No result yet for {flux_request_id}, continuing...")
                continue
            
            # Проверяем структуру ответа (может быть вложенный data)
            if "data" in result and isinstance(result.get("data"), dict):
                data = result["data"]
                status = data.get("status", "").lower()
                outputs = data.get("outputs", [])
            else:
                status = result.get("status", "").lower()
                outputs = result.get("outputs", [])
            
            logger.debug(f"Generation: Flux status: '{status}', outputs: {len(outputs) if outputs else 0}")
            
            if status == "completed":
                if not outputs:
                    logger.error(f"Generation: Status completed but no outputs in result. Full result: {result}")
                    break
                flux_image_url = outputs[0]
                logger.info(f"Generation: Flux generation completed! Image URL: {flux_image_url[:80]}...")
                break
                
            elif status == "failed":
                error_msg = result.get("error") or (data.get("error") if "data" in result else "Unknown error")
                logger.error(f"Generation: WaveSpeed flux generation failed for {flux_request_id}: {error_msg}")
                await update_message_with_error(
                    query=query,
                    context=context,
                    prompt_hash=prompt_hash,
                    error_msg="Generation failed",
                )
                return
        
        if not flux_image_url:
            elapsed_total = time.time() - start_poll_time
            logger.warning(f"Generation: Flux generation timeout or failed after {elapsed_total:.1f}s, {poll_count} polls, request_id={flux_request_id}")
            await update_message_with_error(
                query=query,
                context=context,
                prompt_hash=prompt_hash,
                error_msg="Timed out",
            )
            return
        
        # Stage 2: Background removal (если включено)
        final_image_url = flux_image_url
        bg_removal_success = False
        
        if WAVESPEED_BG_REMOVE_ENABLED:
            logger.info(f"Generation: Starting background removal for image: {flux_image_url[:80]}...")
            # Обновляем статус (опционально, максимум 1 дополнительный edit)
            try:
                status_text = "🧼 Removing background…"
                if query.inline_message_id:
                    await context.bot.edit_message_text(
                        inline_message_id=query.inline_message_id,
                        text=status_text,
                    )
                else:
                    await query.message.edit_text(status_text)
            except Exception as e:
                logger.debug(f"Could not update status to bg-removal: {e}")
            
            try:
                bg_request_id = await wavespeed_client.submit_background_remover(flux_image_url)
                logger.info(f"Generation: Background removal request submitted: request_id={bg_request_id}")
                
                # Polling bg-remover result (в рамках оставшегося времени)
                bg_poll_count = 0
                bg_start_time = time.time()
                
                while time.time() < overall_deadline:
                    bg_poll_count += 1
                    bg_elapsed = time.time() - bg_start_time
                    await asyncio.sleep(poll_interval_base + random.uniform(-0.3, 0.3))
                    
                    logger.debug(f"Generation: Polling bg-remover result #{bg_poll_count} (elapsed: {bg_elapsed:.1f}s, request_id={bg_request_id})")
                    result = await wavespeed_client.get_prediction_result(bg_request_id)
                    
                    if not result:
                        logger.debug(f"Generation: No bg-remover result yet for {bg_request_id}, continuing...")
                        continue
                    
                    # Проверяем структуру ответа (может быть вложенный data)
                    if "data" in result and isinstance(result.get("data"), dict):
                        data = result["data"]
                        status = data.get("status", "").lower()
                        outputs = data.get("outputs", [])
                    else:
                        status = result.get("status", "").lower()
                        outputs = result.get("outputs", [])
                    
                    logger.debug(f"Generation: Bg-remover status: '{status}', outputs: {len(outputs) if outputs else 0}")
                    
                    if status == "completed":
                        if outputs:
                            final_image_url = outputs[0]  # PNG с прозрачностью
                            bg_removal_success = True
                            logger.info(f"Generation: Background removal completed! Final URL: {final_image_url[:80]}...")
                            break
                        else:
                            logger.warning(f"Generation: Bg-remover completed but no outputs found")
                    
                    elif status == "failed":
                        error_msg = result.get("error") or (data.get("error") if "data" in result else "Unknown error")
                        logger.warning(f"Generation: Background removal failed for {bg_request_id}: {error_msg}, using flux result as fallback")
                        break
                
                if not bg_removal_success:
                    bg_elapsed_total = time.time() - bg_start_time
                    logger.info(f"Generation: Background removal timeout or failed after {bg_elapsed_total:.1f}s, {bg_poll_count} polls, using flux result as fallback")
                    
            except Exception as e:
                logger.warning(f"Generation: Background removal error for {flux_image_url[:80]}..., using flux result as fallback: {e}", exc_info=True)
        
        # Обновляем сообщение с финальным изображением
        logger.info(f"[run_generation_and_update_message] Updating message with final image: {final_image_url[:80]}...")
        logger.debug(f"[run_generation_and_update_message] Calling update_message_with_image with: "
                    f"user_id={user_id}, prompt_hash={prompt_hash[:8]}..., "
                    f"has_inline_id={bool(query.inline_message_id)}, has_message={bool(query.message)}")
        
        await update_message_with_image(
            query=query,
            context=context,
            image_url=final_image_url,
            prompt_hash=prompt_hash,
            caption="✅ Generated by STIXLY",
        )
        logger.info(f"[run_generation_and_update_message] SUCCESS: Generation completed for user {user_id}, prompt_hash={prompt_hash[:8]}...")
        
    except Exception as e:
        logger.error(f"[run_generation_and_update_message] ERROR: Exception in generation task for user {user_id}: {e}", exc_info=True)
        await update_message_with_error(
            query=query,
            context=context,
            prompt_hash=prompt_hash,
            error_msg="Error occurred",
        )
    finally:
        # Освобождаем слот
        if quota_manager:
            await quota_manager.finish(user_id)


async def update_message_with_image(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    image_url: str,
    prompt_hash: str,
    caption: str = "✅ Generated by STIXLY",
) -> None:
    """Обновить сообщение с изображением (с fallback на upload)"""
    logger.info(f"[update_message_with_image] START: image_url={image_url[:80]}..., "
                f"prompt_hash={prompt_hash[:8]}..., has_inline_id={bool(query.inline_message_id)}, "
                f"has_message={bool(query.message)}")
    
    def create_keyboard() -> InlineKeyboardMarkup:
        """Создать клавиатуру с кнопками"""
        buttons = []
        
        buttons.append([
            InlineKeyboardButton(
                "Regenerate",
                callback_data=f"regen:{prompt_hash}"
            )
        ])
        
        return InlineKeyboardMarkup(buttons)
    
    # Сохраняем PNG в стикерсет пользователя и обновляем сообщение
    logger.debug(f"[update_message_with_image] Checking sticker_service availability")
    sticker_service = context.bot_data.get("sticker_service")
    logger.debug(f"[update_message_with_image] sticker_service={sticker_service is not None}, "
                 f"query.from_user={query.from_user is not None if query else None}")
    if sticker_service and query.from_user:
        user_id = query.from_user.id
        user_username = query.from_user.username
        bot_username = context.bot.username
        
        if bot_username:
            logger.debug(f"[update_message_with_image] bot_username available: {bot_username}")
            try:
                # Скачиваем PNG изображение
                logger.debug(f"[update_message_with_image] Getting wavespeed_client from bot_data")
                wavespeed_client = context.bot_data.get("wavespeed_client")
                if wavespeed_client:
                    logger.info(f"[update_message_with_image] Downloading PNG image from: {image_url[:80]}...")
                    png_bytes = await wavespeed_client.download_image(image_url)
                    if png_bytes:
                        logger.info(f"[update_message_with_image] PNG downloaded successfully, size: {len(png_bytes)} bytes")
                        # Сохраняем в стикерсет пользователя
                        logger.debug(f"[update_message_with_image] Calling save_sticker_to_user_set")
                        sticker_file_id = await save_sticker_to_user_set(
                            user_id=user_id,
                            user_username=user_username,
                            bot_username=bot_username,
                            png_bytes=png_bytes,
                            sticker_service=sticker_service,
                            context=context,
                        )
                        logger.debug(f"[update_message_with_image] save_sticker_to_user_set returned: {sticker_file_id is not None}")
                        
                        if sticker_file_id:
                            # Стикер успешно сохранен в стикерсет пользователя
                            logger.info(f"[update_message_with_image] Sticker saved to user set {user_username or f'user_{user_id}'}_by_{bot_username}. "
                                      f"File ID: {sticker_file_id[:20]}...")
                            
                            keyboard = create_keyboard()
                            
                            if query.inline_message_id:
                                # Для inline сообщений: отправляем новое сообщение со стикером в чат, откуда поступил запрос
                                # Пытаемся получить chat_id из query.message, если доступно (когда inline сообщение уже отправлено в чат)
                                target_chat_id = None
                                if query.message and query.message.chat:
                                    target_chat_id = query.message.chat.id
                                    logger.info(f"[update_message_with_image] Has inline_message_id with message.chat, sending to chat_id: {target_chat_id}")
                                else:
                                    # Если нет доступа к chat (inline сообщение еще не отправлено в чат),
                                    # отправляем в личный чат пользователя как fallback
                                    target_chat_id = user_id
                                    logger.warning(f"[update_message_with_image] Has inline_message_id but no message.chat available, "
                                                 f"using user_id as fallback: {target_chat_id}. "
                                                 f"Note: inline message may not have been sent to a chat yet.")
                                
                                try:
                                    await context.bot.send_sticker(
                                        chat_id=target_chat_id,
                                        sticker=sticker_file_id,
                                        reply_markup=keyboard,
                                    )
                                    logger.info(f"[update_message_with_image] SUCCESS: Sent new sticker message to chat {target_chat_id}")
                                    return
                                except TelegramError as send_error:
                                    logger.error(f"[update_message_with_image] ERROR: Failed to send sticker to chat {target_chat_id}: {send_error}")
                                    # Продолжаем с обычной логикой обновления
                            else:
                                # Для обычных сообщений: удаляем старое и отправляем новое со стикером
                                logger.info(f"[update_message_with_image] Regular message, deleting old and sending new sticker")
                                try:
                                    # Удаляем старое сообщение
                                    if query.message:
                                        logger.debug(f"[update_message_with_image] Deleting old message: {query.message.message_id}")
                                        await query.message.delete()
                                        logger.debug(f"[update_message_with_image] Old message deleted successfully")
                                    
                                    # Отправляем новое сообщение со стикером
                                    await context.bot.send_sticker(
                                        chat_id=query.message.chat.id if query.message else user_id,
                                        sticker=sticker_file_id,
                                        reply_markup=keyboard,
                                    )
                                    logger.info(f"[update_message_with_image] SUCCESS: Sent new sticker message after deleting old one")
                                    return
                                except TelegramError as send_error:
                                    logger.error(f"[update_message_with_image] ERROR: Failed to delete/send sticker: {send_error}")
                                    # Продолжаем с обычной логикой обновления
                    else:
                        logger.warning(f"[update_message_with_image] Failed to download PNG image from: {image_url[:80]}...")
                else:
                    logger.warning(f"[update_message_with_image] wavespeed_client not available in bot_data")
            except Exception as e:
                logger.error(f"[update_message_with_image] ERROR: Exception while saving sticker to user set: {e}", exc_info=True)
                # Продолжаем с обычной логикой обновления
        else:
            logger.warning(f"[update_message_with_image] bot_username not available")
    
    # Обычная логика обновления сообщения (fallback)
    # Пробуем отправить PNG URL напрямую или скачать и отправить
    logger.info(f"[update_message_with_image] FALLBACK: Using standard message update logic")
    try:
        logger.debug(f"[update_message_with_image] Creating InputMediaPhoto with URL: {image_url[:80]}...")
        media = InputMediaPhoto(
            media=image_url,
            caption=caption,
        )
        
        # Создаем клавиатуру
        keyboard = create_keyboard()
        
        if query.inline_message_id:
            logger.info(f"[update_message_with_image] Updating inline message media with photo URL")
            await context.bot.edit_message_media(
                inline_message_id=query.inline_message_id,
                media=media,
                reply_markup=keyboard,
            )
            logger.info(f"[update_message_with_image] SUCCESS: Inline message updated with photo")
        else:
            logger.info(f"[update_message_with_image] Updating regular message media with photo URL")
            await query.message.edit_media(
                media=media,
                reply_markup=keyboard,
            )
            logger.info(f"[update_message_with_image] SUCCESS: Regular message updated with photo")
        return
        
    except TelegramError as e:
        logger.warning(f"[update_message_with_image] ERROR: Failed to update message with photo URL: {e}")
        # Если не получилось с URL, скачиваем и загружаем
        if "url" in str(e).lower() or "download" in str(e).lower():
            logger.info(f"[update_message_with_image] URL upload failed, downloading image: {type(e).__name__}")
            try:
                # Скачиваем изображение
                logger.debug(f"[update_message_with_image] Downloading image via httpx: {image_url[:80]}...")
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    response = await client.get(image_url)
                    response.raise_for_status()
                    image_bytes = response.content
                logger.info(f"[update_message_with_image] Image downloaded via httpx, size: {len(image_bytes)} bytes")
                
                # Создаем InputFile
                image_file = InputFile(
                    io.BytesIO(image_bytes),
                    filename="stixly.png",
                )
                
                media = InputMediaPhoto(
                    media=image_file,
                    caption=caption,
                )
                
                # Создаем клавиатуру
                keyboard = create_keyboard()
                
                if query.inline_message_id:
                    logger.info(f"[update_message_with_image] Updating inline message with downloaded image file")
                    await context.bot.edit_message_media(
                        inline_message_id=query.inline_message_id,
                        media=media,
                        reply_markup=keyboard,
                    )
                    logger.info(f"[update_message_with_image] SUCCESS: Inline message updated with downloaded image")
                else:
                    try:
                        logger.info(f"[update_message_with_image] Updating regular message with downloaded image file")
                        await query.message.edit_media(
                            media=media,
                            reply_markup=keyboard,
                        )
                        logger.info(f"[update_message_with_image] SUCCESS: Regular message updated with downloaded image")
                    except TelegramError as edit_error:
                        logger.warning(f"[update_message_with_image] Failed to edit message, trying to send new: {edit_error}")
                        # Если редактирование не работает, отправляем новое сообщение
                        if query.message and query.message.chat:
                            logger.info(f"[update_message_with_image] Sending new photo message to chat_id: {query.message.chat.id}")
                            await context.bot.send_photo(
                                chat_id=query.message.chat.id,
                                photo=image_file,
                                caption=caption,
                                reply_markup=keyboard,
                            )
                            logger.info(f"[update_message_with_image] SUCCESS: New photo message sent")
                        else:
                            logger.error(f"[update_message_with_image] ERROR: Cannot send new message: query.message.chat is not available")
                return
                
            except Exception as upload_error:
                logger.error(f"[update_message_with_image] ERROR: Exception while uploading image: {upload_error}", exc_info=True)
        
        # Если и upload не сработал, показываем ошибку
        logger.error(f"[update_message_with_image] ERROR: All update methods failed, raising exception")
        raise


async def update_message_with_error(
    query,
    context: ContextTypes.DEFAULT_TYPE,
    prompt_hash: str,
    error_msg: str,
) -> None:
    """Обновить сообщение с ошибкой"""
    text = f"⚠️ {error_msg}. Try Regenerate."
    
    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton(
            "Regenerate",
            callback_data=f"regen:{prompt_hash}"
        )
    ]])
    
    try:
        if query.inline_message_id:
            await context.bot.edit_message_text(
                inline_message_id=query.inline_message_id,
                text=text,
                reply_markup=keyboard,
            )
        else:
            await query.message.edit_text(
                text=text,
                reply_markup=keyboard,
            )
    except Exception as e:
        logger.error(f"Error updating error message: {e}")

