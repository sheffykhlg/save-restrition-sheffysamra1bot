import time
import asyncio
from pyrogram import enums
from core.config import logger, encrypt_session, decrypt_session
from core.states import CACHED_USER_CLIENTS, CLIENT_LAST_SEEN
from database.mongo import (
    sessions_col,
    replace_rules_col,
    user_chats_col,
    bot_users_col,
    batch_jobs_col
)

def record_user_chat(user_id: int, chat):
    if not user_id or not chat or chat.type == enums.ChatType.PRIVATE:
        return
    try:
        chat_link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
        user_chats_col.update_one(
            {"user_id": user_id, "chat_id": chat.id},
            {
                "$set": {
                    "chat_id": chat.id,
                    "title": chat.title or "Chat",
                    "type": "Channel" if chat.type == enums.ChatType.CHANNEL else "Group",
                    "link": chat_link,
                    "updated_at": time.time()
                }
            },
            upsert=True
        )
    except Exception as e:
        logger.debug(f"Could not record user chat: {e}")

def record_bot_user(user):
    if not user or not getattr(user, "id", None):
        return
    try:
        bot_users_col.update_one(
            {"user_id": user.id},
            {"$set": {
                "first_name": getattr(user, "first_name", ""),
                "last_name": getattr(user, "last_name", ""),
                "username": getattr(user, "username", ""),
                "updated_at": time.time()
            }},
            upsert=True
        )
    except Exception as e:
        logger.debug(f"Could not record bot user: {e}")

def get_user_session(user_id: int):
    data = sessions_col.find_one({"user_id": user_id})
    if not data or not data.get("session_string"):
        return None
    try:
        return decrypt_session(data["session_string"])
    except Exception as e:
        logger.error(f"Error decrypting session for user {user_id}: {e}", exc_info=True)
        return None

def save_user_session(user_id: int, session_str: str):
    encrypted_session = encrypt_session(session_str)
    sessions_col.update_one(
        {"user_id": user_id},
        {"$set": {"session_string": encrypted_session, "updated_at": time.time()}},
        upsert=True
    )

def delete_user_session(user_id: int):
    sessions_col.delete_one({"user_id": user_id})
    replace_rules_col.delete_one({"user_id": user_id})
    CLIENT_LAST_SEEN.pop(user_id, None)
    if user_id in CACHED_USER_CLIENTS:
        try:
            client = CACHED_USER_CLIENTS.pop(user_id, None)
            if client:
                asyncio.create_task(client.stop())
        except Exception as e:
            logger.error(f"Error stopping user client for {user_id}: {e}", exc_info=True)

def get_user_replace_rules(user_id: int) -> dict:
    data = replace_rules_col.find_one({"user_id": user_id})
    return data.get("rules", {}) if data else {}

def save_user_replace_rule(user_id: int, old_word: str, new_word: str):
    data = replace_rules_col.find_one({"user_id": user_id}) or {"rules": {}}
    rules = data.get("rules", {})
    rules[old_word] = new_word
    replace_rules_col.update_one(
        {"user_id": user_id},
        {"$set": {"rules": rules, "updated_at": time.time()}},
        upsert=True
    )

def save_or_update_batch_job(job_id: str, data: dict):
    batch_jobs_col.update_one(
        {"_id": job_id},
        {"$set": data},
        upsert=True
    )

def delete_batch_job(job_id: str):
    batch_jobs_col.delete_one({"_id": job_id})

def get_running_batch_jobs() -> list:
    try:
        return list(batch_jobs_col.find({"status": "RUNNING"}))
    except Exception as e:
        logger.error(f"Error querying pending batch jobs: {e}")
        return []

def get_db_stats() -> dict:
    total_sessions = sessions_col.count_documents({})
    total_users = bot_users_col.count_documents({})
    total_chats = user_chats_col.count_documents({})
    return {
        "total_users": max(total_users, total_sessions),
        "total_sessions": total_sessions,
        "total_chats": total_chats
    }

