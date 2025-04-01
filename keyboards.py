# keyboards.py
from typing import List, Any
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# Импортируем модели для type hints
# Подразумевается, что модели RSSFeed, Channel, ChannelFeedLink определены в database.py
try:
    from database import RSSFeed, Channel, ChannelFeedLink
except ImportError:
    # Заглушки, если модели не найдены (для статической проверки)
    class RSSFeed: pass
    class Channel: pass
    class ChannelFeedLink: pass

# --- Клавиатуры (теперь принимают переведенные тексты) ---

def build_main_menu_keyboard(
    feeds_text: str, channels_text: str, subs_text: str, check_text: str, settings_text: str
) -> InlineKeyboardMarkup:
    """Строит основное меню с переведенными кнопками."""
    keyboard = [
        [InlineKeyboardButton(feeds_text, callback_data="feeds_menu")],
        [InlineKeyboardButton(channels_text, callback_data="channels_menu")],
        [InlineKeyboardButton(subs_text, callback_data="subs_menu")],
        [InlineKeyboardButton(check_text, callback_data="force_check_all")],
        [InlineKeyboardButton(settings_text, callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_settings_menu_keyboard(select_lang_text: str, back_text: str) -> InlineKeyboardMarkup:
    """Строит меню настроек с переведенными кнопками."""
    keyboard = [
        [InlineKeyboardButton(select_lang_text, callback_data="select_language_menu")],
        [InlineKeyboardButton(back_text, callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_language_selection_keyboard(ru_text: str, en_text: str, back_text: str) -> InlineKeyboardMarkup:
    """Строит клавиатуру выбора языка с переведенными кнопками."""
    keyboard = [
        [InlineKeyboardButton(ru_text, callback_data="set_language_ru")],
        [InlineKeyboardButton(en_text, callback_data="set_language_en")],
        [InlineKeyboardButton(back_text, callback_data="settings_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_feeds_menu_keyboard(add_text: str, list_text: str, back_text: str) -> InlineKeyboardMarkup:
    """Строит меню управления лентами с переведенными кнопками."""
    keyboard = [
        [InlineKeyboardButton(add_text, callback_data="add_feed_start")],
        [InlineKeyboardButton(list_text, callback_data="list_feeds")],
        [InlineKeyboardButton(back_text, callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_channels_menu_keyboard(add_text: str, list_text: str, back_text: str) -> InlineKeyboardMarkup:
    """Строит меню управления каналами с переведенными кнопками."""
    keyboard = [
        [InlineKeyboardButton(add_text, callback_data="add_channel_start")],
        [InlineKeyboardButton(list_text, callback_data="list_channels")],
        [InlineKeyboardButton(back_text, callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_subs_menu_keyboard(
    subscribe_text: str, unsubscribe_text: str, edit_hashtags_text: str, list_subs_text: str, back_text: str
) -> InlineKeyboardMarkup:
    """Строит меню управления подписками с переведенными кнопками."""
    keyboard = [
        [InlineKeyboardButton(subscribe_text, callback_data="subscribe_start")],
        [InlineKeyboardButton(unsubscribe_text, callback_data="unsubscribe_start")],
        [InlineKeyboardButton(edit_hashtags_text, callback_data="edit_hashtags_start")],
        [InlineKeyboardButton(list_subs_text, callback_data="list_subs_start")],
        [InlineKeyboardButton(back_text, callback_data="main_menu")]
    ]
    return InlineKeyboardMarkup(keyboard)

def build_back_button(back_text: str, callback_data="main_menu") -> List[InlineKeyboardButton]:
    """Создает кнопку 'Назад' с переведенным текстом."""
    return [InlineKeyboardButton(back_text, callback_data=callback_data)]

def build_paginated_list_keyboard(
    items: List[Any],
    prefix: str,
    page: int,
    page_size: int,
    back_callback: str,
    # Переведенные тексты
    back_text: str,
    prev_text: str,
    next_text: str,
    # Форматтеры для элементов и действий (полученные из get_text)
    item_name_format: str,
    item_name_with_title_format: str,
    channel_item_name_format: str,
    feed_action_delay_format: str,
    feed_action_delete_text: str,
    channel_action_delete_text: str
) -> InlineKeyboardMarkup:
    """Строит клавиатуру для списка с пагинацией и кнопками действий, используя переводы."""
    keyboard_layout = []
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_items = items[start_index:end_index]

    for item in paginated_items:
        item_id = getattr(item, 'id', 'N/A')
        item_name_raw = getattr(item, 'name', None) or getattr(item, 'title', None)

        # Формируем отображаемое имя с использованием переведенных форматов
        if isinstance(item, Channel):
            item_chat_id = getattr(item, 'chat_id', 'N/A')
            if item_name_raw:
                display_name = item_name_with_title_format.format(item_name=item_name_raw, item_chat_id=item_chat_id)
            else:
                display_name = channel_item_name_format.format(item_chat_id=item_chat_id)
        elif isinstance(item, RSSFeed):
            if item_name_raw:
                 display_name = item_name_with_title_format.format(item_name=item_name_raw, item_id=item_id)
            else:
                 display_name = item_name_format.format(item_id=item_id)
        else: # Общий случай
             display_name = item_name_raw or f"ID: {item_id}"

        # Кнопка с именем элемента (пока без callback_data для item_info, т.к. он не используется)
        keyboard_layout.append([InlineKeyboardButton(display_name, callback_data=f"noop_{prefix}{item_id}")])

        action_buttons = []
        if isinstance(item, RSSFeed):
            delay_text = feed_action_delay_format.format(delay=item.publish_delay_minutes)
            action_buttons.append(InlineKeyboardButton(delay_text, callback_data=f"set_delay_start_{item.id}"))
            action_buttons.append(InlineKeyboardButton(feed_action_delete_text, callback_data=f"delete_feed_confirm_{item.id}"))
        elif isinstance(item, Channel):
            action_buttons.append(InlineKeyboardButton(channel_action_delete_text, callback_data=f"delete_channel_confirm_{item.id}"))
        # Добавить другие типы при необходимости

        if action_buttons:
            keyboard_layout.append(action_buttons) # Добавляем кнопки действий отдельной строкой

    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(prev_text, callback_data=f"page_{prefix}{page-1}"))
    if end_index < len(items):
        pagination_row.append(InlineKeyboardButton(next_text, callback_data=f"page_{prefix}{page+1}"))

    if pagination_row:
        keyboard_layout.append(pagination_row)

    keyboard_layout.append(build_back_button(back_text, back_callback)) # Используем переведенный текст
    return InlineKeyboardMarkup(keyboard_layout)


def build_selection_keyboard(
    items: List[Any],
    data_prefix: str,
    name_attr: str,
    id_attr: str,
    back_callback: str,
    # Переведенные тексты
    back_text: str,
    prev_text: str,
    next_text: str,
    # Форматтеры
    channel_item_name_format: str,
    feed_item_name_format: str,
    feed_subscription_item_format: str,
    feed_subscription_no_hashtags_text: str,
    page: int = 1,
    page_size: int = 5
) -> InlineKeyboardMarkup:
    """Строит клавиатуру для выбора элемента из списка с пагинацией, используя переводы."""
    keyboard = []
    start_index = (page - 1) * page_size
    end_index = start_index + page_size
    paginated_items = items[start_index:end_index]

    for item in paginated_items:
        item_id = getattr(item, id_attr, 'N/A')
        item_name_obj = getattr(item, name_attr, None)
        item_name = getattr(item_name_obj, 'name', None) if isinstance(item_name_obj, (RSSFeed, Channel)) else item_name_obj

        display_name = ""
        callback_item_id = item_id # ID для callback_data

        # Формируем отображаемое имя с использованием переведенных форматов
        if isinstance(item, Channel):
            item_chat_id = getattr(item, 'chat_id', 'N/A')
            display_name = item_name or channel_item_name_format.format(item_chat_id=item_chat_id)
        elif isinstance(item, RSSFeed):
            display_name = item_name or feed_item_name_format.format(item_id=item_id)
        elif isinstance(item, ChannelFeedLink):
            feed_name = item.feed.name or feed_item_name_format.format(item_id=item.feed.id)
            hashtags_display = item.hashtags or feed_subscription_no_hashtags_text
            display_name = feed_subscription_item_format.format(feed_name=feed_name, hashtags=hashtags_display)
            callback_item_id = item.feed_id # Используем feed_id для callback_data
        else:
            display_name = item_name or f"ID: {item_id}"

        keyboard.append([InlineKeyboardButton(display_name, callback_data=f"{data_prefix}{callback_item_id}")])

    pagination_row = []
    if page > 1:
        pagination_row.append(InlineKeyboardButton(prev_text, callback_data=f"page_{data_prefix}{page-1}"))
    if end_index < len(items):
        pagination_row.append(InlineKeyboardButton(next_text, callback_data=f"page_{data_prefix}{page+1}"))

    if pagination_row:
        keyboard.append(pagination_row)

    keyboard.append(build_back_button(back_text, back_callback))
    return InlineKeyboardMarkup(keyboard)

# Функция build_item_selection_keyboard больше не нужна, так как build_selection_keyboard теперь универсальна
# def build_item_selection_keyboard(...) -> InlineKeyboardMarkup:
#     """Строит клавиатуру для выбора элемента из списка с пагинацией (аналог build_selection_keyboard)."""
#     return build_selection_keyboard(...)
