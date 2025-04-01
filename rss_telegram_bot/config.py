# config.py
import os
import logging
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
# Это нужно делать здесь, чтобы переменные были доступны при импорте config
load_dotenv()

logger = logging.getLogger(__name__)

# --- Режим работы бота ---
# 'private' - только админы могут использовать, данные общие
# 'public' - любой может использовать, данные разделены по пользователям
BOT_MODE = os.environ.get("BOT_MODE", "private").lower()
if BOT_MODE not in ["private", "public"]:
    logger.warning(f"Некорректный BOT_MODE '{BOT_MODE}'. Используется 'private'.")
    BOT_MODE = "private"

# --- Администраторы бота (для приватного режима) ---
# ID пользователей Telegram через запятую
ADMIN_USER_IDS_STR = os.environ.get("ADMIN_USER_IDS", "")
ADMIN_USER_IDS = set()
if ADMIN_USER_IDS_STR:
    try:
        ADMIN_USER_IDS = {int(admin_id.strip()) for admin_id in ADMIN_USER_IDS_STR.split(',')}
        logger.info(f"Загружены ID администраторов: {ADMIN_USER_IDS}")
    except ValueError:
        logger.error("Ошибка парсинга ADMIN_USER_IDS. Убедитесь, что это числа через запятую.")
        ADMIN_USER_IDS = set()

if BOT_MODE == "private" and not ADMIN_USER_IDS:
     logger.warning("Бот в приватном режиме, но не указан ни один ADMIN_USER_IDS. Никто не сможет использовать бота.")


# --- Прочие настройки ---
LOG_LEVEL = os.environ.get("LOG_LEVEL", "INFO").upper()
DEFAULT_FEED_UPDATE_INTERVAL_MINUTES = 60

# Проверка корректности LOG_LEVEL
if LOG_LEVEL not in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
    logger.warning(f"Некорректный LOG_LEVEL '{LOG_LEVEL}'. Используется INFO.")
    LOG_LEVEL = "INFO"

# Путь к БД определяется в database.py
# Токен бота определяется в bot.py
