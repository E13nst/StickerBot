"""Handlers для inline generation через WaveSpeed"""
import asyncio
import io
import logging
import time
import random
from typing import Optional
import httpx
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, InputFile
from telegram.ext import ContextTypes
from telegram.error import TelegramError

from src.config.settings import (
    WAVESPEED_SYSTEM_PROMPT,
    WAVESPEED_MAX_POLL_SECONDS,
    MINIAPP_GALLERY_URL,
)

logger = logging.getLogger(__name__)


def log_task_exception(task: asyncio.Task):
    """Callback для логирования исключений фоновой задачи"""
    try:
        exc = task.exception()
        if exc:
            logger.exception("Generation task failed", exc_info=exc)
    except Exception as e:
        logger.error(f"Error in task exception callback: {e}")


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
    
    # Собираем final_prompt
    final_prompt = f"{WAVESPEED_SYSTEM_PROMPT}\n\nUser prompt: {user_prompt}"
    
    # Быстро отвечаем
    await query.answer("Generating…")
    
    # Редактируем сообщение
    status_text = "⏳ Generating…"
    try:
        if query.inline_message_id:
            await context.bot.edit_message_text(
                inline_message_id=query.inline_message_id,
                text=status_text,
            )
        else:
            await query.message.edit_text(status_text)
    except Exception as e:
        logger.warning(f"Error editing message: {e}")
    
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
    
    # Собираем final_prompt (тот же промпт, но новый seed)
    final_prompt = f"{WAVESPEED_SYSTEM_PROMPT}\n\nUser prompt: {user_prompt}"
    
    # Быстро отвечаем
    await query.answer("Regenerating…")
    
    # Редактируем сообщение
    status_text = "⏳ Regenerating…"
    try:
        if query.inline_message_id:
            await context.bot.edit_message_text(
                inline_message_id=query.inline_message_id,
                text=status_text,
            )
        else:
            await query.message.edit_text(status_text)
    except Exception as e:
        logger.warning(f"Error editing message: {e}")
    
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
    """Фоновая задача для генерации и обновления сообщения"""
    quota_manager = context.bot_data.get("quota_manager")
    wavespeed_client = context.bot_data.get("wavespeed_client")
    
    try:
        # Отправляем задачу
        request_id = await wavespeed_client.submit_flux_schnell(
            final_prompt, seed=seed
        )
        
        # Polling с jitter
        start_time = time.time()
        poll_interval_base = 1.5
        max_poll_seconds = WAVESPEED_MAX_POLL_SECONDS
        
        while time.time() - start_time < max_poll_seconds:
            await asyncio.sleep(poll_interval_base + random.uniform(-0.3, 0.3))
            
            result = await wavespeed_client.get_prediction_result(request_id)
            if not result:
                continue
            
            status = result.get("status", "").lower()
            
            if status == "completed":
                # Получаем URL изображения
                outputs = result.get("outputs", [])
                if not outputs:
                    logger.error(f"No outputs in completed result: {result}")
                    break
                
                image_url = outputs[0]
                
                # Обновляем сообщение с изображением
                await update_message_with_image(
                    query=query,
                    context=context,
                    image_url=image_url,
                    prompt_hash=prompt_hash,
                )
                return
                
            elif status == "failed":
                error_msg = result.get("error", "Unknown error")
                logger.error(f"WaveSpeed generation failed: {error_msg}")
                await update_message_with_error(
                    query=query,
                    context=context,
                    prompt_hash=prompt_hash,
                    error_msg="Generation failed",
                )
                return
        
        # Timeout
        logger.warning(f"WaveSpeed generation timeout after {max_poll_seconds}s")
        await update_message_with_error(
            query=query,
            context=context,
            prompt_hash=prompt_hash,
            error_msg="Timed out",
        )
        
    except Exception as e:
        logger.exception(f"Error in generation task for user {user_id}: {e}")
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
) -> None:
    """Обновить сообщение с изображением (с fallback на upload)"""
    # Создаем кнопки
    buttons = []
    
    if MINIAPP_GALLERY_URL:
        buttons.append([
            InlineKeyboardButton(
                "Save to Stixly",
                url=f"{MINIAPP_GALLERY_URL}?action=save&hash={prompt_hash}"
            )
        ])
    
    buttons.append([
        InlineKeyboardButton(
            "Regenerate",
            callback_data=f"regen:{prompt_hash}"
        )
    ])
    
    keyboard = InlineKeyboardMarkup(buttons)
    
    # Пробуем отправить URL напрямую
    try:
        media = InputMediaPhoto(
            media=image_url,
            caption="✅ Generated by STIXLY",
        )
        
        if query.inline_message_id:
            await context.bot.edit_message_media(
                inline_message_id=query.inline_message_id,
                media=media,
                reply_markup=keyboard,
            )
        else:
            await query.message.edit_media(
                media=media,
                reply_markup=keyboard,
            )
        return
        
    except TelegramError as e:
        # Если не получилось с URL, скачиваем и загружаем
        if "url" in str(e).lower() or "download" in str(e).lower():
            logger.info(f"URL upload failed, downloading image: {e}")
            try:
                # Скачиваем изображение
                async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
                    response = await client.get(image_url)
                    response.raise_for_status()
                    image_bytes = response.content
                
                # Создаем InputFile
                image_file = InputFile(
                    io.BytesIO(image_bytes),
                    filename="stixly.png",
                )
                
                media = InputMediaPhoto(
                    media=image_file,
                    caption="✅ Generated by STIXLY",
                )
                
                if query.inline_message_id:
                    await context.bot.edit_message_media(
                        inline_message_id=query.inline_message_id,
                        media=media,
                        reply_markup=keyboard,
                    )
                else:
                    await query.message.edit_media(
                        media=media,
                        reply_markup=keyboard,
                    )
                return
                
            except Exception as upload_error:
                logger.error(f"Error uploading image: {upload_error}")
        
        # Если и upload не сработал, показываем ошибку
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

