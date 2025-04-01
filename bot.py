# bot.py
# bot.py
import logging
import os
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

# Импортируем функцию настройки приложения из нового модуля (относительный импорт)
from .bot_setup import setup_application
# Импортируем настройки логирования и функцию инициализации БД (относительные импорты)
from .config import LOG_LEVEL
from .database import init_db

logger = logging.getLogger(__name__)

# Основная функция запуска бота остается здесь
if __name__ == '__main__':
    # Создаем консоль Rich
    console = Console()

    # Формируем ASCII Art баннер "AleshaBot"
    ascii_art = r"""
          _    _     _               _   ____        _   
         / \  | |__ | |__   ___  ___| |_( __ )  ___ | |_ 
        / _ \ | '_ \| '_ \ / _ \/ __| __|\ \ \ / _ \| __|
       / ___ \| | | | | | | (_) \__ \ |_  \ \ \ (_) | |_ 
      /_/   \_\_| |_|_| |_|\___/|___/\__| /_/ / \___/ \__|
    """
    # Используем r-string для избежания проблем с escape-последовательностями
    # Убираем лишние пробелы в начале строк ASCII арта
    cleaned_ascii_art = "\n".join(line.strip() for line in ascii_art.strip().split('\n'))
    banner_text = Text(cleaned_ascii_art, style="bold cyan") # Изменим цвет для разнообразия
    console.print(Panel(banner_text, title="[bold green]Starting AleshaBot[/]", border_style="blue", expand=False))

    # Настройка логирования
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=LOG_LEVEL,
        handlers=[logging.StreamHandler()] # Используем стандартный StreamHandler для совместимости
    )
    # Можно также использовать RichHandler для красивого логирования:
    # from rich.logging import RichHandler
    # logging.basicConfig(
    #     level=LOG_LEVEL, format="%(message)s", datefmt="[%X]", handlers=[RichHandler(console=console)]
    # )

    logger.info("Starting bot initialization...") # Логи теперь тоже могут быть цветными, если используется RichHandler

    # Инициализация базы данных (если это требуется при старте)
    try:
        logger.info("Initializing database...")
        init_db()
        logger.info("Database initialized.")
    except Exception as e:
        logger.error(f"Database initialization error: {e}", exc_info=True)
        # Решаем, стоит ли продолжать без БД или завершить работу
        # exit(1) # Раскомментировать, если БД критична для работы

    # Создание и настройка приложения Telegram
    application = setup_application()

    if application:
        logger.info("Starting bot polling...")
        # Запуск бота в режиме polling
        application.run_polling()
    else:
        logger.error("Failed to create bot application. Check token and settings.")
