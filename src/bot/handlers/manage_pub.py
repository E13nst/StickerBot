import asyncio
import html
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import ContextTypes, ConversationHandler

from src.bot.states import (
    WAITING_MANAGE_CHOICE,
    WAITING_PUBLISH_DECISION,
    PAGE_PREV_LABEL,
    PAGE_NEXT_LABEL,
    CANCEL_LABEL,
)
from src.config.settings import GALLERY_DEFAULT_LANGUAGE

logger = logging.getLogger(__name__)


async def manage_publication(update: Update, context: ContextTypes.DEFAULT_TYPE, gallery_service) -> int:
    """Управление публикацией наборов"""
    if update.message:
        await update.message.reply_text(
            "Выбираем набор для изменения статуса публикации:",
            reply_markup=ReplyKeyboardRemove()
        )
    elif update.callback_query:
        await update.callback_query.answer()

    context.user_data.clear()
    context.user_data['action'] = 'manage_publication'
    return await show_manage_sets(update, context, page=0, gallery_service=gallery_service)


async def show_manage_sets(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    page: int,
    gallery_service
) -> int:
    """Отображение наборов для управления публикацией"""
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
        await update.effective_message.reply_text(
            "Не удалось загрузить список наборов. Попробуй позже.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    items = result.get('content') or []
    if not items:
        await update.effective_message.reply_text(
            "Пока нет ни одного набора. Создай его, а потом управляй публикацией здесь.",
            reply_markup=ReplyKeyboardRemove()
        )
        context.user_data.clear()
        return ConversationHandler.END

    current_page = result.get('page', page) or 0
    total_pages = result.get('totalPages', 1) or 1

    user_data['manage_sets'] = items
    user_data['manage_page'] = current_page
    user_data['manage_total_pages'] = total_pages
    user_data.pop('manage_selected', None)

    icons = {True: '🌐', False: '🔒'}
    lines = [
        "Выбери набор, чтобы изменить статус публикации.",
        f"Страница {current_page + 1} из {total_pages}"
    ]

    keyboard = _build_manage_keyboard(items, current_page, total_pages, icons)

    if update.callback_query:
        query = update.callback_query
        await query.edit_message_text(
            "\n".join(lines),
            reply_markup=keyboard
        )
    else:
        await update.message.reply_text(
            "\n".join(lines),
            reply_markup=keyboard
        )

    return WAITING_MANAGE_CHOICE


def _build_manage_keyboard(items, page, total_pages, icons):
    """Формирует inline-клавиатуру для управления публикацией"""
    buttons = []
    row = []
    for index, item in enumerate(items):
        title = item.get('title') or item.get('name')
        icon = icons[bool(item.get('isPublic'))]
        row.append(
            InlineKeyboardButton(
                text=f"{icon} {title}",
                callback_data=f"manage:set:{index}"
            )
        )
        if len(row) == 2:
            buttons.append(row)
            row = []
    if row:
        buttons.append(row)

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(PAGE_PREV_LABEL, callback_data='manage:page:prev'))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(PAGE_NEXT_LABEL, callback_data='manage:page:next'))
    if nav_buttons:
        buttons.append(nav_buttons)

    buttons.append([InlineKeyboardButton(CANCEL_LABEL, callback_data='manage:cancel')])
    return InlineKeyboardMarkup(buttons)


async def handle_manage_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service,
) -> int:
    """Обработка выбора в управлении публикацией"""
    query = update.callback_query
    data = query.data
    user_data = context.user_data

    if user_data.get('action') != 'manage_publication':
        await query.answer()
        await query.edit_message_text("Процесс управления публикацией не найден. Начни заново с /start.")
        context.user_data.clear()
        return ConversationHandler.END

    current_page = user_data.get('manage_page', 0)
    total_pages = user_data.get('manage_total_pages', 1)

    if data == 'manage:cancel':
        await query.answer("Отменяем.")
        await query.edit_message_text("Управление публикацией завершено. Возвращайся в любое время.")
        context.user_data.clear()
        return ConversationHandler.END

    if data == 'manage:page:next':
        if current_page < total_pages - 1:
            await query.answer("Следующая страница")
            return await show_manage_sets(update, context, page=current_page + 1, gallery_service=gallery_service)
        await query.answer("Это последняя страница", show_alert=True)
        return WAITING_MANAGE_CHOICE

    if data == 'manage:page:prev':
        if current_page > 0:
            await query.answer("Предыдущая страница")
            return await show_manage_sets(update, context, page=current_page - 1, gallery_service=gallery_service)
        await query.answer("Это первая страница", show_alert=True)
        return WAITING_MANAGE_CHOICE

    if data == 'manage:back':
        await query.answer()
        return await show_manage_sets(update, context, page=user_data.get('manage_page', 0), gallery_service=gallery_service)

    if data == 'manage:unpublish':
        selected = user_data.get('manage_selected')
        if not selected:
            await query.answer("Набор не выбран.", show_alert=True)
            return WAITING_MANAGE_CHOICE

        success = await asyncio.to_thread(
            gallery_service.unpublish_sticker_set,
            sticker_set_id=selected.get('id'),
            user_id=update.effective_user.id,
            language=GALLERY_DEFAULT_LANGUAGE,
        )

        if success:
            await query.edit_message_text(
                f"🔕 Набор {selected.get('title') or selected.get('name')} скрыт из галереи."
            )
            return await show_manage_sets(update, context, page=user_data.get('manage_page', 0), gallery_service=gallery_service)

        await query.edit_message_text(
            "Не удалось снять набор с публикации. Попробуй позже."
        )
        return WAITING_MANAGE_CHOICE

    if data.startswith('manage:set:'):
        index = int(data.rsplit(':', 1)[1])
        sets = user_data.get('manage_sets', [])
        if 0 <= index < len(sets):
            target_set = sets[index]
            user_data['manage_selected'] = target_set

            title = target_set.get('title') or target_set.get('name')
            url = target_set.get('url') or f"https://t.me/addstickers/{target_set.get('name')}"
            is_public = bool(target_set.get('isPublic'))

            if is_public:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("🔕 Снять с публикации", callback_data='manage:unpublish')],
                    [InlineKeyboardButton("⬅️ Вернуться", callback_data='manage:back')]
                ])
                text = (
                    f'Набор <a href="{html.escape(url, quote=True)}">{html.escape(title)}</a> сейчас публичный.\n'
                    "Снять его из галереи?"
                )
            else:
                keyboard = InlineKeyboardMarkup([
                    [InlineKeyboardButton("⬅️ Вернуться", callback_data='manage:back')]
                ])
                text = (
                    f'Набор <a href="{html.escape(url, quote=True)}">{html.escape(title)}</a> уже приватный.'
                )

            await query.answer()
            await query.edit_message_text(text, reply_markup=keyboard, parse_mode='HTML')
            return WAITING_MANAGE_CHOICE

    await query.answer("Не удалось обработать выбор", show_alert=True)
    return WAITING_MANAGE_CHOICE


async def handle_manage_choice_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подсказка при текстовом ответе в управлении публикацией"""
    await update.message.reply_text("Пожалуйста, используй кнопки для управления публикацией.")
    return WAITING_MANAGE_CHOICE


async def handle_publish_choice(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    gallery_service,
) -> int:
    """Обработка решения опубликовать набор"""
    query = update.callback_query
    data = query.data
    candidate = context.user_data.get('publish_candidate')

    if not candidate:
        await query.answer("Данных для публикации нет.", show_alert=True)
        await query.edit_message_text("Процесс публикации не найден. Начни заново с /start.")
        context.user_data.clear()
        return ConversationHandler.END

    await query.answer()

    if data == 'publish:yes':
        success = await asyncio.to_thread(
            gallery_service.publish_sticker_set,
            sticker_set_id=candidate.get('id'),
            user_id=update.effective_user.id,
            language=GALLERY_DEFAULT_LANGUAGE,
            is_public=True,
        )

        if success:
            await query.edit_message_text(
                "Готово! Набор опубликован в галерее. Делись ссылкой и собирай реакции 🚀"
            )
        else:
            await query.edit_message_text(
                "Не удалось опубликовать набор. Попробуй позже или свяжись с поддержкой."
            )
    else:
        await query.edit_message_text(
            "Окей, оставим набор приватным. Если передумаешь, опубликовать можно позже."
        )

    context.user_data.clear()
    return ConversationHandler.END


async def handle_publish_choice_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Подсказка при текстовом ответе на предложение публикации"""
    await update.message.reply_text(
        "Пожалуйста, используй кнопки для выбора: опубликовать или оставить приватным."
    )
    return WAITING_PUBLISH_DECISION

