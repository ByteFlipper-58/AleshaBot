# database.py
import logging
from sqlalchemy import create_engine, Column, Integer, String, DateTime, Boolean, ForeignKey, UniqueConstraint, Text, BigInteger
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from sqlalchemy.sql import func
import os
from datetime import datetime, timezone
from typing import List, Optional

# Импортируем настройки режима работы
from config import BOT_MODE
# Импортируем константы для языка по умолчанию
from constants import DEFAULT_LANGUAGE, SUPPORTED_LANGUAGES

logger = logging.getLogger(__name__)

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///rss_bot.db")

Base = declarative_base()
# Создаем engine на основе DATABASE_URL. SQLAlchemy сам определит диалект.
# Убираем connect_args={"check_same_thread": False}, т.к. он специфичен для SQLite.
engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# --- Модели ---

class User(Base):
    """Модель пользователя (для связи данных в public режиме)."""
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, index=True, autoincrement=False) # Telegram User ID
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    last_name = Column(String, nullable=True)
    language_code = Column(String(2), nullable=True) # Добавлено поле для кода языка (e.g., 'en', 'ru')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    # Связи (если BOT_MODE == 'public')
    feeds = relationship("RSSFeed", back_populates="owner", cascade="all, delete-orphan")
    channels = relationship("Channel", back_populates="owner", cascade="all, delete-orphan")
    subscriptions = relationship("ChannelFeedLink", back_populates="owner", cascade="all, delete-orphan")


class RSSFeed(Base):
    __tablename__ = "rss_feeds"
    id = Column(Integer, primary_key=True, index=True)
    # Добавляем user_id, nullable=True (в private режиме будет NULL)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    url = Column(String, index=True, nullable=False) # URL больше не уникален глобально
    name = Column(String, nullable=True)
    last_checked = Column(DateTime(timezone=True), server_default=func.now())
    update_interval_minutes = Column(Integer, default=60, nullable=False)
    publish_delay_minutes = Column(Integer, default=0, nullable=False)

    owner = relationship("User", back_populates="feeds")
    channels = relationship("ChannelFeedLink", back_populates="feed", cascade="all, delete-orphan")
    posts = relationship("PublishedPost", back_populates="feed", cascade="all, delete-orphan")
    scheduled_posts = relationship("ScheduledPost", back_populates="feed", cascade="all, delete-orphan")

    # Уникальность URL для каждого пользователя в public режиме
    __table_args__ = (UniqueConstraint('user_id', 'url', name='_user_feed_url_uc'),)


class Channel(Base):
    __tablename__ = "channels"
    id = Column(Integer, primary_key=True, index=True) # Внутренний ID
    # Добавляем user_id
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    chat_id = Column(String, index=True, nullable=False) # Telegram chat_id (не уникален глобально)
    name = Column(String, nullable=True)

    owner = relationship("User", back_populates="channels")
    feeds = relationship("ChannelFeedLink", back_populates="channel", cascade="all, delete-orphan")
    scheduled_posts = relationship("ScheduledPost", back_populates="channel", cascade="all, delete-orphan")

    # Уникальность chat_id для каждого пользователя в public режиме
    __table_args__ = (UniqueConstraint('user_id', 'chat_id', name='_user_channel_chat_id_uc'),)


class ChannelFeedLink(Base):
    __tablename__ = "channel_feed_links"
    # Добавляем user_id
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), primary_key=True)
    feed_id = Column(Integer, ForeignKey("rss_feeds.id", ondelete="CASCADE"), primary_key=True)
    hashtags = Column(String, nullable=True)

    owner = relationship("User", back_populates="subscriptions")
    channel = relationship("Channel", back_populates="feeds")
    feed = relationship("RSSFeed", back_populates="channels")


class PublishedPost(Base):
    """Хранит GUIDы постов, которые уже были обработаны для конкретной ленты,
       чтобы не добавлять их в очередь повторно. НЕ зависит от пользователя."""
    __tablename__ = "published_posts"
    id = Column(Integer, primary_key=True, index=True)
    feed_id = Column(Integer, ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False)
    post_guid = Column(String(512), index=True, nullable=False)
    published_at = Column(DateTime(timezone=True), server_default=func.now())

    feed = relationship("RSSFeed", back_populates="posts")
    __table_args__ = (UniqueConstraint('feed_id', 'post_guid', name='_feed_post_uc'),)


class ScheduledPost(Base):
    """Посты, ожидающие публикации. Зависят от пользователя в public режиме."""
    __tablename__ = "scheduled_posts"
    id = Column(Integer, primary_key=True, index=True)
    # Добавляем user_id
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    feed_id = Column(Integer, ForeignKey("rss_feeds.id", ondelete="CASCADE"), nullable=False)
    channel_id = Column(Integer, ForeignKey("channels.id", ondelete="CASCADE"), nullable=False)
    post_guid = Column(String(512), nullable=False)
    scheduled_time = Column(DateTime(timezone=True), nullable=False, index=True)
    status = Column(String, default="pending", nullable=False, index=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    post_title = Column(String)
    post_link = Column(String)
    post_summary = Column(Text)
    hashtags = Column(String, nullable=True)

    # Связи не обязательны, но могут быть полезны
    # owner = relationship("User") # Связь с User не нужна напрямую
    feed = relationship("RSSFeed", back_populates="scheduled_posts")
    channel = relationship("Channel", back_populates="scheduled_posts")

    # Уникальность поста для канала и пользователя
    __table_args__ = (UniqueConstraint('user_id', 'feed_id', 'channel_id', 'post_guid', name='_user_feed_channel_post_uc'),)


def init_db():
    """Инициализирует базу данных, создавая все таблицы."""
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Таблицы базы данных успешно созданы/проверены.")
    except Exception as e:
        logger.error(f"Ошибка при инициализации базы данных: {e}")
        raise

def get_db():
    """Генератор сессии базы данных."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- Функции для работы с пользователями ---

def get_or_create_user(db_session, user_id: int, username: str = None, first_name: str = None, last_name: str = None) -> User:
    """Получает или создает пользователя в БД."""
    user = db_session.query(User).filter(User.id == user_id).first()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name, last_name=last_name)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
        logger.info(f"Создан новый пользователь: ID={user_id}, Username={username}")
    # Обновляем язык, если он изменился или не был установлен
    if not user.language_code:
        user.language_code = DEFAULT_LANGUAGE # Устанавливаем язык по умолчанию при создании
        db_session.commit()
        db_session.refresh(user)
    return user

def update_user_language(db_session, user_id: int, language_code: str):
    """Обновляет язык пользователя в БД."""
    user = db_session.query(User).filter(User.id == user_id).first()
    if user:
        if language_code in SUPPORTED_LANGUAGES:
            user.language_code = language_code
            db_session.commit()
            logger.info(f"Язык пользователя {user_id} обновлен на {language_code}.")
            return True
        else:
            logger.warning(f"Попытка установить неподдерживаемый язык '{language_code}' для пользователя {user_id}.")
            return False
    else:
        logger.warning(f"Пользователь {user_id} не найден для обновления языка.")
        return False

# --- Обновленные функции для работы с БД с учетом user_id ---

def add_channel(db_session, chat_id: str, name: str = None, user_id: Optional[int] = None):
    """Добавляет новый канал, привязывая к пользователю в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(Channel).filter(Channel.chat_id == chat_id)
    if owner_id: query = query.filter(Channel.user_id == owner_id)
    existing_channel = query.first()

    if existing_channel:
        logger.warning(f"Канал {chat_id} уже существует для пользователя {owner_id or 'N/A'}.")
        return existing_channel

    new_channel = Channel(chat_id=str(chat_id), name=name, user_id=owner_id)
    db_session.add(new_channel)
    db_session.commit()
    db_session.refresh(new_channel)
    logger.info(f"Канал {chat_id} успешно добавлен для пользователя {owner_id or 'N/A'}.")
    return new_channel

def get_channel(db_session, chat_id: str = None, channel_db_id: int = None, user_id: Optional[int] = None):
    """Получает канал по chat_id или внутреннему ID, фильтруя по user_id в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(Channel)
    if owner_id: query = query.filter(Channel.user_id == owner_id)

    if channel_db_id:
        return query.filter(Channel.id == channel_db_id).first()
    if chat_id:
        return query.filter(Channel.chat_id == str(chat_id)).first()
    return None

def get_all_channels(db_session, user_id: Optional[int] = None):
    """Получает все каналы, фильтруя по user_id в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(Channel)
    if owner_id: query = query.filter(Channel.user_id == owner_id)
    return query.all()

def delete_channel(db_session, chat_id: str, user_id: Optional[int] = None):
    """Удаляет канал, фильтруя по user_id в public режиме."""
    channel = get_channel(db_session, chat_id=chat_id, user_id=user_id)
    if channel:
        db_session.delete(channel)
        db_session.commit()
        logger.info(f"Канал {chat_id} удален для пользователя {user_id or 'N/A'}.")
        return True
    logger.warning(f"Канал {chat_id} не найден для пользователя {user_id or 'N/A'}.")
    return False

# Ленты
def add_feed(db_session, url: str, name: str = None, update_interval_minutes: int = 60, publish_delay_minutes: int = 0, user_id: Optional[int] = None):
    """Добавляет новую RSS-ленту, привязывая к пользователю в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(RSSFeed).filter(RSSFeed.url == url)
    if owner_id: query = query.filter(RSSFeed.user_id == owner_id)
    existing_feed = query.first()

    if existing_feed:
        logger.warning(f"Лента {url} уже существует для пользователя {owner_id or 'N/A'}.")
        return existing_feed

    new_feed = RSSFeed(
        url=url, name=name, update_interval_minutes=update_interval_minutes,
        publish_delay_minutes=publish_delay_minutes, user_id=owner_id
    )
    db_session.add(new_feed)
    db_session.commit()
    db_session.refresh(new_feed)
    logger.info(f"Лента {url} успешно добавлена для пользователя {owner_id or 'N/A'}.")
    return new_feed

def get_feed(db_session, feed_id: int = None, url: str = None, user_id: Optional[int] = None):
    """Получает ленту по ID или URL, фильтруя по user_id в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(RSSFeed)
    if owner_id: query = query.filter(RSSFeed.user_id == owner_id)

    if feed_id: return query.filter(RSSFeed.id == feed_id).first()
    if url: return query.filter(RSSFeed.url == url).first()
    return None

def get_all_feeds(db_session, user_id: Optional[int] = None):
    """Получает все RSS-ленты, фильтруя по user_id в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(RSSFeed)
    if owner_id: query = query.filter(RSSFeed.user_id == owner_id)
    return query.all()

# update_feed_last_checked не зависит от пользователя, т.к. проверка глобальна
def update_feed_last_checked(db_session, feed_id: int):
    feed = db_session.query(RSSFeed).filter(RSSFeed.id == feed_id).first() # Получаем без фильтра по user_id
    if feed:
        feed.last_checked = datetime.now(timezone.utc)
        db_session.commit()

def update_feed_delay(db_session, feed_id: int, delay_minutes: int, user_id: Optional[int] = None):
    """Обновляет задержку публикации, проверяя владельца в public режиме."""
    feed = get_feed(db_session, feed_id=feed_id, user_id=user_id)
    if feed:
        feed.publish_delay_minutes = delay_minutes
        db_session.commit()
        logger.info(f"Задержка для ленты ID {feed_id} (User: {user_id or 'N/A'}) установлена на {delay_minutes} мин.")
        return True
    logger.warning(f"Лента ID {feed_id} не найдена для пользователя {user_id or 'N/A'}.")
    return False

def delete_feed(db_session, feed_id: int, user_id: Optional[int] = None):
    """Удаляет ленту, проверяя владельца в public режиме."""
    feed = get_feed(db_session, feed_id=feed_id, user_id=user_id)
    if feed:
        url_deleted = feed.url
        db_session.delete(feed)
        db_session.commit()
        logger.info(f"Лента ID {feed_id} ({url_deleted}) удалена для пользователя {user_id or 'N/A'}.")
        return True
    logger.warning(f"Лента ID {feed_id} не найдена для пользователя {user_id or 'N/A'}.")
    return False

# Подписки
def subscribe_channel_to_feed(db_session, chat_id: str, feed_id: int, hashtags: str = None, user_id: Optional[int] = None):
    """Подписывает канал на ленту, привязывая к пользователю в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    channel = get_channel(db_session, chat_id=chat_id, user_id=owner_id)
    feed = get_feed(db_session, feed_id=feed_id, user_id=owner_id) # Лента тоже должна принадлежать пользователю

    if not channel: return False, f"Канал {chat_id} не найден."
    if not feed: return False, f"Лента ID {feed_id} не найдена."

    query = db_session.query(ChannelFeedLink).filter_by(channel_id=channel.id, feed_id=feed.id)
    if owner_id: query = query.filter(ChannelFeedLink.user_id == owner_id)
    existing_link = query.first()

    if existing_link: return False, "Канал уже подписан на эту ленту."

    clean_hashtags = format_hashtags(hashtags) if hashtags else None
    link = ChannelFeedLink(user_id=owner_id, channel_id=channel.id, feed_id=feed.id, hashtags=clean_hashtags)
    db_session.add(link)
    db_session.commit()
    msg = f"Успешно подписан. Хештеги: {clean_hashtags or 'нет'}."
    logger.info(f"Канал {chat_id} (User: {owner_id or 'N/A'}) подписан на ленту ID {feed_id}. {msg}")
    return True, msg

def unsubscribe_channel_from_feed(db_session, chat_id: str, feed_id: int, user_id: Optional[int] = None):
    """Отписывает канал от ленты, проверяя владельца в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    channel = get_channel(db_session, chat_id=chat_id, user_id=owner_id)
    feed = get_feed(db_session, feed_id=feed_id, user_id=owner_id)

    if not channel or not feed: return False

    query = db_session.query(ChannelFeedLink).filter_by(channel_id=channel.id, feed_id=feed.id)
    if owner_id: query = query.filter(ChannelFeedLink.user_id == owner_id)
    link = query.first()

    if link:
        db_session.delete(link)
        db_session.commit()
        logger.info(f"Канал {chat_id} (User: {owner_id or 'N/A'}) отписан от ленты ID {feed_id}.")
        return True
    logger.warning(f"Подписка канала {chat_id} на ленту ID {feed_id} не найдена для пользователя {owner_id or 'N/A'}.")
    return False

def get_subscription(db_session, channel_id: int, feed_id: int, user_id: Optional[int] = None) -> ChannelFeedLink | None:
    """Получает подписку, фильтруя по user_id в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(ChannelFeedLink).filter_by(channel_id=channel_id, feed_id=feed_id)
    if owner_id: query = query.filter(ChannelFeedLink.user_id == owner_id)
    return query.first()

def update_subscription_hashtags(db_session, channel_id: int, feed_id: int, hashtags: str | None, user_id: Optional[int] = None):
    """Обновляет хештеги, проверяя владельца в public режиме."""
    link = get_subscription(db_session, channel_id=channel_id, feed_id=feed_id, user_id=user_id)
    if not link: return False, "Подписка не найдена."

    clean_hashtags = format_hashtags(hashtags) if hashtags else None
    link.hashtags = clean_hashtags
    db_session.commit()
    msg = f"Хештеги обновлены: {clean_hashtags or 'удалены'}."
    logger.info(f"Хештеги для подписки канала ID {channel_id} на ленту ID {feed_id} (User: {user_id or 'N/A'}) обновлены.")
    return True, msg

def get_feeds_for_channel(db_session, chat_id: str, user_id: Optional[int] = None):
    """Получает ленты для канала, фильтруя по user_id в public режиме."""
    channel = get_channel(db_session, chat_id=chat_id, user_id=user_id)
    if channel: return [link.feed for link in channel.feeds]
    return []

def get_subscriptions_for_channel(db_session, channel_id: int, user_id: Optional[int] = None) -> List[ChannelFeedLink]:
     """Получает подписки для канала, фильтруя по user_id в public режиме."""
     owner_id = user_id if BOT_MODE == 'public' else None
     query = db_session.query(ChannelFeedLink).filter(ChannelFeedLink.channel_id == channel_id)
     if owner_id: query = query.filter(ChannelFeedLink.user_id == owner_id)
     return query.all()

def get_channels_for_feed(db_session, feed_id: int):
    """Получает все каналы, подписанные на ленту (не зависит от пользователя)."""
    # Эта функция используется планировщиком, который должен знать всех подписчиков ленты
    feed = db_session.query(RSSFeed).filter(RSSFeed.id == feed_id).first()
    if feed: return [link.channel for link in feed.channels] # Возвращает объекты Channel
    return []

def get_subscriptions_for_feed(db_session, feed_id: int) -> List[ChannelFeedLink]:
    """Получает все объекты подписок для данной ленты (не зависит от пользователя)."""
    return db_session.query(ChannelFeedLink).filter(ChannelFeedLink.feed_id == feed_id).all()


# Опубликованные посты (не зависят от пользователя)
def add_published_post(db_session, feed_id: int, post_guid: str):
    if len(post_guid) > 512: post_guid = post_guid[:512]
    if is_post_published(db_session, feed_id, post_guid): return None
    new_post = PublishedPost(feed_id=feed_id, post_guid=post_guid)
    db_session.add(new_post)
    logger.info(f"Запись об обработке поста {post_guid} для ленты {feed_id} добавлена.")
    return new_post

def is_post_published(db_session, feed_id: int, post_guid: str) -> bool:
    if len(post_guid) > 512: post_guid = post_guid[:512]
    return db_session.query(PublishedPost).filter_by(feed_id=feed_id, post_guid=post_guid).count() > 0

# Отложенные посты
def add_scheduled_post(db_session, feed_id: int, channel_id: int, post_guid: str, scheduled_time: datetime, post_data: dict, hashtags: str | None = None, user_id: Optional[int] = None):
    """Добавляет пост в очередь, привязывая к пользователю в public режиме."""
    owner_id = user_id if BOT_MODE == 'public' else None
    query = db_session.query(ScheduledPost).filter_by(feed_id=feed_id, channel_id=channel_id, post_guid=post_guid)
    if owner_id: query = query.filter(ScheduledPost.user_id == owner_id)
    existing = query.first()

    if existing:
        logger.warning(f"Пост {post_guid} для канала ID {channel_id} (User: {owner_id or 'N/A'}) уже в очереди.")
        return None
    if len(post_guid) > 512: post_guid = post_guid[:512]
    new_scheduled_post = ScheduledPost(
        user_id=owner_id, feed_id=feed_id, channel_id=channel_id, post_guid=post_guid,
        scheduled_time=scheduled_time, post_title=post_data.get('title'),
        post_link=post_data.get('link'), post_summary=post_data.get('summary'),
        hashtags=hashtags, status="pending"
    )
    db_session.add(new_scheduled_post)
    logger.info(f"Пост {post_guid} добавлен в очередь для канала ID {channel_id} (User: {owner_id or 'N/A'}) на {scheduled_time.strftime('%Y-%m-%d %H:%M:%S %Z')}.")
    return new_scheduled_post

def get_pending_scheduled_posts(db_session, limit=100):
    """Получает посты, готовые к публикации (не зависит от пользователя)."""
    now = datetime.now(timezone.utc)
    return db_session.query(ScheduledPost).filter(
        ScheduledPost.status == "pending",
        ScheduledPost.scheduled_time <= now
    ).order_by(ScheduledPost.scheduled_time).limit(limit).all()

def update_scheduled_post_status(db_session, post_id: int, status: str):
    """Обновляет статус отложенного поста."""
    post = db_session.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
    if post:
        post.status = status
        logger.info(f"Статус отложенного поста ID {post_id} обновлен на '{status}'.")
        return True
    logger.warning(f"Не найден отложенный пост ID {post_id} для обновления статуса.")
    return False

def delete_scheduled_post(db_session, post_id: int):
    """Удаляет отложенный пост."""
    post = db_session.query(ScheduledPost).filter(ScheduledPost.id == post_id).first()
    if post:
        db_session.delete(post)
        logger.info(f"Отложенный пост ID {post_id} удален.")
        return True
    return False

def format_hashtags(hashtags: Optional[str]) -> Optional[str]:
    """Вспомогательная функция для форматирования хештегов."""
    if not hashtags:
        return None
    tags = [f"#{tag.strip('#')}" for tag in hashtags.split() if tag.strip()]
    return " ".join(tags) if tags else None
