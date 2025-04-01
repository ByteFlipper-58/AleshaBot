# handlers/channels.py
import logging
import asyncio

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Правильный импорт ParseMode

# Локальные импорты
from ..config import BOT_MODE
from ..database import (
    get_db, get_all_channels, add_channel, get_channel, delete_channel
)
from ..constants import (
    CHANNELS_MENU, ADD_CHANNEL_FORWARD, DELETE_CHANNEL_CONFIRM, # Обновленные состояния
    CHANNEL_ID_DB, PAGE_SIZE
)
from ..keyboards import (
    build_channels_menu_keyboard, build_paginated_list_keyboard, build_back_button
)
from .common import is_authorized
from .navigation import channels_menu_back # Импортируем channels_menu_back из navigation
from ..localization import get_text

logger = logging.getLogger(__name__)

# --- Просмотр списка каналов ---

async def list_channels_button(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """Отображает список каналов с пагинацией и кнопками управления."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        if query: await query.answer(get_text("no_access_inline", context), show_alert=True)
        return CHANNELS_MENU

    if query: await query.answer()

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channels = get_all_channels(db, user_id=owner_id)

        total_items = len(channels)
        page_size = PAGE_SIZE
        total_pages = (total_items + page_size - 1) // page_size
        page = max(1, min(page, total_pages))

        text = ""
        reply_markup = None

        if not channels:
            text = get_text("list_channels_empty", context)
            reply_markup = build_channels_menu_keyboard(
                add_text=get_text("channels_menu_add", context),
                list_text=get_text("channels_menu_list", context),
                back_text=get_text("channels_menu_back", context)
            )
        else:
            text = get_text("list_channels_title", context, page=page, total_pages=total_pages) + "\n\n"
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_channels = channels[start_index:end_index]

            for channel in paginated_channels:
                 channel_name = channel.name or get_text("channel_item_name", context, item_chat_id=channel.chat_id)
                 text += (
                     f"<b>{channel_name} (ID: {channel.chat_id})</b>\n"
                 )

            reply_markup = build_paginated_list_keyboard(
                items=paginated_channels,
                prefix="channel_action_",
                page=page,
                page_size=page_size,
                back_callback="channels_menu_back",
                back_text=get_text("back_button", context),
                prev_text=get_text("pagination_prev", context),
                next_text=get_text("pagination_next", context),
                item_name_format=get_text("channel_item_name", context),
                item_name_with_title_format=get_text("channel_item_name_with_title", context),
                channel_item_name_format=get_text("channel_item_name", context),
                feed_action_delay_format="",
                feed_action_delete_text="",
                channel_action_delete_text=get_text("channel_action_delete", context)
            )

        if len(text) > 4096:
            text = text[:4090] + "...\n\n(List too long)" # TODO: Localize

        edit_func = query.edit_message_text if query else context.bot.send_message
        kwargs = {'chat_id': update.effective_chat.id} if not query else {}

        try:
            await edit_func(
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Error displaying channel list: {e}", exc_info=True)
            if query:
                 await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=get_text("list_channels_error", context),
                    reply_markup=build_channels_menu_keyboard(
                        add_text=get_text("channels_menu_add", context),
                        list_text=get_text("channels_menu_list", context),
                        back_text=get_text("channels_menu_back", context)
                    )
                 )

    return CHANNELS_MENU

# --- Добавление канала через пересылку сообщения ---

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог добавления нового канала: просит переслать сообщение."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return CHANNELS_MENU

    await query.answer()
    prompt_text = get_text("add_channel_forward_prompt", context, default="Чтобы добавить канал или группу, перешлите сюда любое сообщение из этого чата.")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(get_text("cancel", context, default="Отмена"), callback_data="cancel")]])
    await query.edit_message_text(text=prompt_text, reply_markup=keyboard)
    return ADD_CHANNEL_FORWARD

async def add_channel_handle_forward(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает пересланное сообщение для добавления канала."""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    message = update.message
    # Используем message.forward_origin для получения информации об источнике
    forward_origin = message.forward_origin

    if not forward_origin:
        await message.reply_text(get_text("add_channel_forward_not_forwarded", context, default="Это не пересланное сообщение. Пожалуйста, перешлите сообщение из нужного канала или группы."))
        return ADD_CHANNEL_FORWARD

    # Проверяем тип источника
    if forward_origin.type not in ['channel', 'group', 'supergroup']:
         await message.reply_text(get_text("add_channel_forward_not_chat", context, default="Пожалуйста, перешлите сообщение из канала или группы, а не от пользователя."))
         return ADD_CHANNEL_FORWARD

    # Извлекаем данные из forward_origin.chat (это объект Chat)
    # Для каналов используем chat.id и chat.title
    # Для групп используем chat.id и chat.title
    chat_id = str(forward_origin.chat.id)
    chat_name = forward_origin.chat.title

    user_id = update.effective_user.id

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = None
        error_message = None
        try:
            channel = add_channel(db, chat_id=chat_id, name=chat_name, user_id=owner_id)
            if channel:
                success_text = get_text("add_channel_success", context, channel_name=(channel.name or channel.chat_id))
                await update.message.reply_text(success_text)
            else:
                existing_channel = get_channel(db, chat_id=chat_id, user_id=owner_id)
                if existing_channel:
                     error_message = get_text("add_channel_already_exists", context, chat_id=chat_id)
                else:
                     error_message = get_text("add_channel_error", context, error="Unknown database issue")
                await update.message.reply_text(error_message)
        except Exception as e:
            logger.error(f"Error adding channel {chat_id} by user {user_id} via forward: {e}", exc_info=True)
            error_message = get_text("add_channel_error", context, error=str(e))
            await update.message.reply_text(error_message)

    return await channels_menu_back(update, context)

# --- Управление существующими каналами (удаление) ---

async def channel_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок действий (удалить) для канала."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return CHANNELS_MENU

    await query.answer()
    data = query.data
    parts = data.split('_')
    action_prefix = parts[0] + "_" + parts[1]
    command = parts[2]
    try:
        item_id = int(parts[3]) # Внутренний ID канала из БД
    except (IndexError, ValueError):
        logger.error(f"Invalid callback_data in channel_action_handler: {data}")
        await query.message.reply_text(get_text("error_occurred", context))
        return await channels_menu_back(update, context)

    context.user_data[CHANNEL_ID_DB] = item_id

    if action_prefix == "delete_channel" and command == "confirm":
        return await delete_channel_confirm_prompt(update, context, item_id)
    else:
        logger.warning(f"Unknown callback in channel_action_handler: {data}")
        await query.message.reply_text(get_text("unknown_command", context))
        return await channels_menu_back(update, context)

# --- Удаление канала ---

async def delete_channel_confirm_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, channel_db_id: int) -> int:
    """Запрашивает подтверждение удаления канала."""
    query = update.callback_query
    user_id = update.effective_user.id

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
        if not channel:
            await query.edit_message_text(get_text("delete_channel_not_found", context),
                                          reply_markup=build_channels_menu_keyboard(
                                              add_text=get_text("channels_menu_add", context),
                                              list_text=get_text("channels_menu_list", context),
                                              back_text=get_text("channels_menu_back", context)
                                          ))
            return CHANNELS_MENU

        text = get_text("delete_channel_confirm_prompt", context,
                        channel_name=(channel.name or channel.chat_id),
                        chat_id=channel.chat_id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text("delete_channel_confirm_yes", context), callback_data=f"delete_channel_do_{channel_db_id}")],
            [InlineKeyboardButton(get_text("delete_channel_confirm_no", context), callback_data="list_channels_refresh")]
        ])
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return DELETE_CHANNEL_CONFIRM

async def delete_channel_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает подтверждение или отмену удаления канала."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return CHANNELS_MENU

    await query.answer()
    data = query.data

    if data.startswith("delete_channel_do_"):
        try:
            channel_db_id = int(data.split('_')[-1])
        except (IndexError, ValueError):
             logger.error(f"Invalid callback_data in delete_channel_confirm_handler: {data}")
             await query.message.reply_text(get_text("error_occurred", context))
             return await list_channels_button(update, context)

        with next(get_db()) as db:
            owner_id = user_id if BOT_MODE == 'public' else None
            channel = get_channel(db, channel_db_id=channel_db_id, user_id=owner_id)
            if channel:
                channel_name_deleted = channel.name or channel.chat_id
                deleted = delete_channel(db, chat_id=channel.chat_id, user_id=owner_id)
                message = get_text("delete_channel_success", context, channel_name=channel_name_deleted) if deleted \
                    else get_text("delete_channel_error", context)
                await query.edit_message_text(message)
            else:
                await query.edit_message_text(get_text("delete_channel_not_found", context))
        await asyncio.sleep(1.5)
        return await list_channels_button(update, context)

    elif data == "list_channels_refresh":
        return await list_channels_button(update, context)
    else:
        logger.warning(f"Unknown callback in delete_channel_confirm_handler: {data}")
        return await channels_menu_back(update, context)
