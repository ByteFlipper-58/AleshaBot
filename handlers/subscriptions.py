# handlers/subscriptions.py
import logging
import asyncio

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Правильный импорт ParseMode

# Локальные импорты
from config import BOT_MODE
from database import (
    get_db, get_all_feeds, get_all_channels, get_channel, get_feed,
    subscribe_channel_to_feed, unsubscribe_channel_from_feed,
    get_subscriptions_for_channel, get_subscription, update_subscription_hashtags,
    format_hashtags
)
from constants import (
    SUBS_MENU, SUBSCRIBE_SELECT_FEED, SUBSCRIBE_SELECT_CHANNEL, SUBSCRIBE_GET_HASHTAGS,
    UNSUBSCRIBE_SELECT_CHANNEL, UNSUBSCRIBE_SELECT_FEED,
    LIST_SUBS_SELECT_CHANNEL,
    EDIT_HASHTAGS_SELECT_CHANNEL, EDIT_HASHTAGS_SELECT_FEED, EDIT_HASHTAGS_GET_VALUE,
    FEED_ID, CHANNEL_ID_DB, HASHTAGS, CURRENT_PAGE, PAGE_SIZE
)
from keyboards import (
    build_subs_menu_keyboard, build_selection_keyboard,
    build_back_button
)
from handlers.common import is_authorized # Убедимся, что subs_menu_back здесь нет
from handlers.navigation import subs_menu_back # Убедимся, что импорт отсюда
from localization import get_text

logger = logging.getLogger(__name__)

# --- Подписка канала на ленту ---

async def subscribe_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог подписки канала на ленту: Шаг 1 - выбор ленты."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        feeds = get_all_feeds(db, user_id=owner_id)
        if not feeds:
            await query.edit_message_text(
                get_text("subscribe_no_feeds", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=feeds,
            data_prefix="sub_feed_",
            name_attr="name",
            id_attr="id",
            back_callback="subs_menu_back",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format="",
            feed_subscription_no_hashtags_text=""
        )
        await query.edit_message_text(get_text("subscribe_select_feed_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return SUBSCRIBE_SELECT_FEED

async def subscribe_select_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор ленты: Шаг 2 - выбор канала."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        feed_id = int(query.data.replace("sub_feed_", ""))
    except (ValueError, AttributeError):
        logger.error(f"Invalid callback_data in subscribe_select_feed: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    context.user_data[FEED_ID] = feed_id
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channels = get_all_channels(db, user_id=owner_id)
        if not channels:
            await query.edit_message_text(
                get_text("subscribe_no_channels", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=channels,
            data_prefix=f"sub_chan_{feed_id}_",
            name_attr="name",
            id_attr="id",
            back_callback="subscribe_start",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format="",
            feed_subscription_no_hashtags_text=""
        )
        await query.edit_message_text(get_text("subscribe_select_channel_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return SUBSCRIBE_SELECT_CHANNEL

async def subscribe_select_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор канала: Шаг 3 - ввод хештегов."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        parts = query.data.split('_')
        feed_id = int(parts[2])
        channel_db_id = int(parts[3])
    except (IndexError, ValueError, AttributeError):
        logger.error(f"Invalid callback_data in subscribe_select_channel: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    context.user_data[FEED_ID] = feed_id
    context.user_data[CHANNEL_ID_DB] = channel_db_id

    await query.edit_message_text(get_text("subscribe_prompt_hashtags", context))
    return SUBSCRIBE_GET_HASHTAGS

async def subscribe_get_hashtags(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает хештеги и завершает подписку."""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    hashtags_text = update.message.text
    feed_id = context.user_data.get(FEED_ID)
    channel_db_id = context.user_data.get(CHANNEL_ID_DB)
    user_id = update.effective_user.id

    if feed_id is None or channel_db_id is None:
        await update.message.reply_text(get_text("error_occurred", context))
        context.user_data.pop(FEED_ID, None)
        context.user_data.pop(CHANNEL_ID_DB, None)
        return await subs_menu_back(update, context)

    hashtags = None if hashtags_text == '-' else hashtags_text

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
        feed = get_feed(db, feed_id=feed_id, user_id=owner_id)

        if not channel or not feed:
            await update.message.reply_text(get_text("error_occurred", context) + " (Channel or Feed not found)")
        else:
            try:
                success, db_message_key_or_text = subscribe_channel_to_feed(
                    db, chat_id=channel.chat_id, feed_id=feed_id, hashtags=hashtags, user_id=owner_id
                )
                if success:
                    formatted_hashtags = format_hashtags(hashtags) or get_text("list_subs_no_hashtags", context)
                    final_message = get_text("subscribe_success", context,
                                             channel_name=(channel.name or channel.chat_id),
                                             feed_name=(feed.name or feed.url),
                                             hashtags=formatted_hashtags)
                elif db_message_key_or_text == "subscribe_already_exists":
                     final_message = get_text("subscribe_already_exists", context)
                else:
                     final_message = get_text("subscribe_error", context, error=db_message_key_or_text)

                await update.message.reply_text(final_message)
            except Exception as e:
                logger.error(f"Error subscribing channel {channel.chat_id} to feed {feed_id}: {e}", exc_info=True)
                await update.message.reply_text(get_text("subscribe_error", context, error=str(e)))

    context.user_data.pop(FEED_ID, None)
    context.user_data.pop(CHANNEL_ID_DB, None)
    return await subs_menu_back(update, context)

# --- Отписка канала от ленты ---

async def unsubscribe_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог отписки: Шаг 1 - выбор канала."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channels = get_all_channels(db, user_id=owner_id)
        if not channels:
            await query.edit_message_text(
                get_text("unsubscribe_no_channels", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=channels,
            data_prefix="unsub_chan_",
            name_attr="name",
            id_attr="id",
            back_callback="subs_menu_back",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format="",
            feed_subscription_no_hashtags_text=""
        )
        await query.edit_message_text(get_text("unsubscribe_select_channel_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return UNSUBSCRIBE_SELECT_CHANNEL

async def unsubscribe_select_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор канала: Шаг 2 - выбор ленты для отписки."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        channel_db_id = int(query.data.replace("unsub_chan_", ""))
    except (ValueError, AttributeError):
        logger.error(f"Invalid callback_data in unsubscribe_select_channel: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    context.user_data[CHANNEL_ID_DB] = channel_db_id
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
        if not channel:
            await query.edit_message_text(
                get_text("error_occurred", context) + " (Channel not found)",
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        subscriptions = get_subscriptions_for_channel(db, channel_id=channel_db_id, user_id=owner_id)
        if not subscriptions:
            await query.edit_message_text(
                get_text("unsubscribe_no_subscriptions", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=subscriptions,
            data_prefix=f"unsub_feed_{channel_db_id}_",
            name_attr="feed",
            id_attr="feed_id",
            back_callback="unsubscribe_start",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format=get_text("feed_subscription_item", context),
            feed_subscription_no_hashtags_text=get_text("feed_subscription_no_hashtags", context)
        )
        await query.edit_message_text(get_text("unsubscribe_select_feed_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return UNSUBSCRIBE_SELECT_FEED

async def unsubscribe_select_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор ленты и завершает отписку."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        parts = query.data.split('_')
        channel_db_id = int(parts[2])
        feed_id = int(parts[3])
    except (IndexError, ValueError, AttributeError):
        logger.error(f"Invalid callback_data in unsubscribe_select_feed: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
        feed = get_feed(db, feed_id=feed_id, user_id=owner_id)

        if not channel or not feed:
            await query.edit_message_text(
                get_text("error_occurred", context) + " (Channel or Feed not found)",
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
        else:
            try:
                if unsubscribe_channel_from_feed(db, chat_id=channel.chat_id, feed_id=feed_id, user_id=owner_id):
                    message = get_text("unsubscribe_success", context,
                                       channel_name=(channel.name or channel.chat_id),
                                       feed_name=(feed.name or feed.url))
                else:
                    message = get_text("unsubscribe_not_found", context)
                await query.edit_message_text(message)
            except Exception as e:
                 logger.error(f"Error unsubscribing channel {channel.chat_id} from feed {feed_id}: {e}", exc_info=True)
                 await query.edit_message_text(get_text("unsubscribe_error", context))

    context.user_data.pop(FEED_ID, None)
    context.user_data.pop(CHANNEL_ID_DB, None)
    keyboard = InlineKeyboardMarkup([build_back_button(get_text("back_button", context), "subs_menu_back")])
    try:
        await query.edit_message_reply_markup(reply_markup=keyboard)
    except Exception as e:
        logger.debug(f"Could not edit reply_markup in unsubscribe_select_feed: {e}")
        await query.message.reply_text(get_text("back_button", context) + "?", reply_markup=keyboard)

    return SUBS_MENU

# --- Просмотр подписок канала ---

async def list_subs_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает просмотр подписок: Шаг 1 - выбор канала."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channels = get_all_channels(db, user_id=owner_id)
        if not channels:
            await query.edit_message_text(
                get_text("list_subs_no_channels", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=channels,
            data_prefix="listsub_chan_",
            name_attr="name",
            id_attr="id",
            back_callback="subs_menu_back",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format="",
            feed_subscription_no_hashtags_text=""
        )
        await query.edit_message_text(get_text("list_subs_select_channel_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return LIST_SUBS_SELECT_CHANNEL

async def list_subs_select_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор канала и отображает его подписки."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        channel_db_id = int(query.data.replace("listsub_chan_", ""))
    except (ValueError, AttributeError):
        logger.error(f"Invalid callback_data in list_subs_select_channel: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
        if not channel:
            await query.edit_message_text(
                get_text("error_occurred", context) + " (Channel not found)",
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        subscriptions = get_subscriptions_for_channel(db, channel_id=channel_db_id, user_id=owner_id)
        text = get_text("list_subs_title", context, channel_name=(channel.name or channel.chat_id)) + "\n\n"
        if not subscriptions:
            text += get_text("list_subs_empty", context)
        else:
            for sub in subscriptions:
                feed = sub.feed
                hashtags_display = sub.hashtags or get_text("list_subs_no_hashtags", context)
                feed_name = feed.name or get_text("feed_item_name", context, item_id=feed.id)
                text += get_text("list_subs_entry", context,
                                 feed_name=feed_name,
                                 feed_id=feed.id,
                                 hashtags=hashtags_display) + "\n\n"

        keyboard = InlineKeyboardMarkup([build_back_button(get_text("back_button", context), "list_subs_start")])

        if len(text) > 4096:
            text = text[:4090] + "..."

        await query.edit_message_text(
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML, # Используем правильную константу
            disable_web_page_preview=True
        )

    return LIST_SUBS_SELECT_CHANNEL

# --- Редактирование хештегов подписки ---

async def edit_hashtags_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает редактирование хештегов: Шаг 1 - выбор канала."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channels = get_all_channels(db, user_id=owner_id)
        if not channels:
            await query.edit_message_text(
                get_text("edit_hashtags_no_channels", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=channels,
            data_prefix="editht_chan_",
            name_attr="name",
            id_attr="id",
            back_callback="subs_menu_back",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format="",
            feed_subscription_no_hashtags_text=""
        )
        await query.edit_message_text(get_text("edit_hashtags_select_channel_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return EDIT_HASHTAGS_SELECT_CHANNEL

async def edit_hashtags_select_channel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор канала: Шаг 2 - выбор подписки (ленты)."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        channel_db_id = int(query.data.replace("editht_chan_", ""))
    except (ValueError, AttributeError):
        logger.error(f"Invalid callback_data in edit_hashtags_select_channel: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    context.user_data[CHANNEL_ID_DB] = channel_db_id
    context.user_data[CURRENT_PAGE] = 1

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
        if not channel:
            await query.edit_message_text(
                get_text("error_occurred", context) + " (Channel not found)",
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        subscriptions = get_subscriptions_for_channel(db, channel_id=channel_db_id, user_id=owner_id)
        if not subscriptions:
            await query.edit_message_text(
                get_text("edit_hashtags_no_subscriptions", context),
                reply_markup=build_subs_menu_keyboard(
                    subscribe_text=get_text("subs_menu_subscribe", context),
                    unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                    edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                    list_subs_text=get_text("subs_menu_list_subs", context),
                    back_text=get_text("subs_menu_back", context)
                )
            )
            return SUBS_MENU

        keyboard = build_selection_keyboard(
            items=subscriptions,
            data_prefix=f"editht_feed_{channel_db_id}_",
            name_attr="feed",
            id_attr="feed_id",
            back_callback="edit_hashtags_start",
            page=1,
            page_size=PAGE_SIZE,
            back_text=get_text("back_button", context),
            prev_text=get_text("pagination_prev", context),
            next_text=get_text("pagination_next", context),
            channel_item_name_format=get_text("channel_item_name", context),
            feed_item_name_format=get_text("feed_item_name", context),
            feed_subscription_item_format=get_text("feed_subscription_item", context),
            feed_subscription_no_hashtags_text=get_text("feed_subscription_no_hashtags", context)
        )
        await query.edit_message_text(get_text("edit_hashtags_select_feed_title", context, page=1, total_pages=1), reply_markup=keyboard)
        return EDIT_HASHTAGS_SELECT_FEED

async def edit_hashtags_select_feed(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор подписки: Шаг 3 - ввод новых хештегов."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    try:
        parts = query.data.split('_')
        channel_db_id = int(parts[2])
        feed_id = int(parts[3])
    except (IndexError, ValueError, AttributeError):
        logger.error(f"Invalid callback_data in edit_hashtags_select_feed: {query.data}")
        await query.edit_message_text(
            get_text("error_occurred", context),
            reply_markup=build_subs_menu_keyboard(
                subscribe_text=get_text("subs_menu_subscribe", context),
                unsubscribe_text=get_text("subs_menu_unsubscribe", context),
                edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
                list_subs_text=get_text("subs_menu_list_subs", context),
                back_text=get_text("subs_menu_back", context)
            )
        )
        return SUBS_MENU

    context.user_data[CHANNEL_ID_DB] = channel_db_id
    context.user_data[FEED_ID] = feed_id

    current_hashtags_text = get_text("list_subs_no_hashtags", context)
    feed_name = f"ID {feed_id}"
    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        subscription = get_subscription(db, channel_id=channel_db_id, feed_id=feed_id, user_id=owner_id)
        if subscription:
            if subscription.hashtags:
                current_hashtags_text = subscription.hashtags
            if subscription.feed and subscription.feed.name:
                feed_name = subscription.feed.name

    # Используем HTML для простоты, т.к. MarkdownV2 требует сложного экранирования
    prompt_text = get_text("edit_hashtags_current", context, feed_name=feed_name, hashtags=f"<code>{current_hashtags_text}</code>") + "\n" \
                  + get_text("edit_hashtags_prompt", context)

    await query.edit_message_text(
        text=prompt_text,
        parse_mode=ParseMode.HTML # Используем HTML
    )
    return EDIT_HASHTAGS_GET_VALUE # Переход к вводу хештегов

async def edit_hashtags_get_value(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает новые хештеги и обновляет подписку."""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    new_hashtags_text = update.message.text
    feed_id = context.user_data.get(FEED_ID)
    channel_db_id = context.user_data.get(CHANNEL_ID_DB)
    user_id = update.effective_user.id

    if feed_id is None or channel_db_id is None:
        await update.message.reply_text(get_text("error_occurred", context))
        context.user_data.pop(FEED_ID, None)
        context.user_data.pop(CHANNEL_ID_DB, None)
        return await subs_menu_back(update, context)

    hashtags = None if new_hashtags_text == '-' else new_hashtags_text

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        feed = get_feed(db, feed_id=feed_id, user_id=owner_id)
        feed_name = feed.name if feed else f"ID {feed_id}"
        try:
            success, db_message_key_or_text = update_subscription_hashtags(
                db, channel_id=channel_db_id, feed_id=feed_id, hashtags=hashtags, user_id=owner_id
            )
            if success:
                # from ..database import format_hashtags # Уже импортирован
                formatted_hashtags = format_hashtags(hashtags) or get_text("list_subs_no_hashtags", context)
                if hashtags is None:
                     final_message = get_text("edit_hashtags_removed", context, feed_name=feed_name)
                else:
                     final_message = get_text("edit_hashtags_success", context, feed_name=feed_name, hashtags=formatted_hashtags)
            elif db_message_key_or_text == "edit_hashtags_not_found":
                 final_message = get_text("edit_hashtags_not_found", context)
            else:
                 final_message = get_text("edit_hashtags_error", context, error=db_message_key_or_text)

            await update.message.reply_text(final_message)
        except Exception as e:
            logger.error(f"Error updating hashtags for channel {channel_db_id} and feed {feed_id}: {e}", exc_info=True)
            await update.message.reply_text(get_text("edit_hashtags_error", context, error=str(e)))

    context.user_data.pop(FEED_ID, None)
    context.user_data.pop(CHANNEL_ID_DB, None)
    return await subs_menu_back(update, context)
