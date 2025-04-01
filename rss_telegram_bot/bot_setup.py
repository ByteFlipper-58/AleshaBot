# bot_setup.py
import logging
import os

from telegram import BotCommand
from telegram.ext import (
    Application, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler,
    filters, ConversationHandler
)

# Локальные импорты
from .constants import * # Импортируем все константы
# Импортируем обработчики по категориям
from .handlers import common # Общие команды (start, cancel)
from .handlers import navigation # Обработчики навигации по меню
from .handlers import feeds, channels, subscriptions, force_check, pagination # Обработчики конкретных действий

logger = logging.getLogger(__name__)

TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN")

async def post_init(application: Application):
    """Выполняется после инициализации приложения для установки команд бота."""
    await application.bot.set_my_commands([
        BotCommand("start", "Показать главное меню"),
        BotCommand("forcecheck", "Принудительно проверить ленты (/forcecheck [id])"),
        BotCommand("cancel", "Отменить текущее действие"),
    ])
    logger.info("Команды бота установлены.")

def setup_application() -> Application | None:
    """Создает и настраивает объект Application."""
    if TELEGRAM_BOT_TOKEN == "YOUR_BOT_TOKEN":
        logger.error("Токен Telegram бота не установлен в переменных окружения (TELEGRAM_BOT_TOKEN).")
        return None

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(post_init).build()

    # --- Определяем ConversationHandlers для каждой фичи ---

    # 1. Добавление ленты
    add_feed_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(feeds.add_feed_start, pattern="^add_feed_start$")],
        states={
            ADD_FEED_URL: [MessageHandler(filters.TEXT & ~filters.COMMAND, feeds.add_feed_get_url)],
            ADD_FEED_DELAY: [MessageHandler(filters.TEXT & ~filters.COMMAND, feeds.add_feed_get_delay)],
            ADD_FEED_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, feeds.add_feed_get_name)],
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"), # Общая отмена
            CallbackQueryHandler(navigation.feeds_menu_back, pattern="^feeds_menu_back$") # Возврат в меню лент из navigation
        ],
        map_to_parent={
            # Возвращаемся в состояние FEEDS_MENU основного хендлера
            ConversationHandler.END: FEEDS_MENU,
            FEEDS_MENU: FEEDS_MENU # Явно указываем возврат в то же меню
        },
        name="add_feed_conversation",
        persistent=False # Не сохраняем состояние между перезапусками
    )

    # 2. Управление лентой (удаление, задержка)
    feed_manage_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(feeds.feed_action_handler, pattern="^(delete_feed_confirm_|set_delay_start_)")],
        states={
            DELETE_FEED_CONFIRM: [CallbackQueryHandler(feeds.delete_feed_confirm_handler, pattern="^(delete_feed_do_|list_feeds_refresh$)")],
            SET_DELAY_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, feeds.set_delay_value_handler)],
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.feeds_menu_back, pattern="^feeds_menu_back$"), # из navigation
            CallbackQueryHandler(feeds.list_feeds_button, pattern="^list_feeds_refresh$") # Обновление списка как fallback
        ],
        map_to_parent={
            ConversationHandler.END: FEEDS_MENU, # Возврат в меню лент после завершения
            FEEDS_MENU: FEEDS_MENU # Возврат в меню лент из fallback'ов
        },
        name="manage_feed_conversation",
        persistent=False
    )

    # 3. Добавление канала (через пересылку)
    add_channel_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(channels.add_channel_start, pattern="^add_channel_start$")],
        states={
            # Ожидаем пересланное сообщение
            ADD_CHANNEL_FORWARD: [MessageHandler(filters.FORWARDED & (~filters.COMMAND), channels.add_channel_handle_forward)],
            # Можно добавить обработчик для обычных текстовых сообщений в этом состоянии,
            # чтобы подсказать пользователю, что нужно именно переслать сообщение.
            # ADD_CHANNEL_FORWARD: [MessageHandler(filters.TEXT & (~filters.COMMAND), channels.add_channel_wrong_input)],
        },
        fallbacks=[
            # Добавляем обработку кнопки Отмена из сообщения add_channel_start
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.channels_menu_back, pattern="^channels_menu_back$") # из navigation
        ],
        map_to_parent={
            ConversationHandler.END: CHANNELS_MENU,
            CHANNELS_MENU: CHANNELS_MENU
        },
        name="add_channel_conversation",
        persistent=False
    )

    # 4. Управление каналом (удаление)
    channel_manage_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(channels.channel_action_handler, pattern="^delete_channel_confirm_")],
        states={
            DELETE_CHANNEL_CONFIRM: [CallbackQueryHandler(channels.delete_channel_confirm_handler, pattern="^(delete_channel_do_|list_channels_refresh$)")],
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.channels_menu_back, pattern="^channels_menu_back$"), # из navigation
            CallbackQueryHandler(channels.list_channels_button, pattern="^list_channels_refresh$")
        ],
        map_to_parent={
            ConversationHandler.END: CHANNELS_MENU,
            CHANNELS_MENU: CHANNELS_MENU
        },
        name="manage_channel_conversation",
        persistent=False
    )

    # 5. Подписка канала на ленту
    subscribe_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(subscriptions.subscribe_start, pattern="^subscribe_start$")],
        states={
            SUBSCRIBE_SELECT_FEED: [
                CallbackQueryHandler(subscriptions.subscribe_select_feed, pattern="^sub_feed_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_sub_feed_") # Пагинация лент
            ],
            SUBSCRIBE_SELECT_CHANNEL: [
                CallbackQueryHandler(subscriptions.subscribe_select_channel, pattern="^sub_chan_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_sub_chan_") # Пагинация каналов
            ],
            SUBSCRIBE_GET_HASHTAGS: [MessageHandler(filters.TEXT & ~filters.COMMAND, subscriptions.subscribe_get_hashtags)]
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.subs_menu_back, pattern="^subs_menu_back$"), # Назад в меню подписок из navigation
            CallbackQueryHandler(subscriptions.subscribe_start, pattern="^subscribe_start$") # Возврат к началу подписки
        ],
        map_to_parent={
            ConversationHandler.END: SUBS_MENU, # Возврат в меню подписок после завершения
            SUBS_MENU: SUBS_MENU # Возврат из fallback'ов
        },
        name="subscribe_conversation",
        persistent=False
    )

    # 6. Отписка канала от ленты
    unsubscribe_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(subscriptions.unsubscribe_start, pattern="^unsubscribe_start$")],
        states={
            UNSUBSCRIBE_SELECT_CHANNEL: [
                CallbackQueryHandler(subscriptions.unsubscribe_select_channel, pattern="^unsub_chan_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_unsub_chan_") # Пагинация каналов
            ],
            UNSUBSCRIBE_SELECT_FEED: [
                CallbackQueryHandler(subscriptions.unsubscribe_select_feed, pattern="^unsub_feed_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_unsub_feed_") # Пагинация подписок
            ]
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.subs_menu_back, pattern="^subs_menu_back$"), # из navigation
            CallbackQueryHandler(subscriptions.unsubscribe_start, pattern="^unsubscribe_start$") # Возврат к началу отписки
        ],
        map_to_parent={
             ConversationHandler.END: SUBS_MENU, # Возврат в меню подписок
             SUBS_MENU: SUBS_MENU
        },
        name="unsubscribe_conversation",
        persistent=False
    )

    # 7. Просмотр подписок канала
    list_subs_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(subscriptions.list_subs_start, pattern="^list_subs_start$")],
        states={
            LIST_SUBS_SELECT_CHANNEL: [
                CallbackQueryHandler(subscriptions.list_subs_select_channel, pattern="^listsub_chan_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_listsub_chan_") # Пагинация каналов
            ]
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.subs_menu_back, pattern="^subs_menu_back$"), # Назад в меню подписок из navigation
            CallbackQueryHandler(subscriptions.list_subs_start, pattern="^list_subs_start$") # Возврат к началу просмотра
        ],
         map_to_parent={
             ConversationHandler.END: SUBS_MENU, # Возврат в меню подписок
             SUBS_MENU: SUBS_MENU
        },
        name="list_subs_conversation",
        persistent=False
    )

    # 8. Редактирование хештегов подписки
    edit_hashtags_conv = ConversationHandler(
        entry_points=[CallbackQueryHandler(subscriptions.edit_hashtags_start, pattern="^edit_hashtags_start$")],
        states={
            EDIT_HASHTAGS_SELECT_CHANNEL: [
                CallbackQueryHandler(subscriptions.edit_hashtags_select_channel, pattern="^editht_chan_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_editht_chan_") # Пагинация каналов
            ],
            EDIT_HASHTAGS_SELECT_FEED: [
                CallbackQueryHandler(subscriptions.edit_hashtags_select_feed, pattern="^editht_feed_"),
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_editht_feed_") # Пагинация подписок
            ],
            EDIT_HASHTAGS_GET_VALUE: [MessageHandler(filters.TEXT & ~filters.COMMAND, subscriptions.edit_hashtags_get_value)],
        },
        fallbacks=[
            CommandHandler("cancel", common.cancel_conversation),
            CallbackQueryHandler(common.cancel_conversation, pattern="^cancel$"),
            CallbackQueryHandler(navigation.subs_menu_back, pattern="^subs_menu_back$"), # из navigation
            CallbackQueryHandler(subscriptions.edit_hashtags_start, pattern="^edit_hashtags_start$") # Возврат к началу редактирования
        ],
        map_to_parent={
             ConversationHandler.END: SUBS_MENU, # Возврат в меню подписок
             SUBS_MENU: SUBS_MENU
        },
        name="edit_hashtags_conversation",
        persistent=False
    )

    # --- Основной ConversationHandler для навигации по меню ---
    main_conv = ConversationHandler(
        entry_points=[CommandHandler("start", common.start)],
        states={
            MAIN_MENU: [
                # Обработчик кнопок главного меню из navigation
                CallbackQueryHandler(navigation.main_menu_handler, pattern="^(feeds_menu|channels_menu|subs_menu|force_check_all|settings_menu)$")
            ],
            FEEDS_MENU: [
                # Кнопки внутри меню лент
                CallbackQueryHandler(navigation.feeds_menu_handler, pattern="^main_menu$"), # Назад в главное меню из navigation
                CallbackQueryHandler(feeds.list_feeds_button, pattern="^list_feeds$"), # Показать список лент
                CallbackQueryHandler(navigation.feeds_menu_back, pattern="^feeds_menu_back$"), # Обработка кнопки "Назад" из списков (из navigation)
                # Пагинация для основного списка лент
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_feed_action_"), # Обработчик пагинации
                # Вложенные диалоги для лент
                add_feed_conv,
                feed_manage_conv
            ],
            CHANNELS_MENU: [
                # Кнопки внутри меню каналов
                CallbackQueryHandler(navigation.channels_menu_handler, pattern="^main_menu$"), # Назад из navigation
                CallbackQueryHandler(channels.list_channels_button, pattern="^list_channels$"), # Список каналов
                CallbackQueryHandler(navigation.channels_menu_back, pattern="^channels_menu_back$"), # Назад из списков (из navigation)
                 # Пагинация для основного списка каналов
                CallbackQueryHandler(pagination.handle_pagination, pattern="^page_channel_action_"), # Обработчик пагинации
                # Вложенные диалоги для каналов
                add_channel_conv,
                channel_manage_conv
            ],
            SUBS_MENU: [
                 # Кнопки внутри меню подписок
                CallbackQueryHandler(navigation.subs_menu_handler, pattern="^main_menu$"), # Назад из navigation
                CallbackQueryHandler(navigation.subs_menu_back, pattern="^subs_menu_back$"), # Обработка кнопки "Назад" из диалогов (из navigation)
                # Вложенные диалоги для подписок
                subscribe_conv,
                unsubscribe_conv,
                list_subs_conv,
                edit_hashtags_conv
            ],
            SETTINGS_MENU: [ # Новое состояние для меню настроек
                CallbackQueryHandler(navigation.settings_menu_handler, pattern="^(main_menu|select_language_menu)$") # из navigation
            ],
            SELECT_LANGUAGE: [ # Новое состояние для выбора языка
                CallbackQueryHandler(navigation.select_language_handler, pattern="^(set_language_ru|set_language_en|settings_menu)$") # из navigation
            ],
        },
        fallbacks=[
            CommandHandler("start", common.start), # Позволяет перезапустить диалог с /start
            CommandHandler("cancel", common.cancel_conversation) # Глобальная отмена
        ],
        name="main_menu_conversation",
        persistent=False # Не сохраняем состояние главного меню
    )

    # Добавляем основной обработчик диалогов
    application.add_handler(main_conv)

    # Добавляем отдельные команды, не входящие в основной диалог
    application.add_handler(CommandHandler("forcecheck", force_check.forcecheck_command))
    # Добавляем CommandHandler для cancel на верхнем уровне на всякий случай
    application.add_handler(CommandHandler("cancel", common.cancel_conversation))

    logger.info("Обработчики команд и диалогов настроены.")
    return application
