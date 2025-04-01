# rss_parser.py
import feedparser
import logging
from datetime import datetime
from time import mktime
from typing import List, Dict, Optional

logger = logging.getLogger(__name__)

def parse_feed(feed_url: str) -> Optional[List[Dict]]:
    """
    Парсит RSS-ленту и возвращает список словарей с данными постов.

    Args:
        feed_url: URL RSS-ленты.

    Returns:
        Список словарей, где каждый словарь представляет пост,
        или None в случае ошибки парсинга.
        Формат поста: {'title': str, 'link': str, 'published': datetime, 'guid': str, 'summary': str}
    """
    logger.info(f"Начинаю парсинг ленты: {feed_url}")
    try:
        # Устанавливаем user-agent, чтобы избежать блокировок на некоторых сайтах
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3'}
        feed_data = feedparser.parse(feed_url, agent=headers['User-Agent'])

        # Проверка на ошибки парсинга
        if feed_data.bozo:
            bozo_exception = feed_data.get('bozo_exception', 'Неизвестная ошибка')
            logger.error(f"Ошибка парсинга ленты {feed_url}: {bozo_exception}")
            # Можно добавить более детальную обработку разных типов ошибок bozo_exception
            # Например, isinstance(bozo_exception, feedparser.CharacterEncodingOverride)
            return None

        if feed_data.status != 200 and feed_data.status != 301 and feed_data.status != 302:
             logger.error(f"Ошибка при запросе ленты {feed_url}: HTTP статус {feed_data.status}")
             return None


        posts = []
        for entry in feed_data.entries:
            # Получаем дату публикации
            published_time = None
            if hasattr(entry, 'published_parsed') and entry.published_parsed:
                published_time = datetime.fromtimestamp(mktime(entry.published_parsed))
            elif hasattr(entry, 'updated_parsed') and entry.updated_parsed:
                published_time = datetime.fromtimestamp(mktime(entry.updated_parsed))
            else:
                # Если нет даты, используем текущее время (или можно пропустить пост)
                published_time = datetime.now()
                logger.warning(f"Не найдена дата публикации для поста '{entry.get('title', 'Без заголовка')}' в ленте {feed_url}. Используется текущее время.")

            # Получаем уникальный идентификатор поста (guid или link)
            guid = entry.get('guid', entry.get('link'))
            if not guid:
                logger.warning(f"Не найден GUID или link для поста '{entry.get('title', 'Без заголовка')}' в ленте {feed_url}. Пост будет пропущен.")
                continue

            post_data = {
                'title': entry.get('title', 'Без заголовка'),
                'link': entry.get('link', ''),
                'published': published_time,
                'guid': guid,
                'summary': entry.get('summary', entry.get('description', '')) # Иногда описание в description
            }
            posts.append(post_data)

        logger.info(f"Лента {feed_url} успешно распарсена, найдено {len(posts)} постов.")
        return posts

    except Exception as e:
        logger.error(f"Непредвиденная ошибка при парсинге ленты {feed_url}: {e}", exc_info=True)
        return None

if __name__ == '__main__':
    # Пример использования
    logging.basicConfig(level=logging.INFO)
    # test_feed_url = "https://www.python.org/blogs/rss/" # Пример RSS
    test_feed_url = "http://static.feed.rbc.ru/rbc/logical/footer/news.rss" # Другой пример
    parsed_posts = parse_feed(test_feed_url)
    if parsed_posts:
        print(f"Найдено постов: {len(parsed_posts)}")
        for post in parsed_posts[:2]: # Печатаем первые 2 для примера
            print("-" * 20)
            print(f"Заголовок: {post['title']}")
            print(f"Ссылка: {post['link']}")
            print(f"Дата: {post['published']}")
            print(f"GUID: {post['guid']}")
            # print(f"Описание: {post['summary'][:100]}...") # Печатаем начало описания
    else:
        print("Не удалось распарсить ленту.")
