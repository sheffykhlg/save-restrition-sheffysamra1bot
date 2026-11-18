import re
import time
from pyrogram import Client, enums
from pyrogram.types import Message
from core.config import FSUB_CHANNEL, LOG_CHANNEL_ID
from core.client import get_entity_id
from core.states import PROMPT_STATES
from database.repository import (
    record_bot_user,
    record_user_chat,
    save_user_replace_rule,
    get_user_session
)
from parsers.link import is_telegram_link_private
from services.session_service import verify_and_save_session
from services.batch_service import execute_batch_job
from ui.keyboards import get_add_buttons, get_fsub_markup, send_clean_pm_notice
from ui.templates import pm_denied_template, fsub_denied_template
from handlers.fsub import is_user_fsub_member

async def text_and_batch_listener(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return

    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    text = message.text.strip()
    is_pm = message.chat.type == enums.ChatType.PRIVATE

    if not is_pm:
        record_user_chat(user_id, message.chat)

    if not await is_user_fsub_member(client, user_id):
        if is_pm:
            try:
                await message.delete()
            except Exception:
                pass
            fsub_text = fsub_denied_template()
            await send_clean_pm_notice(message.chat.id, fsub_text, reply_markup=get_fsub_markup())
        else:
            fsub_text = fsub_denied_template(message.from_user.mention if message.from_user else 'User')
            await message.reply_text(fsub_text, reply_markup=get_fsub_markup())
        return

    # Check conversational state machine
    if user_id in PROMPT_STATES:
        state = PROMPT_STATES[user_id]
        if time.time() - state.get("timestamp", time.time()) > 600:
            del PROMPT_STATES[user_id]
        elif state["step"] == "AWAIT_SESSION":
            del PROMPT_STATES[user_id]
            try:
                await message.delete()
            except Exception:
                pass
            await verify_and_save_session(message, user_id, text)
            return
        elif state["step"] == "AWAIT_OLD_WORD":
            state["old_word"] = text.strip('"\'')
            state["step"] = "AWAIT_NEW_WORD"
            state["timestamp"] = time.time()
            prompt_text = (
                f"✅ <b>Word to replace:</b> <code>{state['old_word']}</code>\n\n"
                f"Now send the replacement word (e.g. <code>desibotz</code>):"
            )
            if is_pm:
                try:
                    await message.delete()
                except Exception:
                    pass
                await send_clean_pm_notice(message.chat.id, prompt_text)
            else:
                await message.reply_text(prompt_text)
            return
        elif state["step"] == "AWAIT_NEW_WORD":
            old_word = state["old_word"]
            new_word = text.strip('"\'')
            del PROMPT_STATES[user_id]
            save_user_replace_rule(user_id, old_word, new_word)
            resp_text = (
                f"✅ <b>Rule Saved!</b>\n\n"
                f"🔄 <b>Old:</b> <code>{old_word}</code>\n"
                f"➡️ <b>New:</b> <code>{new_word}</code>"
            )
            if is_pm:
                try:
                    await message.delete()
                except Exception:
                    pass
                buttons = await get_add_buttons(user_id)
                await send_clean_pm_notice(message.chat.id, resp_text, reply_markup=buttons)
            else:
                await message.reply_text(resp_text)
            return
        elif state["step"] == "AWAIT_LINK":
            if not re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/", text):
                err_text = "❌ <b>Invalid link. Send a valid Telegram post link or /cancel.</b>"
                if is_pm:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await send_clean_pm_notice(message.chat.id, err_text)
                else:
                    await message.reply_text(err_text)
                return
            state["start_link"] = text
            state["step"] = "AWAIT_RANGE"
            state["timestamp"] = time.time()
            prompt_text = (
                "✅ <b>Link received!</b>\n\n"
                "Enter how many messages you want to download (e.g. <code>5</code>):"
            )
            if is_pm:
                try:
                    await message.delete()
                except Exception:
                    pass
                await send_clean_pm_notice(message.chat.id, prompt_text)
            else:
                await message.reply_text(prompt_text)
            return
        elif state["step"] == "AWAIT_RANGE":
            if not text.isdigit():
                err_text = "❌ <b>Please send a valid number or /cancel.</b>"
                if is_pm:
                    try:
                        await message.delete()
                    except Exception:
                        pass
                    await send_clean_pm_notice(message.chat.id, err_text)
                else:
                    await message.reply_text(err_text)
                return
            count = max(int(text), 1)
            start_link = state["start_link"]
            del PROMPT_STATES[user_id]
            is_private = is_telegram_link_private(start_link)
            session_str = get_user_session(user_id)
            if is_private and not session_str:
                await message.reply_text("🔒 <b>Private Channel Link Detected!</b>\n\nPrivate posts require a connected Pyrogram session. Use /addsession first.")
                return
            if is_pm:
                try:
                    await message.delete()
                except Exception:
                    pass
                notice_text = (
                    "⚠️ <b>THIS BOT DOES NOT WORK IN PM!</b>\n\n"
                    "Downloading is only supported inside <b>Groups</b> and <b>Channels</b>.\n\n"
                    "Please add me to your Group or Channel using the buttons below and execute batch jobs there!"
                )
                buttons = await get_add_buttons(user_id)
                await send_clean_pm_notice(message.chat.id, notice_text, reply_markup=buttons)
                return
            await execute_batch_job(message, session_str, start_link, count)
            return

    # Auto-detect and instantly delete raw session string pasted in Group/Channel for privacy
    if (text.startswith("BA") or text.startswith("BQ") or text.startswith("1B")) and len(text) > 150:
        try:
            await message.delete()
        except Exception:
            pass
        await verify_and_save_session(message, user_id, text)
        return

    # In PM: Auto-delete user's message and send clean notice with Group/Channel buttons
    if is_pm:
        try:
            await message.delete()
        except Exception:
            pass
        notice_text = pm_denied_template()
        buttons = await get_add_buttons(user_id)
        await send_clean_pm_notice(message.chat.id, notice_text, reply_markup=buttons)
        return

    # In Group/Channel: execute single post download
    if re.search(r"(?:t\.me|telegram\.me|telegram\.dog)/", text):
        is_private = is_telegram_link_private(text)
        session_str = get_user_session(user_id)
        if is_private and not session_str:
            await message.reply_text("🔒 <b>Private Channel Link Detected!</b>\n\nPrivate posts require a connected Pyrogram session. Use /addsession first.")
            return
        await execute_batch_job(message, session_str, text, range_count=1)

