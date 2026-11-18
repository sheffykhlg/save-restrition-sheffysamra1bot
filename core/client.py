import os
import time
import asyncio
from pyrogram import Client, enums
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait,
    AuthKeyDuplicated,
    AuthKeyUnregistered,
    UserDeactivated,
    SessionRevoked,
    Unauthorized
)
from core.config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    logger,
    encrypt_session,
    decrypt_session
)
from core.states import CACHED_USER_CLIENTS, CLIENT_LAST_SEEN, ACTIVE_TASKS
from database.mongo import bot_meta_col
from database.repository import delete_user_session

_cached_bot_doc = bot_meta_col.find_one({"_id": "main_bot_session"})
_saved_bot_session = _cached_bot_doc.get("session_string") if _cached_bot_doc else None
if not _saved_bot_session and os.path.exists(".botsession"):
    try:
        with open(".botsession", "r", encoding="utf-8") as f:
            _local_s = f.read().strip()
            if _local_s:
                _saved_bot_session = encrypt_session(_local_s)
    except Exception:
        pass

bot_kwargs = {
    "name": "universal_bot_interface",
    "api_id": API_ID,
    "api_hash": API_HASH,
    "workers": 64,
    "max_concurrent_transmissions": 8,
    "parse_mode": enums.ParseMode.HTML,
    "sleep_threshold": 180
}
if _saved_bot_session:
    bot_kwargs["session_string"] = decrypt_session(_saved_bot_session)
else:
    bot_kwargs["bot_token"] = BOT_TOKEN

bot = Client(**bot_kwargs)

def get_entity_id(message: Message) -> int:
    if message.from_user:
        return message.from_user.id
    return message.chat.id

async def resolve_peer_safely(chat_id):
    try:
        await bot.get_chat(chat_id)
    except Exception as e:
        logger.warning(f"Could not pre-resolve peer {chat_id}: {e}")

async def safe_edit_text(status_msg: Message, text: str, reply_markup=None):
    try:
        if reply_markup is not None:
            await status_msg.edit_text(text, reply_markup=reply_markup)
        else:
            await status_msg.edit_text(text)
    except FloodWait as f:
        await asyncio.sleep(f.value + 1)
        if reply_markup is not None:
            await status_msg.edit_text(text, reply_markup=reply_markup)
        else:
            await status_msg.edit_text(text)

async def safe_delete_msg(status_msg: Message):
    try:
        await status_msg.delete()
    except FloodWait as f:
        await asyncio.sleep(f.value + 1)
        await status_msg.delete()
    except Exception:
        pass

def cleanup_idle_clients(max_idle_seconds=1800, max_clients=25):
    """
    Optimized for Heroku 2X Standard (1024 MB RAM):
    Safely disconnects and unloads user clients that have been idle
    for over 30 minutes or when total cached clients exceed limit.
    """
    now = time.time()
    for uid in list(CACHED_USER_CLIENTS.keys()):
        if uid in ACTIVE_TASKS:
            continue
        last_seen = CLIENT_LAST_SEEN.get(uid, 0)
        if (now - last_seen > max_idle_seconds) or (len(CACHED_USER_CLIENTS) > max_clients):
            client = CACHED_USER_CLIENTS.pop(uid, None)
            CLIENT_LAST_SEEN.pop(uid, None)
            if client:
                try:
                    asyncio.create_task(client.stop())
                except Exception:
                    pass

# =====================================================================
# ⛔ [LOCKED ARCHITECTURE] PERSISTENT CONNECTION CACHE (MULTI-DC MTProto)
# DO NOT MODIFY OR REMOVE: Preserves DC1-DC5 auth keys across batch jobs.
# =====================================================================
async def get_or_create_user_client(user_id: int, session_str: str) -> Client:
    if user_id in CACHED_USER_CLIENTS:
        client = CACHED_USER_CLIENTS[user_id]
        cached_sess = getattr(client, "_session_string", None)
        if cached_sess and cached_sess != session_str:
            try:
                if getattr(client, "is_connected", False):
                    await client.stop()
            except Exception:
                pass
            CACHED_USER_CLIENTS.pop(user_id, None)
        else:
            if getattr(client, "is_connected", False):
                CLIENT_LAST_SEEN[user_id] = time.time()
                return client
            try:
                await client.connect()
                CLIENT_LAST_SEEN[user_id] = time.time()
                return client
            except (AuthKeyDuplicated, AuthKeyUnregistered, UserDeactivated, SessionRevoked, Unauthorized) as auth_err:
                delete_user_session(user_id)
                CACHED_USER_CLIENTS.pop(user_id, None)
                raise auth_err
            except Exception:
                CACHED_USER_CLIENTS.pop(user_id, None)

    user_app = Client(
        name=f"persistent_user_{user_id}",
        api_id=API_ID,
        api_hash=API_HASH,
        session_string=session_str,
        workers=64,
        max_concurrent_transmissions=16,
        sleep_threshold=180,
        no_updates=True,
        skip_updates=True,
        in_memory=True
    )
    user_app._session_string = session_str
    try:
        await user_app.start()
    except (AuthKeyDuplicated, AuthKeyUnregistered, UserDeactivated, SessionRevoked, Unauthorized) as e:
        delete_user_session(user_id)
        CACHED_USER_CLIENTS.pop(user_id, None)
        raise e
    CACHED_USER_CLIENTS[user_id] = user_app
    CLIENT_LAST_SEEN[user_id] = time.time()
    return user_app

