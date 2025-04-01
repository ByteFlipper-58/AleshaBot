# handlers/navigation.py
import logging
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

# Локальные импорты (относительные)
from ..constants import (
    MAIN_MENU, FEEDS_MENU, CHANNELS_MENU, SUBS_MENU, SETTINGS_MENU, SELECT_LANGUAGE
)
from ..keyboards import (
    build_main_menu_keyboard, build_feeds_menu_keyboard,
    build_channels_menu_keyboard, build_subs_menu_keyboard,
    build_settings_menu_keyboard, build_language_selection_keyboard
)
from ..localization import get_text
from .common import is_authorized, start # Импортируем start для возврата в главное меню

logger = logging.getLogger(__name__)

# --- Навигация по меню ---

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок в главном меню."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return MAIN_MENU

    await query.answer()
    data = query.data

    if data == "feeds_menu":
        text = get_text("feeds_menu_title", context)
        keyboard = build_feeds_menu_keyboard(
            add_text=get_text("feeds_menu_add", context),
            list_text=get_text("feeds_menu_list", context),
            back_text=get_text("feeds_menu_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return FEEDS_MENU
    elif data == "channels_menu":
        text = get_text("channels_menu_title", context)
        keyboard = build_channels_menu_keyboard(
            add_text=get_text("channels_menu_add", context),
            list_text=get_text("channels_menu_list", context),
            back_text=get_text("channels_menu_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return CHANNELS_MENU
    elif data == "subs_menu":
        text = get_text("subs_menu_title", context)
        keyboard = build_subs_menu_keyboard(
            subscribe_text=get_text("subs_menu_subscribe", context),
            unsubscribe_text=get_text("subs_menu_unsubscribe", context),
            edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
            list_subs_text=get_text("subs_menu_list_subs", context),
            back_text=get_text("subs_menu_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return SUBS_MENU
    elif data == "force_check_all":
        from .force_check import force_check_feeds # Оставляем импорт здесь
        await query.message.reply_text(get_text("force_check_starting", context))
        asyncio.create_task(force_check_feeds(update, context, feed_id=None))
        return MAIN_MENU
    elif data == "settings_menu":
        text = get_text("settings_menu_title", context)
        keyboard = build_settings_menu_keyboard(
            select_lang_text=get_text("settings_menu_select_language", context),
            back_text=get_text("settings_menu_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return SETTINGS_MENU
    else:
        await query.message.reply_text(get_text("unknown_command", context))
        return MAIN_MENU

async def feeds_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок в меню управления лентами."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return FEEDS_MENU

    await query.answer()
    data = query.data

    if data == "main_menu":
        return await start(update, context) # Используем импортированную start
    logger.warning(f"Необработанный callback в feeds_menu_handler: {data}")
    text = get_text("feeds_menu_title", context)
    keyboard = build_feeds_menu_keyboard(
        add_text=get_text("feeds_menu_add", context),
        list_text=get_text("feeds_menu_list", context),
        back_text=get_text("feeds_menu_back", context)
    )
    await query.edit_message_text(text=text, reply_markup=keyboard)
    return FEEDS_MENU

async def channels_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок в меню управления каналами."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return CHANNELS_MENU

    await query.answer()
    data = query.data

    if data == "main_menu":
        return await start(update, context)
    logger.warning(f"Необработанный callback в channels_menu_handler: {data}")
    text = get_text("channels_menu_title", context)
    keyboard = build_channels_menu_keyboard(
        add_text=get_text("channels_menu_add", context),
        list_text=get_text("channels_menu_list", context),
        back_text=get_text("channels_menu_back", context)
    )
    await query.edit_message_text(text=text, reply_markup=keyboard)
    return CHANNELS_MENU

async def subs_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок в меню управления подписками."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SUBS_MENU

    await query.answer()
    data = query.data

    if data == "main_menu":
        return await start(update, context)
    logger.warning(f"Необработанный callback в subs_menu_handler: {data}")
    text = get_text("subs_menu_title", context)
    keyboard = build_subs_menu_keyboard(
        subscribe_text=get_text("subs_menu_subscribe", context),
        unsubscribe_text=get_text("subs_menu_unsubscribe", context),
        edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
        list_subs_text=get_text("subs_menu_list_subs", context),
        back_text=get_text("subs_menu_back", context)
    )
    await query.edit_message_text(text=text, reply_markup=keyboard)
    return SUBS_MENU

# --- Обработчики меню настроек (перенесены из common.py) ---

async def settings_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает нажатия кнопок в меню настроек."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SETTINGS_MENU

    await query.answer()
    data = query.data

    if data == "main_menu":
        return await start(update, context)
    elif data == "select_language_menu":
        text = get_text("select_language_title", context)
        keyboard = build_language_selection_keyboard(
            ru_text=get_text("select_language_ru", context),
            en_text=get_text("select_language_en", context),
            back_text=get_text("select_language_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return SELECT_LANGUAGE
    else:
        logger.warning(f"Необработанный callback в settings_menu_handler: {data}")
        text = get_text("settings_menu_title", context)
        keyboard = build_settings_menu_keyboard(
            select_lang_text=get_text("settings_menu_select_language", context),
            back_text=get_text("settings_menu_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return SETTINGS_MENU

async def select_language_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обрабатывает выбор языка."""
    query = update.callback_query
    if not is_authorized(update):
        await query.answer(get_text("no_access_inline", context), show_alert=True)
        return SELECT_LANGUAGE

    await query.answer()
    data = query.data
    user_id = update.effective_user.id
    new_lang = None

    if data == "set_language_ru":
        new_lang = "ru"
    elif data == "set_language_en":
        new_lang = "en"
    elif data == "settings_menu":
        text = get_text("settings_menu_title", context)
        keyboard = build_settings_menu_keyboard(
            select_lang_text=get_text("settings_menu_select_language", context),
            back_text=get_text("settings_menu_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return SETTINGS_MENU
    else:
        logger.warning(f"Необработанный callback в select_language_handler: {data}")
        text = get_text("select_language_title", context)
        keyboard = build_language_selection_keyboard(
            ru_text=get_text("select_language_ru", context),
            en_text=get_text("select_language_en", context),
            back_text=get_text("select_language_back", context)
        )
        await query.edit_message_text(text=text, reply_markup=keyboard)
        return SELECT_LANGUAGE

    if new_lang and new_lang in context.application.bot_data.get("supported_languages", ["en", "ru"]): # Получаем из bot_data
        context.user_data[context.application.bot_data.get("user_language_key", "user_language")] = new_lang
        try:
            from ..database import update_user_language, get_db # Импорт внутри, т.к. файл может быть импортирован раньше database
            with next(get_db()) as db:
                update_user_language(db, user_id, new_lang)
            logger.info(f"User {user_id} set language to {new_lang}")
            success_text = get_text("language_updated", context)
            await query.edit_message_text(text=success_text)
            await asyncio.sleep(1.5)
            return await start(update, context)

        except ImportError:
             logger.error("Функция update_user_language не найдена в database.py")
             await query.edit_message_text(get_text("error_saving_language", context))
             text = get_text("settings_menu_title", context)
             keyboard = build_settings_menu_keyboard(
                 select_lang_text=get_text("settings_menu_select_language", context),
                 back_text=get_text("settings_menu_back", context)
             )
             await query.edit_message_text(text=text, reply_markup=keyboard)
             return SETTINGS_MENU
        except Exception as e:
            logger.error(f"Ошибка при обновлении языка для пользователя {user_id}: {e}")
            await query.edit_message_text(get_text("error_saving_language_occurred", context))
            text = get_text("settings_menu_title", context)
            keyboard = build_settings_menu_keyboard(
                select_lang_text=get_text("settings_menu_select_language", context),
                back_text=get_text("settings_menu_back", context)
            )
            await query.edit_message_text(text=text, reply_markup=keyboard)
            return SETTINGS_MENU
    else:
        return SELECT_LANGUAGE


# --- Функции возврата в предыдущие меню (перенесены из common.py) ---

async def feeds_menu_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возвращает пользователя в меню управления лентами."""
    text = get_text("feeds_menu_title", context)
    keyboard = build_feeds_menu_keyboard(
        add_text=get_text("feeds_menu_add", context),
        list_text=get_text("feeds_menu_list", context),
        back_text=get_text("feeds_menu_back", context)
    )
    reply_func = update.message.reply_text if update.message else update.callback_query.edit_message_text
    if update.callback_query:
        await update.callback_query.answer()
    await reply_func(text=text, reply_markup=keyboard)
    return FEEDS_MENU

async def channels_menu_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возвращает пользователя в меню управления каналами."""
    text = get_text("channels_menu_title", context)
    keyboard = build_channels_menu_keyboard(
        add_text=get_text("channels_menu_add", context),
        list_text=get_text("channels_menu_list", context),
        back_text=get_text("channels_menu_back", context)
    )
    reply_func = update.message.reply_text if update.message else update.callback_query.edit_message_text
    if update.callback_query:
        await update.callback_query.answer()
    await reply_func(text=text, reply_markup=keyboard)
    return CHANNELS_MENU

async def subs_menu_back(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Возвращает пользователя в меню управления подписками."""
    text = get_text("subs_menu_title", context)
    keyboard = build_subs_menu_keyboard(
        subscribe_text=get_text("subs_menu_subscribe", context),
        unsubscribe_text=get_text("subs_menu_unsubscribe", context),
        edit_hashtags_text=get_text("subs_menu_edit_hashtags", context),
        list_subs_text=get_text("subs_menu_list_subs", context),
        back_text=get_text("subs_menu_back", context)
    )
    reply_func = update.message.reply_text if update.message else update.callback_query.edit_message_text
    if update.callback_query:
        await update.callback_query.answer()
    await reply_func(text=text, reply_markup=keyboard)
    return SUBS_MENU
