# handlers/channels.py
# handlers/channels.py
import logging
import asyncio
import uuid # Для генерации request_id

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Правильный импорт ParseMode

import telegram # Добавим импорт telegram для telegram.error
from telegram.ext import MessageHandler, filters # Добавить импорты

# Локальные импорты
from config import BOT_MODE
from database import (
    get_db, get_all_channels, add_channel, get_channel, delete_channel
)
from constants import (
    CHANNELS_MENU, DELETE_CHANNEL_CONFIRM, # ADD_CHANNEL_FORWARD удален
    CHANNEL_ID_DB, PAGE_SIZE
)
# Добавляем новое состояние
ADDING_CHANNEL_LINK = uuid.uuid4()

from keyboards import (
    build_channels_menu_keyboard, build_paginated_list_keyboard, build_back_button,
    build_request_chat_keyboard
)
# Импортируем is_authorized и cancel_conversation (если он там есть, иначе уберем)
# На самом деле cancel_conversation здесь не используется, но исправим импорт
from handlers.common import is_authorized # Убираем импорт cancel/cancel_conversation, он не нужен здесь
from handlers.navigation import channels_menu_back # Импортируем channels_menu_back из navigation
from localization import get_text

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
                add_select_text=get_text("channels_menu_add_select", context), # Обновляем тексты кнопок
                add_link_text=get_text("channels_menu_add_link", context),
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
                        add_select_text=get_text("channels_menu_add_select", context), # Обновляем тексты кнопок
                        add_link_text=get_text("channels_menu_add_link", context),
                        list_text=get_text("channels_menu_list", context),
                        back_text=get_text("channels_menu_back", context)
                    )
                 )

    return CHANNELS_MENU

# --- Добавление канала через выбор чата ---

async def add_channel_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Отправляет кнопку для запроса выбора чата."""
    query = update.callback_query
    if not is_authorized(update):
        if query: await query.answer(get_text("no_access_inline", context), show_alert=True)
        return

    if query: await query.answer()

    # Генерируем уникальный ID для этого запроса
    request_id = uuid.uuid4().int & (1<<31)-1 # Генерируем положительный 31-битный int
    # Сохраняем request_id и цель во временном хранилище (например, user_data)
    # Ключ может включать user_id для предотвращения коллизий в public режиме
    context.user_data[f'chat_request_{request_id}'] = {'purpose': 'add_channel'}
    logger.info(f"Generated chat request ID {request_id} for user {update.effective_user.id} to add channel.")

    prompt_text = get_text("add_channel_select_chat_prompt", context)
    keyboard = build_request_chat_keyboard(
        button_text=get_text("add_channel_select_chat_button", context),
        request_id=request_id
    )

    # ReplyKeyboardMarkup нужно отправлять новым сообщением.
    # Если был query, сначала отредактируем старое сообщение, убрав клавиатуру.
    try:
        if query:
            await query.edit_message_text(text=prompt_text, reply_markup=None) # Убираем старую клавиатуру

        # Отправляем новое сообщение с ReplyKeyboardMarkup
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=prompt_text, # Можно оставить тот же текст или изменить
            reply_markup=keyboard
        )
    except Exception as e:
        logger.error(f"Error sending chat request button: {e}", exc_info=True)
        # Сообщаем об ошибке пользователю (в новом сообщении, если query был)
        error_text = get_text("error_occurred", context)
        # Отправляем сообщение об ошибке
        await context.bot.send_message(chat_id=update.effective_chat.id, text=error_text)
        # Очищаем user_data
        context.user_data.pop(f'chat_request_{request_id}', None)

    # Эта функция больше не возвращает состояние для ConversationHandler, т.к.
    # обработка ответа идет через MessageHandler(filters.StatusUpdate.CHAT_SHARED)

async def handle_chat_shared(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обрабатывает ответ пользователя на запрос выбора чата."""
    message = update.effective_message
    chat_shared = message.chat_shared
    user_id = update.effective_user.id

    if not chat_shared:
        logger.warning("Received update without chat_shared in handle_chat_shared.")
        return

    request_id = chat_shared.request_id
    shared_chat_id = chat_shared.chat_id
    logger.info(f"Received shared chat ID {shared_chat_id} for request ID {request_id} from user {user_id}.")

    # Проверяем request_id и цель в user_data
    request_key = f'chat_request_{request_id}'
    request_info = context.user_data.get(request_key)

    if not request_info or request_info.get('purpose') != 'add_channel':
        logger.warning(f"Received shared chat for unknown or mismatched request ID {request_id} / purpose.")
        # Можно отправить сообщение пользователю, что запрос устарел или не найден
        return

    # Очищаем user_data сразу после проверки
    context.user_data.pop(request_key, None)

    # Проверяем, является ли бот участником и администратором в выбранном чате
    chat_title = f"ID {shared_chat_id}" # Имя по умолчанию
    try:
        # Сначала пытаемся получить информацию о чате, чтобы узнать его название
        try:
            chat_info = await context.bot.get_chat(chat_id=shared_chat_id)
            chat_title = chat_info.title
        except telegram.error.BadRequest as e:
            # Если чат не найден, бот не является его участником
            if "chat not found" in str(e).lower():
                logger.warning(f"Bot is not a member of the selected chat {shared_chat_id}.")
                # Используем текст из локализации, если он есть, иначе - стандартный
                error_text = get_text("add_channel_bot_not_member", context, chat_id=shared_chat_id)
                await message.reply_text(error_text)
                return
            else:
                # Другая ошибка BadRequest при получении информации о чате
                raise e # Передаем ошибку дальше
        except Exception as e:
             logger.error(f"Unexpected error getting chat info for {shared_chat_id}: {e}", exc_info=True)
             # Используем имя по умолчанию, но продолжаем проверку прав
             pass # Продолжаем, используя chat_title по умолчанию

        # Теперь проверяем права бота в чате
        chat_member = await context.bot.get_chat_member(chat_id=shared_chat_id, user_id=context.bot.id)
        if not chat_member.status == 'administrator' or not chat_member.can_post_messages:
            # Используем текст из локализации, если он есть, иначе - стандартный
            error_text = get_text("add_channel_bot_not_admin", context, chat_title=chat_title)
            await message.reply_text(error_text)
            return

    except telegram.error.BadRequest as e:
        # Повторно ловим Chat not found на случай, если get_chat прошел, а get_chat_member нет (маловероятно)
        if "chat not found" in str(e).lower():
             logger.warning(f"Bot is not a member of the selected chat {shared_chat_id} (checked via get_chat_member).")
             # Используем текст из локализации, если он есть, иначе - стандартный
             error_text = get_text("add_channel_bot_not_member", context, chat_id=shared_chat_id)
             await message.reply_text(error_text)
             return
        else:
             # Другая ошибка BadRequest при проверке прав
             logger.error(f"BadRequest checking bot status in chat {shared_chat_id}: {e}", exc_info=True)
             await message.reply_text(get_text("error_occurred", context))
             return
    except Exception as e:
        # Любая другая неожиданная ошибка
        logger.error(f"Unexpected error checking bot status in chat {shared_chat_id}: {e}", exc_info=True)
        await message.reply_text(get_text("error_occurred", context))
        return

    # Если мы дошли сюда, бот является админом с правом постинга. Добавляем канал в БД.
    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        channel = None
        error_message = None
        try:
            channel = add_channel(db, chat_id=str(shared_chat_id), name=chat_title, user_id=owner_id)
            if channel:
                success_text = get_text("add_channel_request_success", context, chat_title=chat_title, chat_id=shared_chat_id)
                await message.reply_text(success_text)
            else:
                # Проверяем, существует ли уже
                existing_channel = get_channel(db, chat_id=str(shared_chat_id), user_id=owner_id)
                if existing_channel:
                     error_message = get_text("add_channel_request_already_exists", context, chat_title=chat_title, chat_id=shared_chat_id)
                else:
                     error_message = get_text("add_channel_request_error", context, chat_title=chat_title, error="Database issue")
                await message.reply_text(error_message)
        except Exception as e:
            logger.error(f"Error adding channel {shared_chat_id} by user {user_id} via chat_shared: {e}", exc_info=True)
            error_message = get_text("add_channel_request_error", context, chat_title=chat_title, error=str(e))
            await message.reply_text(error_message)

    # Возвращаться в меню не нужно, т.к. это обработчик отдельного update


# --- Добавление канала по ссылке/юзернейму ---

async def add_channel_link_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> object:
    """Запрашивает у пользователя ссылку или username публичного канала/группы."""
    query = update.callback_query
    if not is_authorized(update):
        if query: await query.answer(get_text("no_access_inline", context), show_alert=True)
        # Возвращаемся в меню каналов, завершая диалог добавления по ссылке
        await channels_menu_back(update, context)
        return ConversationHandler.END

    await query.answer()
    prompt_text = get_text("add_channel_link_prompt", context)
    # Редактируем сообщение, убирая кнопки меню каналов
    try:
        await query.edit_message_text(text=prompt_text)
    except Exception as e:
        logger.error(f"Error editing message in add_channel_link_start: {e}")
        # Если редактирование не удалось, отправим новое сообщение
        await context.bot.send_message(chat_id=update.effective_chat.id, text=prompt_text)

    return ADDING_CHANNEL_LINK # Переходим в состояние ожидания ссылки

async def add_channel_link_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> object:
    """Обрабатывает введенную ссылку или username канала/группы."""
    message = update.effective_message
    user_id = update.effective_user.id
    identifier = message.text.strip()

    if not identifier:
        await message.reply_text(get_text("add_channel_link_empty", context))
        return ADDING_CHANNEL_LINK # Остаемся в том же состоянии

    # Проверяем, похоже ли это на username или ссылку
    if not (identifier.startswith('@') or 't.me/' in identifier or identifier.startswith('-100')): # Добавим проверку на ID
         await message.reply_text(get_text("add_channel_link_invalid_format", context))
         return ADDING_CHANNEL_LINK

    # Убираем префикс https://t.me/ если он есть, оставляем только @username или username
    # Если это ID, оставляем как есть
    if 't.me/' in identifier:
        identifier = '@' + identifier.split('/')[-1].split('?')[0] # Убираем параметры из ссылки

    logger.info(f"User {user_id} trying to add public channel/group: {identifier}")

    chat_title = identifier # Имя по умолчанию
    shared_chat_id = None

    try:
        # Пытаемся получить информацию о чате по идентификатору
        chat_info = await context.bot.get_chat(chat_id=identifier)
        chat_title = chat_info.title
        shared_chat_id = chat_info.id
        logger.info(f"Successfully got info for public chat {identifier}: ID {shared_chat_id}, Title: {chat_title}")

        # Пытаемся добавить в БД (или обновить имя, если уже есть по ID)
        with next(get_db()) as db:
            owner_id = user_id if BOT_MODE == 'public' else None
            channel = add_channel(db, chat_id=str(shared_chat_id), name=chat_title, user_id=owner_id)

            if channel:
                success_text = get_text("add_channel_link_success", context, chat_title=chat_title, chat_id=shared_chat_id)
                await message.reply_text(success_text)
            else:
                # Возможно, канал уже существует (добавлен ранее или через выбор)
                existing_channel = get_channel(db, chat_id=str(shared_chat_id), user_id=owner_id)
                if existing_channel:
                    # Обновляем имя на всякий случай
                    if existing_channel.name != chat_title:
                         existing_channel.name = chat_title
                         db.commit()
                         logger.info(f"Updated channel name for {shared_chat_id} to '{chat_title}'")
                    info_text = get_text("add_channel_link_already_exists", context, chat_title=chat_title, chat_id=shared_chat_id)
                    await message.reply_text(info_text)
                else:
                    # Не удалось добавить по другой причине
                    error_text = get_text("add_channel_request_error", context, chat_title=chat_title, error="Database issue")
                    await message.reply_text(error_text)

    except telegram.error.BadRequest as e:
        if "chat not found" in str(e).lower() or "chat id is empty" in str(e).lower():
            logger.warning(f"Could not find public chat {identifier} provided by user {user_id}.")
            error_text = get_text("add_channel_link_not_found", context, identifier=identifier)
            await message.reply_text(error_text)
            return ADDING_CHANNEL_LINK # Просим ввести снова
        else:
            logger.error(f"BadRequest getting info for public chat {identifier}: {e}", exc_info=True)
            await message.reply_text(get_text("error_occurred", context))
            # Выходим из диалога при непонятной ошибке
            await channels_menu_back(update, context)
            return ConversationHandler.END
    except Exception as e:
        logger.error(f"Unexpected error processing public chat {identifier}: {e}", exc_info=True)
        await message.reply_text(get_text("error_occurred", context))
        # Выходим из диалога при неожиданной ошибке
        await channels_menu_back(update, context)
        return ConversationHandler.END

    # После успешного добавления или сообщения "уже существует" выходим из диалога
    await channels_menu_back(update, context) # Используем существующую функцию для возврата в меню
    return ConversationHandler.END


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
                                              add_select_text=get_text("channels_menu_add_select", context), # Обновляем тексты кнопок
                                              add_link_text=get_text("channels_menu_add_link", context),
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
