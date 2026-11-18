import time
import struct
from pyrogram import Client, enums
from pyrogram.types import Message
from pyrogram.errors import (
    AuthKeyDuplicated,
    AuthKeyUnregistered,
    UserDeactivated,
    SessionRevoked,
    Unauthorized
)
from core.config import API_ID, API_HASH, logger
from core.client import bot, safe_edit_text
from core.states import CACHED_USER_CLIENTS, CLIENT_LAST_SEEN
from database.repository import save_user_session, delete_user_session
from ui.keyboards import get_add_buttons, send_clean_pm_notice
from ui.templates import session_success_pm_template, session_success_group_template

async def verify_and_save_session(message: Message, user_id: int, session_str: str):
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    if is_pm:
        status = await send_clean_pm_notice(message.chat.id, "⏳ <b>Verifying Pyrogram session string...</b>")
    else:
        try:
            status = await message.reply_text("⏳ <b>Verifying Pyrogram session string...</b>")
        except Exception:
            status = await bot.send_message(message.chat.id, "⏳ <b>Verifying Pyrogram session string...</b>")

    temp_user = None
    try:
        if user_id in CACHED_USER_CLIENTS:
            try:
                await CACHED_USER_CLIENTS[user_id].stop()
            except Exception:
                pass
            del CACHED_USER_CLIENTS[user_id]
            CLIENT_LAST_SEEN.pop(user_id, None)

        temp_user = Client(
            f"persistent_user_{user_id}",
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
        await temp_user.start()
        me = await temp_user.get_me()
        temp_user._session_string = session_str
        CACHED_USER_CLIENTS[user_id] = temp_user
        CLIENT_LAST_SEEN[user_id] = time.time()
        save_user_session(user_id, session_str)

        if is_pm:
            resp_text = session_success_pm_template(me.first_name)
            buttons = await get_add_buttons(user_id)
            await safe_edit_text(status, resp_text, reply_markup=buttons)
        else:
            resp_text = session_success_group_template(me.first_name)
            await safe_edit_text(status, resp_text)

    except (AuthKeyDuplicated, AuthKeyUnregistered, UserDeactivated, SessionRevoked, Unauthorized) as e:
        logger.error(f"Session terminated on another device: {e}")
        delete_user_session(user_id)
        await safe_edit_text(status, "❌ <b>Session Expired or Terminated:</b> The session key was revoked or used on another device. Please generate a fresh Pyrogram session.")
    except (struct.error, ValueError) as e:
        logger.error(f"Malformed session string for user {user_id}: {e}")
        await safe_edit_text(status, "❌ <b>Invalid Session String:</b> The string is malformed or not a valid <b>Pyrogram v2</b> session. Please generate a fresh session.")
    except Exception as e:
        logger.error(f"Session verification failed for user {user_id}: {e}", exc_info=True)
        await safe_edit_text(status, f"❌ <b>Invalid Session:</b> <code>{str(e)}</code>")
    finally:
        if temp_user and user_id not in CACHED_USER_CLIENTS:
            try:
                if getattr(temp_user, "is_connected", False):
                    await temp_user.stop()
            except Exception:
                pass

