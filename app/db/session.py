import os
import sqlite3
import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Generator, Any
from app.config import settings

logger = logging.getLogger(__name__)

USE_POSTGRES = False
if settings.DATABASE_URL and settings.DATABASE_URL.startswith(("postgres://", "postgresql://")):
    try:
        import psycopg
        from psycopg.rows import dict_row
        USE_POSTGRES = True
    except ImportError:
        logger.warning("psycopg is not installed. Falling back to local SQLite database.")
        USE_POSTGRES = False

DB_FILE = Path(__file__).parent / "local_store.db"


@contextmanager
def get_db() -> Generator[Any, None, None]:
    """
    Context manager yielding a database connection.
    Automatically handles PostgreSQL (Neon) or SQLite fallback.
    """
    if USE_POSTGRES:
        conn = psycopg.connect(settings.DATABASE_URL, row_factory=dict_row)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
    else:
        conn = sqlite3.connect(str(DB_FILE))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()


def init_db():
    """Initializes tables in either PostgreSQL or SQLite."""
    with get_db() as conn:
        cursor = conn.cursor()
        
        if USE_POSTGRES:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id     BIGINT PRIMARY KEY,
                    username        VARCHAR(128) DEFAULT '',
                    full_name       VARCHAR(256) DEFAULT '',
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS user_credentials (
                    telegram_id     BIGINT PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
                    same_instance   BOOLEAN DEFAULT TRUE,
                    att_odoo_url    TEXT NOT NULL,
                    att_odoo_db     TEXT NOT NULL,
                    att_odoo_user   TEXT NOT NULL,
                    att_odoo_key    TEXT NOT NULL,
                    task_odoo_url   TEXT NOT NULL,
                    task_odoo_db    TEXT NOT NULL,
                    task_odoo_user  TEXT NOT NULL,
                    task_odoo_key   TEXT NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW(),
                    updated_at      TIMESTAMPTZ DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id              BIGSERIAL PRIMARY KEY,
                    telegram_id     BIGINT REFERENCES users(telegram_id) ON DELETE CASCADE,
                    role            VARCHAR(32) NOT NULL,
                    content         TEXT NOT NULL,
                    created_at      TIMESTAMPTZ DEFAULT NOW()
                );
            """)
        else:
            cursor.executescript("""
                CREATE TABLE IF NOT EXISTS users (
                    telegram_id     INTEGER PRIMARY KEY,
                    username        TEXT DEFAULT '',
                    full_name       TEXT DEFAULT '',
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS user_credentials (
                    telegram_id     INTEGER PRIMARY KEY REFERENCES users(telegram_id) ON DELETE CASCADE,
                    same_instance   INTEGER DEFAULT 1,
                    att_odoo_url    TEXT NOT NULL,
                    att_odoo_db     TEXT NOT NULL,
                    att_odoo_user   TEXT NOT NULL,
                    att_odoo_key    TEXT NOT NULL,
                    task_odoo_url   TEXT NOT NULL,
                    task_odoo_db    TEXT NOT NULL,
                    task_odoo_user  TEXT NOT NULL,
                    task_odoo_key   TEXT NOT NULL,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS chat_history (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id     INTEGER REFERENCES users(telegram_id) ON DELETE CASCADE,
                    role            TEXT NOT NULL,
                    content         TEXT NOT NULL,
                    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );
            """)
