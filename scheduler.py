# scheduler.py
import logging
from datetime import datetime, timedelta, timezone
import asyncio
import html

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.orm import Session
from telegram import Bot
from telegram.error import TelegramError, BadRequest
from telegram.constants import ParseMode # Правильный импорт ParseMode

# Локальные импорты
from database import (
    get_db, RSSFeed, Channel, ChannelFeedLink, ScheduledPost, # Модели
    get_subscriptions_for_feed,
    add_published_post, is_post_published,
    add_scheduled_post, get_pending_scheduled_posts, update_scheduled_post_status,
    update_feed_last_checked
)
from rss_parser import parse_feed # Убрали FeedEntry
# from config import BOT_MODE # BOT_MODE здесь не используется

logger = logging.getLogger(__name__)

# --- Форматирование и отправка ---

def format_scheduled_message(scheduled_post: ScheduledPost) -> str:
    """Форматирует отложенный пост для отправки в Telegram."""
    title = html.escape(scheduled_post.post_title or 'Без заголовка')
    link = scheduled_post.post_link or ''
    summary_html = scheduled_post.post_summary or ''
    hashtags = scheduled_post.hashtags or ''

    message = f"<b>{title}</b>\n\n"
    if summary_html:
        message += f"{summary_html}\n\n"
    if link:
        message += f'\n<a href="{link}">Источник</a>'
    if hashtags:
        message += f"\n\n{html.escape(hashtags)}"

    MAX_MESSAGE_LENGTH = 4096
    if len(message) > MAX_MESSAGE_LENGTH:
         message = message[:MAX_MESSAGE_LENGTH - 4] + "..."

    return message

# --- Задачи планировщика ---

async def process_single_feed(bot: Bot, db: Session, feed: RSSFeed):
    """
    Обрабатывает одну RSS-ленту: парсит, находит новые посты и добавляет их в очередь ScheduledPost.
    """
    logger.info(f"Начинаю проверку ленты ID {feed.id}: {feed.url}")
    parsed_posts = parse_feed(feed.url)

    if parsed_posts is None:
        logger.warning(f"Не удалось получить посты для ленты ID {feed.id}: {feed.url}")
        return
    if not parsed_posts:
        logger.info(f"Постов не найдено в ленте ID {feed.id}: {feed.url}")
        return

    subscriptions = get_subscriptions_for_feed(db, feed.id)
    if not subscriptions:
        logger.info(f"Нет подписок для ленты ID {feed.id}.")
        posts_marked = 0
        for post_data in parsed_posts:
            guid = post_data.get('guid')
            if guid and not is_post_published(db, feed.id, guid):
                if add_published_post(db, feed.id, guid):
                    posts_marked += 1
        if posts_marked > 0:
            try:
                db.commit()
                logger.info(f"Отмечено {posts_marked} новых постов как обработанные для ленты {feed.id} (нет подписок).")
            except Exception as e:
                logger.error(f"Ошибка commit при отметке постов для ленты {feed.id} (нет подписок): {e}")
                db.rollback()
        return

    logger.info(f"Лента ID {feed.id} ({feed.url}): Найдено {len(parsed_posts)} постов. Подписок: {len(subscriptions)}.")

    new_posts_scheduled = 0
    now = datetime.now(timezone.utc)

    for post_data in reversed(parsed_posts):
        guid = post_data.get('guid')
        if not guid:
            logger.warning(f"Пост в ленте {feed.id} без GUID, пропущен: {post_data.get('title')}")
            continue

        if not is_post_published(db, feed.id, guid):
            logger.info(f"Найден новый необработанный пост в ленте {feed.id}: GUID={guid}, Title={post_data.get('title')}")
            add_published_post(db, feed.id, guid)
            scheduled_time = now + timedelta(minutes=feed.publish_delay_minutes)

            for sub in subscriptions:
                added = add_scheduled_post(
                    db_session=db,
                    feed_id=feed.id,
                    channel_id=sub.channel_id,
                    post_guid=guid,
                    scheduled_time=scheduled_time,
                    post_data=post_data,
                    hashtags=sub.hashtags,
                    user_id=sub.user_id
                )
                if added:
                    new_posts_scheduled += 1
            try:
                db.commit()
            except Exception as e:
                logger.error(f"Ошибка commit при добавлении поста {guid} (feed_id={feed.id}) в очередь: {e}")
                db.rollback()

    if new_posts_scheduled > 0:
        logger.info(f"Добавлено {new_posts_scheduled} постов в очередь для ленты {feed.id}.")
    else:
        logger.info(f"Новых необработанных постов не найдено для ленты {feed.id}.")


async def check_all_feeds_job(context):
    """Задача: проверка всех RSS лент и добавление новых постов в очередь."""
    bot: Bot = context.bot
    logger.info("Запуск задачи проверки RSS лент...")
    start_time = datetime.now()
    checked_count = 0

    with next(get_db()) as db:
        all_feeds_in_db = db.query(RSSFeed).all()
        if not all_feeds_in_db:
            logger.info("Нет RSS лент в базе данных для проверки.")
            return

        logger.info(f"Найдено {len(all_feeds_in_db)} лент в БД для потенциальной проверки.")
        now = datetime.now(timezone.utc)

        for feed in all_feeds_in_db:
            last_checked_aware = feed.last_checked.replace(tzinfo=timezone.utc) if feed.last_checked and feed.last_checked.tzinfo is None else feed.last_checked
            should_check = not last_checked_aware or now >= (last_checked_aware + timedelta(minutes=feed.update_interval_minutes))

            if should_check:
                logger.info(f"Время проверки для ленты ID {feed.id} ({feed.url}).")
                try:
                    await process_single_feed(bot, db, feed)
                    update_feed_last_checked(db, feed.id) # Эта функция сама коммитит
                    checked_count += 1
                except Exception as e:
                    logger.error(f"Ошибка при полной обработке ленты ID {feed.id}: {e}", exc_info=True)
                    db.rollback()
            # else:
            #      logger.debug(f"Пропуск проверки ленты ID {feed.id}. Следующая проверка не раньше {next_check_time.strftime('%Y-%m-%d %H:%M:%S %Z')}")

    duration = datetime.now() - start_time
    logger.info(f"Задача проверки RSS лент завершена. Проверено {checked_count} лент. Длительность: {duration}.")


async def publish_scheduled_posts_job(context):
    """Задача: публикация отложенных постов."""
    bot: Bot = context.bot
    logger.info("Запуск задачи публикации отложенных постов...")
    published_count = 0
    failed_count = 0

    with next(get_db()) as db:
        posts_to_publish = get_pending_scheduled_posts(db)
        if not posts_to_publish:
            logger.info("Нет отложенных постов для публикации.")
            return
        logger.info(f"Найдено {len(posts_to_publish)} отложенных постов для публикации.")

        for scheduled_post in posts_to_publish:
            channel = db.query(Channel).filter(Channel.id == scheduled_post.channel_id).first()
            if not channel:
                logger.error(f"Не найден канал (внутр. ID {scheduled_post.channel_id}) для отложенного поста ID {scheduled_post.id}. Помечаем как failed.")
                update_scheduled_post_status(db, scheduled_post.id, "failed")
                failed_count += 1
                continue

            message_text = format_scheduled_message(scheduled_post)
            status = "published"
            try:
                await bot.send_message(chat_id=channel.chat_id, text=message_text, parse_mode=ParseMode.HTML, disable_web_page_preview=False)
                logger.info(f"Отложенный пост ID {scheduled_post.id} (GUID: {scheduled_post.post_guid}) успешно отправлен в канал {channel.chat_id}.")
                published_count += 1
            except BadRequest as e:
                 logger.error(f"Ошибка BadRequest при отправке отложенного поста ID {scheduled_post.id} в канал {channel.chat_id}: {e}")
                 status = "failed"
                 failed_count += 1
            except TelegramError as e:
                logger.error(f"Ошибка Telegram при отправке отложенного поста ID {scheduled_post.id} в канал {channel.chat_id}: {e}")
                status = "failed"
                failed_count += 1
            except Exception as e:
                logger.error(f"Непредвиденная ошибка при отправке отложенного поста ID {scheduled_post.id} в канал {channel.chat_id}: {e}", exc_info=True)
                status = "failed"
                failed_count += 1

            update_scheduled_post_status(db, scheduled_post.id, status)
            await asyncio.sleep(0.2) # Пауза

        try:
            db.commit() # Коммитим все изменения статусов
        except Exception as e:
            logger.error(f"Ошибка commit при обновлении статусов отложенных постов: {e}")
            db.rollback()

    logger.info(f"Задача публикации отложенных постов завершена. Опубликовано: {published_count}, Ошибок: {failed_count}.")


# --- Управление планировщиком ---

scheduler = AsyncIOScheduler(timezone="UTC")

def start_scheduler(application):
    """Инициализирует и запускает планировщик с двумя задачами."""
    if not scheduler.running:
        scheduler.add_job(
            check_all_feeds_job,
            trigger=IntervalTrigger(minutes=5),
            id="check_all_feeds_job",
            name="Проверка RSS лент",
            replace_existing=True,
            args=[application]
        )
        scheduler.add_job(
            publish_scheduled_posts_job,
            trigger=IntervalTrigger(minutes=1),
            id="publish_scheduled_posts_job",
            name="Публикация отложенных постов",
            replace_existing=True,
            args=[application]
        )

        scheduler.start()
        logger.info("Планировщик запущен. Добавлены задачи: проверка лент (5 мин), публикация отложенных (1 мин).")
    else:
        logger.warning("Планировщик уже запущен.")
    return scheduler

def stop_scheduler():
    """Останавливает планировщик."""
    if scheduler.running:
        scheduler.shutdown()
        logger.info("Планировщик остановлен.")

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    logger.info("Тестовый запуск обработки лент...")
    print("Для запуска планировщика используйте main.py")
