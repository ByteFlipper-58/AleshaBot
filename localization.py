# localization.py
import json
import os
import logging
from typing import Dict, Any

from telegram.ext import ContextTypes

from .constants import USER_LANGUAGE, DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

translations: Dict[str, Dict[str, str]] = {}
locales_dir = os.path.join(os.path.dirname(__file__), 'locales')

def load_translations():
    """Загружает переводы из JSON файлов в директории locales."""
    global translations
    translations = {} # Очищаем перед загрузкой
    try:
        for lang_code in SUPPORTED_LANGUAGES:
            file_path = os.path.join(locales_dir, f"{lang_code}.json")
            if os.path.exists(file_path):
                with open(file_path, 'r', encoding='utf-8') as f:
                    translations[lang_code] = json.load(f)
                logger.info(f"Загружены переводы для языка: {lang_code}")
            else:
                logger.warning(f"Файл перевода не найден для языка: {lang_code} по пути {file_path}")
    except Exception as e:
        logger.error(f"Ошибка загрузки переводов: {e}", exc_info=True)
        # В случае ошибки оставляем translations пустым или частично загруженным

def get_user_language(context: ContextTypes.DEFAULT_TYPE | None) -> str:
    """Получает язык пользователя из контекста или возвращает язык по умолчанию."""
    if context and context.user_data:
        return context.user_data.get(USER_LANGUAGE, DEFAULT_LANGUAGE)
    return DEFAULT_LANGUAGE

def get_text(key: str, context: ContextTypes.DEFAULT_TYPE | None = None, lang_code: str | None = None, **kwargs: Any) -> str:
    """
    Возвращает переведенную строку по ключу для языка пользователя или указанного языка.
    Поддерживает форматирование строки с помощью kwargs.
    """
    if not translations:
        load_translations() # Попытка загрузить, если еще не загружено

    if lang_code:
        language = lang_code
    else:
        language = get_user_language(context)

    # Пытаемся получить перевод для нужного языка
    lang_translations = translations.get(language)
    if lang_translations:
        text = lang_translations.get(key)
        if text:
            try:
                return text.format(**kwargs) if kwargs else text
            except KeyError as e:
                logger.error(f"Ошибка форматирования для ключа '{key}' языка '{language}': отсутствует ключ {e} в kwargs={kwargs}")
                return f"[{key}_format_error]" # Возвращаем ошибку форматирования
        else:
            # Если ключ не найден в основном языке, пробуем язык по умолчанию
            if language != DEFAULT_LANGUAGE:
                default_translations = translations.get(DEFAULT_LANGUAGE)
                if default_translations:
                    text = default_translations.get(key)
                    if text:
                        logger.warning(f"Ключ '{key}' не найден для языка '{language}', используется язык по умолчанию '{DEFAULT_LANGUAGE}'.")
                        try:
                            return text.format(**kwargs) if kwargs else text
                        except KeyError as e:
                            logger.error(f"Ошибка форматирования (fallback) для ключа '{key}' языка '{DEFAULT_LANGUAGE}': отсутствует ключ {e} в kwargs={kwargs}")
                            return f"[{key}_format_error]"
            # Если ключ не найден и в языке по умолчанию
            logger.warning(f"Ключ перевода '{key}' не найден ни для языка '{language}', ни для языка по умолчанию '{DEFAULT_LANGUAGE}'.")
            return f"[{key}]" # Возвращаем сам ключ как индикатор отсутствия перевода
    else:
        # Если переводы для языка вообще не загружены
        logger.error(f"Переводы для языка '{language}' не загружены.")
        return f"[{key}_{language}_missing]"

# Загружаем переводы при импорте модуля
load_translations()
