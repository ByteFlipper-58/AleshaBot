# handlers/pagination.py
import logging

from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Импортируем ParseMode отсюда

# Локальные импорты
from config import BOT_MODE
from database import get_db, get_all_feeds, get_all_channels, get_channel, get_subscriptions_for_channel
from constants import (
    CURRENT_PAGE, PAGE_SIZE,
    SUBSCRIBE_SELECT_FEED, SUBSCRIBE_SELECT_CHANNEL,
    UNSUBSCRIBE_SELECT_CHANNEL, UNSUBSCRIBE_SELECT_FEED,
    LIST_SUBS_SELECT_CHANNEL,
    EDIT_HASHTAGS_SELECT_CHANNEL, EDIT_HASHTAGS_SELECT_FEED
)
from keyboards import build_selection_keyboard # build_item_selection_keyboard удален
from handlers.common import is_authorized
from localization import get_text # Импортируем get_text
# Импортируем функции списков для возврата управления после пагинации
from handlers.feeds import list_feeds_button
from handlers.channels import list_channels_button

logger = logging.getLogger(__name__)

async def handle_pagination(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок пагинации."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        # Не знаем, в каком состоянии мы были, поэтому лучше завершить
        return ConversationHandler.END

    await query.answer()
    data = query.data # Пример: "page_sub_feed_2" или "page_feed_action_3"
    try:
        parts = data.split('_')
        # Префикс определяет тип списка и контекст
        # Пример: "page_sub_feed_" или "page_feed_action_" или "page_unsub_feed_123_"
        prefix = "_".join(parts[:-1]) + "_" # Восстанавливаем префикс с последним '_'
        page = int(parts[-1]) # Последняя часть - номер страницы
    except (IndexError, ValueError, AttributeError):
        logger.error(f"Invalid callback_data for pagination: {data}")
        await query.edit_message_text(get_text("error_occurred", context)) # Общая ошибка
        # Пытаемся вернуть в главное меню или завершить
        # Возможно, стоит вернуть в предыдущее известное меню, если оно хранится в user_data
        return ConversationHandler.END # Или другое безопасное состояние

    context.user_data[CURRENT_PAGE] = page

    # Определяем, какой список нужно отобразить и в каком состоянии мы находимся
    back_callback, items, name_attr, id_attr, text_key, current_state = "", [], "", "", "error_occurred", ConversationHandler.END
    owner_id = user_id if BOT_MODE == 'public' else None
    page_size = PAGE_SIZE
    # keyboard_builder больше не нужен, используем build_selection_keyboard всегда

    with next(get_db()) as db:
        # Пагинация для списков действий (ленты/каналы)
        if prefix == "page_feed_action_":
            # Просто вызываем функцию отображения списка лент с нужной страницей
            return await list_feeds_button(update, context, page=page)
        elif prefix == "page_channel_action_":
            # Просто вызываем функцию отображения списка каналов с нужной страницей
            return await list_channels_button(update, context, page=page)

        # Пагинация для диалогов выбора
        elif prefix == "page_sub_feed_":
            items = get_all_feeds(db, user_id=owner_id)
            back_callback = "subs_menu_back"
            name_attr = "name"; id_attr = "id"
            text_key = "subscribe_select_feed_title"
            current_state = SUBSCRIBE_SELECT_FEED
        elif prefix.startswith("page_sub_chan_"):
            items = get_all_channels(db, user_id=owner_id)
            back_callback = "subscribe_start" # Назад к выбору ленты
            name_attr = "name"; id_attr = "id"
            text_key = "subscribe_select_channel_title"
            current_state = SUBSCRIBE_SELECT_CHANNEL
        elif prefix == "page_unsub_chan_":
            items = get_all_channels(db, user_id=owner_id)
            back_callback = "subs_menu_back"
            name_attr = "name"; id_attr = "id"
            text_key = "unsubscribe_select_channel_title"
            current_state = UNSUBSCRIBE_SELECT_CHANNEL
        elif prefix.startswith("page_unsub_feed_"):
            try: channel_db_id = int(prefix.split('_')[2])
            except (IndexError, ValueError): channel_db_id = None
            channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id) if channel_db_id else None
            items = get_subscriptions_for_channel(db, channel_id=channel_db_id, user_id=owner_id) if channel else []
            back_callback = "unsubscribe_start" # Назад к выбору канала
            name_attr = "feed"; id_attr = "feed_id"
            text_key = "unsubscribe_select_feed_title" # TODO: Add channel name to text?
            current_state = UNSUBSCRIBE_SELECT_FEED
        elif prefix == "page_listsub_chan_":
            items = get_all_channels(db, user_id=owner_id)
            back_callback = "subs_menu_back"
            name_attr = "name"; id_attr = "id"
            text_key = "list_subs_select_channel_title"
            current_state = LIST_SUBS_SELECT_CHANNEL
        elif prefix == "page_editht_chan_":
            items = get_all_channels(db, user_id=owner_id)
            back_callback = "subs_menu_back"
            name_attr = "name"; id_attr = "id"
            text_key = "edit_hashtags_select_channel_title"
            current_state = EDIT_HASHTAGS_SELECT_CHANNEL
        elif prefix.startswith("page_editht_feed_"):
            try: channel_db_id = int(prefix.split('_')[2])
            except (IndexError, ValueError): channel_db_id = None
            channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id) if channel_db_id else None
            items = get_subscriptions_for_channel(db, channel_id=channel_db_id, user_id=owner_id) if channel else []
            back_callback = "edit_hashtags_start" # Назад к выбору канала
            name_attr = "feed"; id_attr = "feed_id"
            text_key = "edit_hashtags_select_feed_title" # TODO: Add channel name to text?
            current_state = EDIT_HASHTAGS_SELECT_FEED
        else:
            logger.error(f"Unknown pagination prefix: {prefix}")
            await query.edit_message_text(get_text("error_occurred", context))
            return ConversationHandler.END

    # Рассчитываем общее количество страниц
    total_items = len(items)
    total_pages = (total_items + page_size - 1) // page_size
    page = max(1, min(page, total_pages)) # Корректируем номер страницы снова, т.к. total_items мог измениться

    # Строим клавиатуру для выбора элемента
    # Префикс для callback_data кнопок выбора должен быть без "page_"
    selection_prefix = prefix.replace("page_", "")
    keyboard = build_selection_keyboard(
        items=items, # Передаем полный список, пагинация внутри build_selection_keyboard
        data_prefix=selection_prefix,
        name_attr=name_attr,
        id_attr=id_attr,
        back_callback=back_callback,
        page=page,
        page_size=page_size,
        # Переводы
        back_text=get_text("back_button", context),
        prev_text=get_text("pagination_prev", context),
        next_text=get_text("pagination_next", context),
        channel_item_name_format=get_text("channel_item_name", context),
        feed_item_name_format=get_text("feed_item_name", context),
        feed_subscription_item_format=get_text("feed_subscription_item", context),
        feed_subscription_no_hashtags_text=get_text("feed_subscription_no_hashtags", context)
    )

    # Получаем локализованный текст заголовка
    text = get_text(text_key, context, page=page, total_pages=total_pages)

    try:
        await query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True
        )
    except Exception as e:
        logger.error(f"Error updating pagination message (prefix {prefix}): {e}", exc_info=True)
        # Пытаемся отправить новое сообщение как fallback
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=get_text("error_occurred", context), # Общая ошибка
            # Здесь нужна какая-то общая клавиатура возврата, например, главное меню
            # reply_markup=build_main_menu_keyboard(...)
        )
        return ConversationHandler.END # Завершаем, так как состояние потеряно

    return current_state # Возвращаем состояние, соответствующее текущему шагу диалога
