# constants.py

# Состояния ConversationHandler
(MAIN_MENU, FEEDS_MENU, CHANNELS_MENU, SUBS_MENU, SETTINGS_MENU, SELECT_LANGUAGE,
 ADD_FEED_URL, ADD_FEED_DELAY, ADD_FEED_NAME,
 DELETE_FEED_CONFIRM, SET_DELAY_VALUE,
 # Заменяем состояния добавления канала
 ADD_CHANNEL_FORWARD, DELETE_CHANNEL_CONFIRM, # ADD_CHANNEL_ID, ADD_CHANNEL_NAME удалены
 SUBSCRIBE_SELECT_FEED, SUBSCRIBE_SELECT_CHANNEL, SUBSCRIBE_GET_HASHTAGS,
 UNSUBSCRIBE_SELECT_CHANNEL, UNSUBSCRIBE_SELECT_FEED,
 LIST_SUBS_SELECT_CHANNEL,
 EDIT_HASHTAGS_SELECT_CHANNEL, EDIT_HASHTAGS_SELECT_FEED, EDIT_HASHTAGS_GET_VALUE
 ) = range(22) # Уменьшено количество состояний

# Ключи для user_data / context.user_data
FEED_URL, FEED_DELAY, FEED_ID = "feed_url", "feed_delay", "feed_id"
# CHANNEL_CHAT_ID, CHANNEL_NAME больше не нужны в user_data для добавления канала
CHANNEL_ID_DB = "channel_id_db"
HASHTAGS, CURRENT_PAGE = "hashtags", "current_page"
USER_LANGUAGE = "user_language" # Ключ для хранения языка пользователя

# Настройки
PAGE_SIZE = 5 # Количество элементов на странице пагинации
DEFAULT_LANGUAGE = "en" # Язык по умолчанию
SUPPORTED_LANGUAGES = ["en", "ru"] # Поддерживаемые языки
