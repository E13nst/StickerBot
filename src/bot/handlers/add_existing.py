import asyncio
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove, ReplyKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from src.bot.states import (
    WAITING_EXISTING_CHOICE,
    WAITING_STICKER,
    WAITING_EMOJI,
    WAITING_DECISION,
    PAGE_PREV_LABEL,
    PAGE_NEXT_LABEL,
    CANCEL_LABEL,
)
from src.config.settings import GALLERY_DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)


async def add_to_existing(update: Update, context: ContextTypes.DEFAULT_TYPE, gallery_service) -> int:
    """Добавление стикера в существующий стикерсет"""
    await update.message.reply_text(
        "Добавляем стикер в существующий стикерсет. Сначала выберем подходящий набор 👇",
        reply_markup=ReplyKeyboardRemove()
    )

    context.user_data.clear()
    context.user_data['action'] = 'add_existing'
    return await show_existing_sets(update, context, page=0, gallery_service=gallery_service)


async def show_existing_sets(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    gallery_service
) -> int:
    """Отображение списка существующих наборов пользователя"""
    user_id = update.effective_user.id
    user_data = context.user_data

    result = await asyncio.to_thread(
        gallery_service.get_user_sticker_sets,
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

    keyboard = _build_existing_sets_keyboard(items, current_page, total_pages)

    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(text=text, reply_markup=keyboard)
    else:
        await update.message.reply_text(text, reply_markup=keyboard)

    return WAITING_EXISTING_CHOICE


def _build_existing_sets_keyboard(items, page, total_pages):
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


async def handle_existing_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sticker_service,
    gallery_service,
) -> int:
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
            return await show_existing_sets(update, context, page=current_page + 1, gallery_service=gallery_service)
        await query.answer("Это последняя страница", show_alert=True)
        return WAITING_EXISTING_CHOICE

    if data == 'page:prev':
        if current_page > 0:
            await query.answer("Предыдущая страница")
            return await show_existing_sets(update, context, page=current_page - 1, gallery_service=gallery_service)
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


async def handle_existing_choice_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подсказка, если пользователь отправил текст вместо использования кнопок"""
    await update.message.reply_text("Пожалуйста, выбери набор с помощью кнопок ниже.")
    return WAITING_EXISTING_CHOICE


async def handle_emoji_for_add_existing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    sticker_service,
    gallery_service,
) -> int:
    """Обработка эмодзи для добавления в существующий набор"""
    emoji = update.message.text
    user_data = context.user_data

    if 'current_webp' not in user_data:
        await update.message.reply_text(
            "Не получилось сопоставить эмодзи с картинкой. Попробуй отправить стикер ещё раз."
        )
        return WAITING_STICKER

    user_data['emoji'] = emoji

    selected = user_data.get('selected_set')
    if not selected:
        await update.message.reply_text(
            "Не удалось найти выбранный набор. Попробуй выбрать его снова."
        )
        return await show_existing_sets(update, context, page=user_data.get('existing_page', 0), gallery_service=gallery_service)

    success = await asyncio.to_thread(
        sticker_service.add_sticker_to_set,
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

    await update.message.reply_text(
        "Не получилось добавить стикер. Попробуй снова или выбери другой набор.",
        reply_markup=ReplyKeyboardRemove()
    )
    return await show_existing_sets(update, context, page=user_data.get('existing_page', 0), gallery_service=gallery_service)


async def finish_sticker_collection_for_add_existing(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
) -> int:
    """Завершение добавления стикеров для существующего набора"""
    context.user_data.clear()
    await update.message.reply_text(
        "Готово! Если захочешь добавить ещё, просто отправь /start.",
        reply_markup=ReplyKeyboardRemove()
    )
    return ConversationHandler.END


async def prompt_waiting_for_more(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подсказка пользователю, если ожидается файл или завершение"""
    from telegram import ReplyKeyboardMarkup
    import html
    
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

