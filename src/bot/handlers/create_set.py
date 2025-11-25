import asyncio
import html
import logging
import re
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from src.bot.states import (
    WAITING_NEW_TITLE,
    WAITING_STICKER,
    WAITING_EMOJI,
    WAITING_DECISION,
    WAITING_SHORT_NAME,
    WAITING_PUBLISH_DECISION,
)
from src.config.settings import GALLERY_DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)


async def create_new_set(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
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


async def handle_new_set_title(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработка пользовательского названия нового стикерсета"""
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


async def handle_emoji_for_create(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    image_service,
) -> int:
    """Обработка эмодзи для создания нового стикерсета"""
    emoji = update.message.text
    user_data = context.user_data

    if 'current_webp' not in user_data:
        await update.message.reply_text(
            "Не получилось сопоставить эмодзи с картинкой. Попробуй отправить стикер ещё раз."
        )
        return WAITING_STICKER

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


async def finish_sticker_collection_for_create(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Завершение добавления стикеров для создания нового набора"""
    user_data = context.user_data
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


async def handle_short_name(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sticker_service,
    gallery_service,
) -> int:
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
        sticker_service.is_sticker_set_available,
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
        sticker_service.create_new_sticker_set,
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
            sticker_service.add_sticker_to_set,
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

    gallery_record = None
    if gallery_service.is_configured():
        gallery_record = await asyncio.to_thread(
            gallery_service.save_sticker_set,
            user_id=update.effective_user.id,
            sticker_set_id=None,
            sticker_set_link=sticker_set_link,
            title=title,
            is_public=False,
            language=GALLERY_DEFAULT_LANGUAGE,
        )

        if not gallery_record:
            logger.warning(
                "Не удалось сохранить стикерсет в галерее для пользователя %s",
                update.effective_user.id
            )

    if gallery_record:
        message += "\n\n✅ Я добавил этот набор в твою галерею."

    await update.message.reply_text(message, reply_markup=ReplyKeyboardRemove())

    if gallery_record and gallery_record.get('id'):
        context.user_data['publish_candidate'] = {
            'id': gallery_record.get('id'),
            'title': title,
            'link': sticker_set_link,
        }
        await _prompt_publish_choice(update, context, title, sticker_set_link)
        return WAITING_PUBLISH_DECISION

    context.user_data.clear()
    return ConversationHandler.END


async def _prompt_publish_choice(update: Update, context: ContextTypes.DEFAULT_TYPE, title: str, link: str) -> None:
    """Предложение опубликовать набор в галерее"""
    from telegram import InlineKeyboardButton, InlineKeyboardMarkup
    
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🚀 Опубликовать", callback_data='publish:yes')
        ],
        [
            InlineKeyboardButton("Оставить приватным", callback_data='publish:no')
        ]
    ])

    await update.message.reply_text(
        f'Хочешь поделиться набором <a href="{html.escape(link, quote=True)}">{html.escape(title)}</a> '
        'в галерее, чтобы его увидели другие?',
        reply_markup=keyboard,
        parse_mode='HTML'
    )

