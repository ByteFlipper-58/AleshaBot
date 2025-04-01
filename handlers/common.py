# handlers/common.py
import logging
from urllib.parse import urlparse
import asyncio

from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
from telegram.constants import ParseMode # Правильный импорт ParseMode

# Локальные импорты
from config import BOT_MODE, ADMIN_USER_IDS
from database import get_db, get_or_create_user, update_user_language
from constants import (
    MAIN_MENU, # Оставляем только MAIN_MENU для возврата из cancel
    USER_LANGUAGE, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES
)
from keyboards import (
    build_main_menu_keyboard # Оставляем только клавиатуру главного меню
)
from localization import get_text

logger = logging.getLogger(__name__)

# --- Вспомогательные функции ---

def is_valid_url(url: str) -> bool:
    """Проверяет, является ли строка валидным URL."""
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except ValueError:
        return False

def is_authorized(update: Update) -> bool:
    """Проверяет авторизацию пользователя."""
    if BOT_MODE == 'public':
        return True
    user_id = update.effective_user.id
    if user_id in ADMIN_USER_IDS:
        return True
    logger.warning(f"Неавторизованный доступ от пользователя {user_id}")
    return False

# --- Основные обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Обработчик команды /start и возврата в главное меню."""
    user = update.effective_user
    if not is_authorized(update):
        no_access_text = get_text("no_access", context)
        no_access_inline_text = get_text("no_access_inline", context)
        if update.message:
            await update.message.reply_text(no_access_text)
        elif update.callback_query:
            await update.callback_query.answer(no_access_inline_text, show_alert=True)
        return ConversationHandler.END

    # Сохраняем или обновляем пользователя в БД
    with next(get_db()) as db:
        db_user = get_or_create_user(db, user.id, user.username, user.first_name, user.last_name)
        context.user_data[USER_LANGUAGE] = getattr(db_user, 'language_code', DEFAULT_LANGUAGE) or DEFAULT_LANGUAGE

    text = get_text("greeting", context, user_mention=user.mention_html()) \
           + " " + get_text("choose_action", context)

    keyboard = build_main_menu_keyboard(
        feeds_text=get_text("main_menu_feeds", context),
        channels_text=get_text("main_menu_channels", context),
        subs_text=get_text("main_menu_subscriptions", context),
        check_text=get_text("main_menu_force_check", context),
        settings_text=get_text("main_menu_settings", context)
    )

    if update.callback_query:
        await update.callback_query.answer()
        try:
            await update.callback_query.edit_message_text(
                text=text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
        except Exception as e:
            logger.debug(f"Ошибка редактирования сообщения в start: {e}")
            await context.bot.send_message(
                chat_id=update.effective_chat.id, text=text, reply_markup=keyboard, parse_mode=ParseMode.HTML
            )
    else:
        await update.message.reply_html(text=text, reply_markup=keyboard)

    return MAIN_MENU

async def cancel_conversation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Отменяет текущий диалог и возвращает в главное меню."""
    text = get_text("action_cancelled", context)
    reply_markup = build_main_menu_keyboard(
        feeds_text=get_text("main_menu_feeds", context),
        channels_text=get_text("main_menu_channels", context),
        subs_text=get_text("main_menu_subscriptions", context),
        check_text=get_text("main_menu_force_check", context),
        settings_text=get_text("main_menu_settings", context)
    )

    if update.callback_query:
        await update.callback_query.answer()
        await update.callback_query.edit_message_text(text=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML)
    elif update.message:
        await update.message.reply_html(text=text, reply_markup=reply_markup)

    return MAIN_MENU
