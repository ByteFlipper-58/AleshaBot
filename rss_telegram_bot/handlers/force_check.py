# handlers/force_check.py
import logging
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

# handlers/force_check.py
import logging
import asyncio

from telegram import Update
from telegram.ext import ContextTypes

# Локальные импорты
from ..database import get_db, RSSFeed
from ..scheduler import process_single_feed # Импортируем функцию обработки одной ленты
from .common import is_authorized
from ..localization import get_text # Импортируем get_text

logger = logging.getLogger(__name__)

async def force_check_feeds(update: Update, context: ContextTypes.DEFAULT_TYPE, feed_id: int | None = None):
    """
    Принудительно проверяет указанную ленту или все ленты.
    Запускается асинхронно.
    """
    user = update.effective_user
    if not is_authorized(update):
        # Не отправляем сообщение об ошибке, т.к. это может быть вызвано из callback'а
        logger.warning(f"Unauthorized attempt to call force_check_feeds by {user.id}")
        if update.callback_query: await update.callback_query.answer(get_text("no_access_inline", context), show_alert=True)
        elif update.message: await update.message.reply_text(get_text("no_access", context))
        return

    # Логи оставляем на английском
    log_prefix = f"Force check for {'feed ID ' + str(feed_id) if feed_id else 'all feeds'}"
    logger.info(f"{log_prefix} triggered by user {user.id}.")
    chat_id = update.effective_chat.id # ID чата, куда отправлять отчет
    checked_count = 0
    processed_feeds_info = [] # Можно использовать для более детального отчета

    try:
        with next(get_db()) as db:
            feeds_to_process: list[RSSFeed] = []
            if feed_id:
                # Вне зависимости от режима (public/private), проверяем конкретную ленту глобально
                # Администратор может захотеть проверить любую ленту
                feed = db.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
                if feed:
                    feeds_to_process.append(feed)
                else:
                    await context.bot.send_message(chat_id=chat_id, text=get_text("force_check_not_found", context, feed_id=feed_id))
                    return
            else:
                # Если ID не указан, проверяем все ленты
                feeds_to_process = db.query(RSSFeed).all()

            if not feeds_to_process:
                await context.bot.send_message(chat_id=chat_id, text=get_text("force_check_no_feeds", context))
                return

            # Отправляем предварительное сообщение
            # await context.bot.send_message(chat_id=chat_id, text=f"Начинаю проверку {len(feeds_to_process)} лент...")

            for feed_item in feeds_to_process:
                try:
                    # Вызываем функцию обработки одной ленты из модуля scheduler
                    await process_single_feed(context.bot, db, feed_item)
                    processed_feeds_info.append(f"ID {feed_item.id}")
                    checked_count += 1
                    # Можно добавить небольшую паузу, чтобы не перегружать API Telegram или RSS-серверы
                    # await asyncio.sleep(0.5)
                except Exception as e:
                    logger.error(f"Ошибка при принудительной обработке ленты ID {feed_item.id}: {e}", exc_info=True)
                    db.rollback() # Откатываем изменения для этой ленты
                    try:
                        error_text = get_text("force_check_error", context, error=f"Feed ID {feed_item.id}. Details in logs.") # TODO: Localize details part
                        await context.bot.send_message( # Исправлен отступ
                            text=error_text
                        )
                    except Exception as send_err: # Исправлен отступ
                        logger.error(f"Failed to send message about feed processing error {feed_item.id}: {send_err}")

        # Отправляем итоговый отчет
        result_message = get_text("force_check_completed", context) # TODO: Add count?
        # if processed_feeds_info:
        #     result_message += f"\nProcessed IDs: {', '.join(processed_feeds_info)}" # TODO: Localize
        await context.bot.send_message(chat_id=chat_id, text=result_message)

    except Exception as e: # Этот except должен быть на том же уровне, что и try
        logger.error(f"Critical error during force_check_feeds execution: {e}", exc_info=True)
        try:
            await context.bot.send_message(chat_id=chat_id, text=get_text("error_occurred", context)) # Общая ошибка
        except Exception as send_err:
            logger.error(f"Failed to send message about critical error in force_check_feeds: {send_err}")


async def forcecheck_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Обработчик команды /forcecheck [feed_id]"""
    if not is_authorized(update):
        await update.message.reply_text(get_text("no_access", context))
        return

    feed_id_to_check = None
    if context.args and context.args[0].isdigit():
        feed_id_to_check = int(context.args[0])

    start_message = get_text("force_check_starting_single", context, feed_id=feed_id_to_check) \
        if feed_id_to_check else get_text("force_check_starting", context)
    await update.message.reply_text(start_message)
    # Запускаем основную логику проверки в фоне
    asyncio.create_task(force_check_feeds(update, context, feed_id=feed_id_to_check))
