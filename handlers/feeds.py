# handlers/feeds.py
import logging
import asyncio # Добавим asyncio для sleep

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Импортируем ParseMode отсюда

# Локальные импорты
from config import BOT_MODE
from database import (
    get_db, get_all_feeds, add_feed, get_feed, delete_feed, update_feed_delay
)
from constants import (
    FEEDS_MENU, ADD_FEED_URL, ADD_FEED_DELAY, ADD_FEED_NAME,
    DELETE_FEED_CONFIRM, SET_DELAY_VALUE, FEED_URL, FEED_DELAY, FEED_ID, PAGE_SIZE
)
from keyboards import (
    build_feeds_menu_keyboard, build_paginated_list_keyboard, build_back_button
)
from handlers.common import is_authorized, is_valid_url # Убедимся, что feeds_menu_back здесь нет
from handlers.navigation import feeds_menu_back # Убедимся, что импорт отсюда
from localization import get_text # Импортируем get_text

logger = logging.getLogger(__name__)

# --- Просмотр списка лент ---

async def list_feeds_button(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 1) -> int:
    """Отображает список RSS-лент с пагинацией и кнопками управления."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        if query: await query.answer(get_text("no_access_inline", context), show_alert=True)
        return FEEDS_MENU # Возвращаемся в меню лент

    if query: await query.answer()

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        feeds = get_all_feeds(db, user_id=owner_id)

        total_items = len(feeds)
        page_size = PAGE_SIZE
        total_pages = (total_items + page_size - 1) // page_size
        page = max(1, min(page, total_pages)) # Корректируем номер страницы

        text = ""
        reply_markup = None

        if not feeds:
            text = get_text("list_feeds_empty", context)
            # Клавиатура меню лент с переводами
            reply_markup = build_feeds_menu_keyboard(
                add_text=get_text("feeds_menu_add", context),
                list_text=get_text("feeds_menu_list", context),
                back_text=get_text("feeds_menu_back", context)
            )
        else:
            text = get_text("list_feeds_title", context, page=page, total_pages=total_pages) + "\n\n"
            start_index = (page - 1) * page_size
            end_index = start_index + page_size
            paginated_feeds = feeds[start_index:end_index]

            # Формируем текст списка (можно вынести в отдельную функцию)
            for feed in paginated_feeds:
                 feed_name = feed.name or get_text("feed_item_name", context, item_id=feed.id)
                 last_checked_str = feed.last_checked.strftime('%Y-%m-%d %H:%M:%S %Z') if feed.last_checked else 'Never' # TODO: Localize 'Never'
                 feed_info = (
                     f"<b>{feed_name} (ID: {feed.id})</b>\n"
                     f"<a href='{feed.url}'>URL</a> | Delay: {feed.publish_delay_minutes} min\n" # TODO: Localize 'Delay', 'min'
                     f"Checked: {last_checked_str}" # TODO: Localize 'Checked'
                 )
                 text += feed_info + "\n\n"

            # Строим клавиатуру с пагинацией и кнопками действий, передавая переводы
            reply_markup = build_paginated_list_keyboard(
                items=paginated_feeds, # Передаем только элементы текущей страницы
                prefix="feed_action_",
                page=page,
                page_size=page_size, # page_size не используется внутри, но передаем для консистентности
                back_callback="feeds_menu_back",
                # Переведенные тексты
                back_text=get_text("back_button", context),
                prev_text=get_text("pagination_prev", context),
                next_text=get_text("pagination_next", context),
                # Форматтеры и тексты для кнопок действий
                item_name_format=get_text("feed_item_name", context), # Формат для ID, если нет имени
                item_name_with_title_format=get_text("feed_item_name_with_title", context), # Формат для имени и ID
                channel_item_name_format="", # Не используется для лент
                feed_action_delay_format=get_text("feed_action_delay", context),
                feed_action_delete_text=get_text("feed_action_delete", context),
                channel_action_delete_text="" # Не используется для лент
            )

        if len(text) > 4096: # Telegram limit
            text = text[:4090] + "...\n\n(List too long)" # TODO: Localize

        # Определяем, редактировать сообщение или отправлять новое
        edit_func = query.edit_message_text if query else context.bot.send_message
        kwargs = {'chat_id': update.effective_chat.id} if not query else {}

        try:
            await edit_func(
                text=text,
                reply_markup=reply_markup,
                parse_mode=ParseMode.HTML,
                disable_web_page_preview=True,
                **kwargs
            )
        except Exception as e:
            logger.error(f"Error displaying feed list: {e}", exc_info=True)
            # Попытка отправить сообщение, если редактирование не удалось
            if query:
                 await context.bot.send_message(
                    chat_id=update.effective_chat.id,
                    text=get_text("list_feeds_error", context), # Используем локализованную ошибку
                    reply_markup=build_feeds_menu_keyboard( # Локализованная клавиатура
                        add_text=get_text("feeds_menu_add", context),
                        list_text=get_text("feeds_menu_list", context),
                        back_text=get_text("feeds_menu_back", context)
                    )
                 )


    return FEEDS_MENU # Остаемся в меню управления лентами

# --- Добавление ленты ---

async def add_feed_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Начинает диалог добавления новой RSS-ленты."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return FEEDS_MENU # Возврат в меню лент

    await query.answer()
    await query.edit_message_text(text=get_text("add_feed_prompt_url", context))
    return ADD_FEED_URL # Переход к состоянию ожидания URL

async def add_feed_get_url(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает URL ленты от пользователя."""
    if not is_authorized(update): # Проверка на случай прямого ввода сообщения
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    url = update.message.text
    if not is_valid_url(url):
        await update.message.reply_text(get_text("add_feed_invalid_url", context))
        return ADD_FEED_URL # Остаемся в том же состоянии

    context.user_data[FEED_URL] = url
    await update.message.reply_text(get_text("add_feed_prompt_delay", context))
    return ADD_FEED_DELAY # Переход к состоянию ожидания задержки

async def add_feed_get_delay(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает задержку публикации от пользователя."""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    delay_text = update.message.text
    if not delay_text.isdigit() or int(delay_text) < 0:
        await update.message.reply_text(get_text("add_feed_invalid_delay", context))
        return ADD_FEED_DELAY # Остаемся в том же состоянии

    context.user_data[FEED_DELAY] = int(delay_text)
    await update.message.reply_text(get_text("add_feed_prompt_name", context))
    return ADD_FEED_NAME # Переход к состоянию ожидания имени

async def add_feed_get_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает имя ленты и сохраняет ее в БД."""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    name = update.message.text
    if name == '-':
        name = None # Если пользователь ввел '-', имя будет пустым

    url = context.user_data.get(FEED_URL)
    delay = context.user_data.get(FEED_DELAY)
    user_id = update.effective_user.id

    if not url or delay is None:
        await update.message.reply_text(get_text("error_occurred", context))
        context.user_data.pop(FEED_URL, None)
        context.user_data.pop(FEED_DELAY, None)
        # Возвращаемся в меню лент
        return await feeds_menu_back(update, context) # feeds_menu_back теперь локализован

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        feed = None
        error_message = None
        try:
            feed = add_feed(db, url=url, name=name, publish_delay_minutes=delay, user_id=owner_id)
            if feed:
                # Успех
                success_text = get_text("add_feed_success", context, feed_name=(feed.name or feed.url))
                await update.message.reply_text(success_text)
            else:
                # Проверяем, существует ли уже такая лента
                existing_feed = get_feed(db, url=url, user_id=owner_id)
                if existing_feed:
                    error_message = get_text("add_feed_already_exists", context, url=url)
                else:
                    error_message = get_text("add_feed_error", context, error="Unknown database issue") # TODO: Improve error detail
                await update.message.reply_text(error_message)
        except Exception as e:
             logger.error(f"Error adding feed {url} by user {user_id}: {e}", exc_info=True)
             error_message = get_text("add_feed_error", context, error=str(e))
             await update.message.reply_text(error_message)

    context.user_data.pop(FEED_URL, None)
    context.user_data.pop(FEED_DELAY, None)
    # Возвращаемся в меню лент
    return await feeds_menu_back(update, context) # feeds_menu_back теперь локализован

# --- Управление существующими лентами (удаление, задержка) ---

async def feed_action_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок действий (удалить, изменить задержку) для ленты."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return FEEDS_MENU

    await query.answer()
    data = query.data # Пример: "delete_feed_confirm_123" или "set_delay_start_123"
    parts = data.split('_')
    action_prefix = parts[0] + "_" + parts[1] # "delete_feed" или "set_delay"
    command = parts[2] # "confirm" или "start"
    try:
        item_id = int(parts[3]) # ID ленты
    except (IndexError, ValueError):
        logger.error(f"Invalid callback_data in feed_action_handler: {data}")
        await query.message.reply_text(get_text("error_occurred", context))
        return await feeds_menu_back(update, context) # Локализованный возврат

    context.user_data[FEED_ID] = item_id # Сохраняем ID ленты для следующих шагов

    if action_prefix == "delete_feed" and command == "confirm":
        # Переходим к подтверждению удаления
        return await delete_feed_confirm_prompt(update, context, item_id)
    elif action_prefix == "set_delay" and command == "start":
        # Начинаем диалог установки новой задержки
        with next(get_db()) as db:
            owner_id = update.effective_user.id if BOT_MODE == 'public' else None
            feed = get_feed(db, feed_id=item_id, user_id=owner_id)
            if feed:
                prompt_text = get_text("set_delay_prompt", context,
                                       feed_name=(feed.name or feed.url),
                                       current_delay=feed.publish_delay_minutes)
                await query.edit_message_text(prompt_text)
                return SET_DELAY_VALUE # Переходим в состояние ожидания значения задержки
            else:
                await query.edit_message_text(get_text("delete_feed_not_found", context)) # Используем текст "не найдено"
                return await feeds_menu_back(update, context) # Локализованный возврат
    else:
        logger.warning(f"Unknown callback in feed_action_handler: {data}")
        await query.message.reply_text(get_text("unknown_command", context))
        return await feeds_menu_back(update, context) # Локализованный возврат

# --- Удаление ленты ---

async def delete_feed_confirm_prompt(update: Update, context: ContextTypes.DEFAULT_TYPE, feed_id: int) -> int:
    """Запрашивает подтверждение удаления ленты."""
    query = update.callback_query
    user_id = update.effective_user.id
    # Авторизация уже проверена в feed_action_handler

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        feed = get_feed(db, feed_id=feed_id, user_id=owner_id)
        if not feed:
            await query.edit_message_text(get_text("delete_feed_not_found", context),
                                          reply_markup=build_feeds_menu_keyboard( # Локализованная клавиатура
                                              add_text=get_text("feeds_menu_add", context),
                                              list_text=get_text("feeds_menu_list", context),
                                              back_text=get_text("feeds_menu_back", context)
                                          ))
            return FEEDS_MENU

        text = get_text("delete_feed_confirm_prompt", context, feed_name=(feed.name or feed.url), feed_id=feed.id)
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton(get_text("delete_feed_confirm_yes", context), callback_data=f"delete_feed_do_{feed_id}")],
            [InlineKeyboardButton(get_text("delete_feed_confirm_no", context), callback_data="list_feeds_refresh")] # Кнопка для обновления списка
        ])
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return DELETE_FEED_CONFIRM # Переходим в состояние ожидания подтверждения

async def delete_feed_confirm_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает подтверждение или отмену удаления ленты."""
    query = update.callback_query
    user_id = update.effective_user.id
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return FEEDS_MENU

    await query.answer()
    data = query.data

    if data.startswith("delete_feed_do_"):
        try:
            feed_id = int(data.split('_')[-1])
        except (IndexError, ValueError):
             logger.error(f"Invalid callback_data in delete_feed_confirm_handler: {data}")
             await query.message.reply_text(get_text("error_occurred", context))
             return await list_feeds_button(update, context) # Обновляем список

        with next(get_db()) as db:
            owner_id = user_id if BOT_MODE == 'public' else None
            feed = get_feed(db, feed_id=feed_id, user_id=owner_id) # Получаем перед удалением для имени
            if feed:
                feed_name_deleted = feed.name or feed.url
                deleted = delete_feed(db, feed_id=feed_id, user_id=owner_id)
                message = get_text("delete_feed_success", context, feed_name=feed_name_deleted) if deleted \
                    else get_text("delete_feed_error", context)
                await query.edit_message_text(message)
            else:
                await query.edit_message_text(get_text("delete_feed_not_found", context))
        # Обновляем список лент после удаления
        # Небольшая задержка перед обновлением списка
        await asyncio.sleep(1.5)
        return await list_feeds_button(update, context)

    elif data == "list_feeds_refresh":
        # Пользователь нажал "Назад", просто обновляем список
        return await list_feeds_button(update, context)
    else:
        logger.warning(f"Unknown callback in delete_feed_confirm_handler: {data}")
        return await feeds_menu_back(update, context) # Локализованный возврат

# --- Установка задержки ---

async def set_delay_value_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Получает новое значение задержки и обновляет его в БД."""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return ConversationHandler.END

    delay_text = update.message.text
    feed_id = context.user_data.get(FEED_ID)
    user_id = update.effective_user.id

    if not feed_id:
        await update.message.reply_text(get_text("error_occurred", context) + " (Feed ID missing)") # TODO: Localize error detail
        context.user_data.pop(FEED_ID, None)
        return await feeds_menu_back(update, context) # Локализованный возврат

    if not delay_text.isdigit() or int(delay_text) < 0:
        await update.message.reply_text(get_text("add_feed_invalid_delay", context)) # Используем ту же строку ошибки
        return SET_DELAY_VALUE # Остаемся в том же состоянии

    delay_minutes = int(delay_text)

    with next(get_db()) as db:
        owner_id = user_id if BOT_MODE == 'public' else None
        feed = get_feed(db, feed_id=feed_id, user_id=owner_id) # Получаем для имени
        if feed:
            if update_feed_delay(db, feed_id=feed_id, delay_minutes=delay_minutes, user_id=owner_id):
                success_text = get_text("set_delay_success", context,
                                        feed_name=(feed.name or feed.url),
                                        delay=delay_minutes)
                await update.message.reply_text(success_text)
            else:
                # Эта ветка маловероятна, если feed найден, но на всякий случай
                await update.message.reply_text(get_text("set_delay_error", context))
        else:
            await update.message.reply_text(get_text("set_delay_not_found", context))

    context.user_data.pop(FEED_ID, None)

    # Создаем "фальшивый" query, чтобы вызвать list_feeds_button для обновления списка
    # Обновляем список лент, чтобы показать новую задержку
    # Создаем "фальшивый" update с callback_query, чтобы list_feeds_button мог отредактировать сообщение
    # Это обходной путь, т.к. list_feeds_button ожидает callback_query
    class FakeCallbackQuery:
        async def answer(self): pass
        async def edit_message_text(self, *args, **kwargs):
            # Пытаемся отредактировать исходное сообщение, которое вызвало set_delay_start_
            # Это может не сработать, если исходное сообщение было удалено или слишком старое
            original_message = context.user_data.get('_origin_message') # Предполагаем, что сохранили его
            if original_message:
                try:
                    await original_message.edit_text(*args, **kwargs)
                    return
                except Exception as e:
                    logger.warning(f"Не удалось отредактировать исходное сообщение в set_delay: {e}")
            # Fallback: отправляем новое сообщение
            await context.bot.send_message(chat_id=update.effective_chat.id, *args, **kwargs)

        message = update.message # Используем текущее сообщение для chat_id и т.д.

    fake_update = type('obj', (object,), {
        'callback_query': FakeCallbackQuery(),
        'effective_user': update.effective_user,
        'effective_chat': update.effective_chat
    })()

    # Сохраняем исходное сообщение (если оно было от callback_query) перед вызовом list_feeds_button
    # Это нужно делать в feed_action_handler при нажатии set_delay_start_
    # context.user_data['_origin_message'] = query.message # Примерно так

    return await list_feeds_button(fake_update, context)
