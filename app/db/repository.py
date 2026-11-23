from typing import Optional, Dict, Any, List
from app.db.session import get_db, USE_POSTGRES
from app.security.crypto import encrypt_val, decrypt_val


def upsert_user(telegram_id: int, username: str = "", full_name: str = "") -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO users (telegram_id, username, full_name)
                VALUES (%s, %s, %s)
                ON CONFLICT (telegram_id) DO UPDATE 
                SET username = EXCLUDED.username, full_name = EXCLUDED.full_name;
            """, (telegram_id, username, full_name))
        else:
            cursor.execute("""
                INSERT INTO users (telegram_id, username, full_name)
                VALUES (?, ?, ?)
                ON CONFLICT(telegram_id) DO UPDATE 
                SET username = excluded.username, full_name = excluded.full_name;
            """, (telegram_id, username, full_name))


def save_credentials(
    telegram_id: int,
    same_instance: bool,
    att_url: str = "",
    att_db: str = "",
    att_user: str = "",
    att_key: str = "",
    task_url: str = "",
    task_db: str = "",
    task_user: str = "",
    task_key: str = "",
) -> None:
    """Save encrypted credentials for both instances with smart merging."""
    # Ensure user record exists first to satisfy foreign key constraint
    upsert_user(telegram_id)

    # Check existing credentials to preserve partial updates
    existing = get_credentials(telegram_id) or {}

    if same_instance:
        task_url = att_url
        task_db = att_db
        task_user = att_user
        task_key = att_key
    else:
        # Preserve existing if only one instance was submitted in this update
        if not att_url and existing.get("att_odoo_url"):
            att_url = existing["att_odoo_url"]
            att_db = existing.get("att_odoo_db", "")
            att_user = existing.get("att_odoo_user", "")
            att_key = existing.get("att_odoo_key", "")

        if not task_url and existing.get("task_odoo_url"):
            task_url = existing["task_odoo_url"]
            task_db = existing.get("task_odoo_db", "")
            task_user = existing.get("task_odoo_user", "")
            task_key = existing.get("task_odoo_key", "")

    enc_att_key = encrypt_val(att_key) if att_key else ""
    enc_task_key = encrypt_val(task_key) if task_key else ""

    with get_db() as conn:
        cursor = conn.cursor()
        if USE_POSTGRES:
            cursor.execute("""
                INSERT INTO user_credentials (
                    telegram_id, same_instance,
                    att_odoo_url, att_odoo_db, att_odoo_user, att_odoo_key,
                    task_odoo_url, task_odoo_db, task_odoo_user, task_odoo_key,
                    updated_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (telegram_id) DO UPDATE SET
                    same_instance = EXCLUDED.same_instance,
                    att_odoo_url = EXCLUDED.att_odoo_url,
                    att_odoo_db = EXCLUDED.att_odoo_db,
                    att_odoo_user = EXCLUDED.att_odoo_user,
                    att_odoo_key = EXCLUDED.att_odoo_key,
                    task_odoo_url = EXCLUDED.task_odoo_url,
                    task_odoo_db = EXCLUDED.task_odoo_db,
                    task_odoo_user = EXCLUDED.task_odoo_user,
                    task_odoo_key = EXCLUDED.task_odoo_key,
                    updated_at = NOW();
            """, (
                telegram_id, same_instance,
                att_url, att_db, att_user, enc_att_key,
                task_url, task_db, task_user, enc_task_key
            ))
        else:
            cursor.execute("""
                INSERT INTO user_credentials (
                    telegram_id, same_instance,
                    att_odoo_url, att_odoo_db, att_odoo_user, att_odoo_key,
                    task_odoo_url, task_odoo_db, task_odoo_user, task_odoo_key,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(telegram_id) DO UPDATE SET
                    same_instance = excluded.same_instance,
                    att_odoo_url = excluded.att_odoo_url,
                    att_odoo_db = excluded.att_odoo_db,
                    att_odoo_user = excluded.att_odoo_user,
                    att_odoo_key = excluded.att_odoo_key,
                    task_odoo_url = excluded.task_odoo_url,
                    task_odoo_db = excluded.task_odoo_db,
                    task_odoo_user = excluded.task_odoo_user,
                    task_odoo_key = excluded.task_odoo_key,
                    updated_at = CURRENT_TIMESTAMP;
            """, (
                telegram_id, 1 if same_instance else 0,
                att_url, att_db, att_user, enc_att_key,
                task_url, task_db, task_user, enc_task_key
            ))


def get_credentials(telegram_id: int) -> Optional[Dict[str, Any]]:
    """Retrieve and decrypt credentials for a given user."""
    with get_db() as conn:
        cursor = conn.cursor()
        query = "SELECT * FROM user_credentials WHERE telegram_id = " + ("%s" if USE_POSTGRES else "?")
        cursor.execute(query, (telegram_id,))
        row = cursor.fetchone()
        if not row:
            return None

        data = dict(row)
        data["att_odoo_key"] = decrypt_val(data.get("att_odoo_key", "")) if data.get("att_odoo_key") else ""
        data["task_odoo_key"] = decrypt_val(data.get("task_odoo_key", "")) if data.get("task_odoo_key") else ""
        return data


def delete_credentials(telegram_id: int) -> bool:
    with get_db() as conn:
        cursor = conn.cursor()
        query = "DELETE FROM user_credentials WHERE telegram_id = " + ("%s" if USE_POSTGRES else "?")
        cursor.execute(query, (telegram_id,))
        return cursor.rowcount > 0


def save_chat_message(telegram_id: int, role: str, content: str) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        query = "INSERT INTO chat_history (telegram_id, role, content) VALUES (" + ("%s, %s, %s" if USE_POSTGRES else "?, ?, ?") + ")"
        cursor.execute(query, (telegram_id, role, content))


def get_chat_history(telegram_id: int, limit: int = 10) -> List[Dict[str, str]]:
    with get_db() as conn:
        cursor = conn.cursor()
        query = f"SELECT role, content FROM chat_history WHERE telegram_id = {'%s' if USE_POSTGRES else '?'} ORDER BY id DESC LIMIT {limit}"
        cursor.execute(query, (telegram_id,))
        rows = cursor.fetchall()
        return [{"role": r["role"], "content": r["content"]} for r in reversed(rows)]


def clear_chat_history(telegram_id: int) -> None:
    with get_db() as conn:
        cursor = conn.cursor()
        query = "DELETE FROM chat_history WHERE telegram_id = " + ("%s" if USE_POSTGRES else "?")
        cursor.execute(query, (telegram_id,))
