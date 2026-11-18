import os
import gc
import time
import shlex
import shutil
import asyncio
from pyrogram import Client, enums
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait,
    PeerIdInvalid,
    UserIsBlocked,
    InputUserDeactivated
)
from core.config import FSUB_CHANNEL, ADMIN_ID, WORK_DIR, LOG_CHANNEL_ID, logger
from core.client import bot, get_entity_id, safe_edit_text
from core.states import PROMPT_STATES, ACTIVE_TASKS, CACHED_USER_CLIENTS
from database.mongo import bot_users_col, sessions_col, user_chats_col
from database.repository import (
    record_bot_user,
    record_user_chat,
    delete_user_session,
    save_user_replace_rule,
    get_user_session,
    get_db_stats
)
from parsers.link import is_telegram_link_private
from services.session_service import verify_and_save_session
from services.batch_service import execute_batch_job
from ui.keyboards import get_add_buttons, get_fsub_markup, get_start_keyboard, send_clean_pm_notice
from ui.templates import welcome_template, pm_denied_template, fsub_denied_template, stats_template
from handlers.fsub import is_user_fsub_member

async def start_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)

    if message.chat.type == enums.ChatType.PRIVATE:
        try:
            await message.delete()
        except Exception:
            pass
        if not await is_user_fsub_member(client, user_id):
            fsub_text = fsub_denied_template()
            await send_clean_pm_notice(message.chat.id, fsub_text, reply_markup=get_fsub_markup())
            return
        notice_text = pm_denied_template()
        buttons = await get_add_buttons(user_id)
        await send_clean_pm_notice(message.chat.id, notice_text, reply_markup=buttons)
        return

    record_user_chat(user_id, message.chat)
    if not await is_user_fsub_member(client, user_id):
        fsub_text = fsub_denied_template(message.from_user.mention if message.from_user else 'User')
        await message.reply_text(fsub_text, reply_markup=get_fsub_markup())
        return

    welcome_text = welcome_template()
    keyboard = get_start_keyboard()
    await message.reply_text(welcome_text, reply_markup=keyboard)

async def add_session_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    try:
        await message.delete()
    except Exception:
        pass
    if not is_pm:
        record_user_chat(user_id, message.chat)
    if not await is_user_fsub_member(client, user_id):
        fsub_text = f"⚠️ You must join <b>@{FSUB_CHANNEL}</b> before using this bot."
        if is_pm:
            await send_clean_pm_notice(message.chat.id, fsub_text, reply_markup=get_fsub_markup())
        else:
            await message.reply_text(fsub_text, reply_markup=get_fsub_markup())
        return

    args = message.text.split(None, 1)
    if len(args) > 1:
        session_str = args[1].strip()
        await verify_and_save_session(message, user_id, session_str)
    else:
        PROMPT_STATES[user_id] = {"step": "AWAIT_SESSION", "timestamp": time.time()}
        prompt_text = "🔐 <b>Please send your Pyrogram string session:</b>\n\n<i>(Your message will be deleted instantly for privacy)</i>"
        if is_pm:
            await send_clean_pm_notice(message.chat.id, prompt_text)
        else:
            await message.reply_text(prompt_text)

async def replace_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    if is_pm:
        try:
            await message.delete()
        except Exception:
            pass
    else:
        record_user_chat(user_id, message.chat)
    if not await is_user_fsub_member(client, user_id):
        fsub_text = f"⚠️ You must join <b>@{FSUB_CHANNEL}</b> before using this bot."
        if is_pm:
            await send_clean_pm_notice(message.chat.id, fsub_text, reply_markup=get_fsub_markup())
        else:
            await message.reply_text(fsub_text, reply_markup=get_fsub_markup())
        return

    command_text = message.text.replace("/replace", "").strip()
    if command_text:
        try:
            parsed_args = shlex.split(command_text)
            if len(parsed_args) >= 2:
                old_word, new_word = parsed_args[0], parsed_args[1]
                save_user_replace_rule(user_id, old_word, new_word)
                resp_text = (
                    f"✅ <b>Replace Rule Saved!</b>\n\n"
                    f"🔄 <b>Old:</b> <code>{old_word}</code>\n"
                    f"➡️ <b>New:</b> <code>{new_word}</code>\n\n"
                    f"<i>Hyperlinks and URLs will also be cleaned automatically.</i>"
                )
                if is_pm:
                    buttons = await get_add_buttons(user_id)
                    await send_clean_pm_notice(message.chat.id, resp_text, reply_markup=buttons)
                else:
                    await message.reply_text(resp_text)
                return
        except Exception as e:
            logger.error(f"Replace rule parse error: {e}", exc_info=True)

    PROMPT_STATES[user_id] = {"step": "AWAIT_OLD_WORD", "timestamp": time.time()}
    prompt_text = (
        "🔀 <b>Word Replacement Setting</b>\n\n"
        "Send the word or phrase you want to <b>replace</b> (e.g. <code>desibotz</code> or <code>\"desi botz\"</code>):\n\n"
        "<i>(Send /cancel to abort)</i>"
    )
    if is_pm:
        await send_clean_pm_notice(message.chat.id, prompt_text)
    else:
        await message.reply_text(prompt_text)

async def del_session_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    if is_pm:
        try:
            await message.delete()
        except Exception:
            pass
    else:
        record_user_chat(user_id, message.chat)
    delete_user_session(user_id)
    resp_text = "✅ <b>Your saved session has been deleted successfully.</b>"
    if is_pm:
        buttons = await get_add_buttons(user_id)
        await send_clean_pm_notice(message.chat.id, resp_text, reply_markup=buttons)
    else:
        await message.reply_text(resp_text)

async def cancel_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    if is_pm:
        try:
            await message.delete()
        except Exception:
            pass
    else:
        record_user_chat(user_id, message.chat)
    cancelled_something = False
    if user_id in PROMPT_STATES:
        del PROMPT_STATES[user_id]
        cancelled_something = True
    if user_id in ACTIVE_TASKS:
        ACTIVE_TASKS[user_id].set()
        del ACTIVE_TASKS[user_id]
        cancelled_something = True
    resp_text = "🛑 <b>Current task or prompt cancelled.</b>" if cancelled_something else "ℹ️ <b>No active task or prompt found to cancel.</b>"
    if is_pm:
        buttons = await get_add_buttons(user_id)
        await send_clean_pm_notice(message.chat.id, resp_text, reply_markup=buttons)
    else:
        await message.reply_text(resp_text)

async def stats_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    if is_pm:
        try:
            await message.delete()
        except Exception:
            pass
    else:
        record_user_chat(user_id, message.chat)

    stats = get_db_stats()
    total_disk, used_disk, free_disk = shutil.disk_usage(WORK_DIR)
    total_gb = total_disk / (1024 ** 3)
    used_gb = used_disk / (1024 ** 3)
    free_gb = free_disk / (1024 ** 3)

    stats_text = stats_template(stats, total_gb, used_gb, free_gb, len(CACHED_USER_CLIENTS))
    if is_pm:
        buttons = await get_add_buttons(user_id)
        await send_clean_pm_notice(message.chat.id, stats_text, reply_markup=buttons)
    else:
        await message.reply_text(stats_text)

async def clear_disk_cmd(client: Client, message: Message):
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    if user_id != ADMIN_ID:
        return
    status = await message.reply_text("🧹 <b>Cleaning bot downloads folder & clearing disk cache...</b>")
    cleaned_count = 0
    freed_bytes = 0
    try:
        if os.path.exists(WORK_DIR):
            for file_name in os.listdir(WORK_DIR):
                file_path = os.path.join(WORK_DIR, file_name)
                try:
                    size = os.path.getsize(file_path) if os.path.isfile(file_path) else 0
                    if os.path.isfile(file_path) or os.path.islink(file_path):
                        os.unlink(file_path)
                    elif os.path.isdir(file_path):
                        shutil.rmtree(file_path)
                    cleaned_count += 1
                    freed_bytes += size
                except Exception as e:
                    logger.debug(f"Failed deleting {file_path}: {e}")
        gc.collect()
        total_disk, used_disk, free_disk = shutil.disk_usage(WORK_DIR)
        free_gb = free_disk / (1024 ** 3)
        freed_mb = freed_bytes / (1024 ** 2)
        await safe_edit_text(
            status,
            f"✅ <b>Downloads Folder Successfully Cleaned!</b>\n\n"
            f"🗑️ <b>Deleted Files:</b> <code>{cleaned_count}</code>\n"
            f"📦 <b>Freed Space:</b> <code>{freed_mb:.2f} MB</code>\n"
            f"🟢 <b>Available Disk Space:</b> <code>{free_gb:.2f} GB</code>"
        )
    except Exception as e:
        await safe_edit_text(status, f"❌ <b>Error cleaning folder:</b> <code>{str(e)}</code>")

async def broadcast_cmd(client: Client, message: Message):
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)
    if user_id != ADMIN_ID:
        return
    reply_msg = message.reply_to_message
    text_parts = message.text.split(maxsplit=1)
    broadcast_text = text_parts[1].strip() if len(text_parts) > 1 else None

    mode = "users"
    if broadcast_text and "-chats" in broadcast_text:
        mode = "chats"
        broadcast_text = broadcast_text.replace("-chats", "").strip()
    elif broadcast_text and "-all" in broadcast_text:
        mode = "all"
        broadcast_text = broadcast_text.replace("-all", "").strip()

    if not reply_msg and not broadcast_text:
        await message.reply_text(
            "📢 <b>Broadcast Command Guide</b>\n\n"
            "1. <b>Reply to any message</b> (photo, video, document, audio, text) with <code>/broadcast</code>\n"
            "2. Or directly send: <code>/broadcast &lt;your message&gt;</code>\n\n"
            "<b>🎯 Target Options:</b>\n"
            "• <code>/broadcast</code> (Default: All PM Users)\n"
            "• <code>/broadcast -chats</code> (All Connected Groups/Channels)\n"
            "• <code>/broadcast -all</code> (Both Users & Groups/Channels)"
        )
        return

    status_msg = await message.reply_text("⏳ <b>Fetching broadcast targets from database...</b>")

    target_ids = set()
    if mode in ["users", "all"]:
        for doc in bot_users_col.find():
            if doc.get("user_id") and doc["user_id"] > 0:
                target_ids.add(doc["user_id"])
        for doc in sessions_col.find():
            if doc.get("user_id") and doc["user_id"] > 0:
                target_ids.add(doc["user_id"])
        if ADMIN_ID:
            target_ids.add(ADMIN_ID)

    if mode in ["chats", "all"]:
        for doc in user_chats_col.find():
            if doc.get("chat_id"):
                target_ids.add(doc["chat_id"])

    targets = list(target_ids)
    total = len(targets)
    if total == 0:
        await safe_edit_text(status_msg, "⚠️ <b>No targets found to broadcast!</b>")
        return

    await safe_edit_text(status_msg, f"📢 <b>Broadcasting to {total} targets ({mode.upper()})...</b>")

    successful = 0
    blocked = 0
    failed = 0
    start_time = time.time()
    last_update = time.time()

    for idx, target_id in enumerate(targets, start=1):
        try:
            if reply_msg:
                await bot.copy_message(
                    chat_id=target_id,
                    from_chat_id=message.chat.id,
                    message_id=reply_msg.id
                )
            else:
                await bot.send_message(chat_id=target_id, text=broadcast_text)
            successful += 1
        except FloodWait as f:
            await asyncio.sleep(f.value + 1)
            try:
                if reply_msg:
                    await bot.copy_message(
                        chat_id=target_id,
                        from_chat_id=message.chat.id,
                        message_id=reply_msg.id
                    )
                else:
                    await bot.send_message(chat_id=target_id, text=broadcast_text)
                successful += 1
            except Exception:
                failed += 1
        except (UserIsBlocked, InputUserDeactivated):
            blocked += 1
            bot_users_col.delete_one({"user_id": target_id})
            sessions_col.delete_one({"user_id": target_id})
        except PeerIdInvalid:
            failed += 1
        except Exception:
            failed += 1

        if time.time() - last_update >= 4 or idx == total:
            last_update = time.time()
            pct = int((idx / total) * 100) if total > 0 else 100
            try:
                await safe_edit_text(
                    status_msg,
                    f"📢 <b>Broadcast in Progress...</b>\n\n"
                    f"👥 <b>Total Targets:</b> <code>{total}</code>\n"
                    f"✅ <b>Sent:</b> <code>{successful}</code>\n"
                    f"🚫 <b>Blocked:</b> <code>{blocked}</code>\n"
                    f"❌ <b>Failed:</b> <code>{failed}</code>\n"
                    f"⏳ <b>Progress:</b> <code>{pct}%</code> [{idx}/{total}]"
                )
            except Exception:
                pass

        await asyncio.sleep(0.04)

    elapsed = max(time.time() - start_time, 0.1)
    await safe_edit_text(
        status_msg,
        f"📢 <b>Broadcast Completed!</b>\n\n"
        f"🎯 <b>Total Targets:</b> <code>{total}</code>\n"
        f"✅ <b>Successfully Sent:</b> <code>{successful}</code>\n"
        f"🚫 <b>Blocked / Removed:</b> <code>{blocked}</code>\n"
        f"❌ <b>Failed / Invalid:</b> <code>{failed}</code>\n"
        f"⏱️ <b>Time Taken:</b> <code>{elapsed:.1f}s</code>"
    )

async def batch_cmd(client: Client, message: Message):
    if message.chat.username and message.chat.username.lower() == FSUB_CHANNEL.lower():
        return
    if LOG_CHANNEL_ID and message.chat.id == LOG_CHANNEL_ID:
        return
    is_pm = message.chat.type == enums.ChatType.PRIVATE
    user_id = get_entity_id(message)
    record_bot_user(message.from_user)

    if is_pm:
        try:
            await message.delete()
        except Exception:
            pass
        if not await is_user_fsub_member(client, user_id):
            await send_clean_pm_notice(message.chat.id, f"⚠️ You must join <b>@{FSUB_CHANNEL}</b> first.", reply_markup=get_fsub_markup())
            return
        notice_text = (
            "⚠️ <b>THIS BOT DOES NOT WORK IN PM!</b>\n\n"
            "Batch downloads only run inside <b>Groups</b> and <b>Channels</b>.\n\n"
            "Please add me to your Group or Channel using the buttons below, then use <code>/batch &lt;link&gt; &lt;count&gt;</code> there!"
        )
        buttons = await get_add_buttons(user_id)
        await send_clean_pm_notice(message.chat.id, notice_text, reply_markup=buttons)
        return

    record_user_chat(user_id, message.chat)
    if not await is_user_fsub_member(client, user_id):
        await message.reply_text(f"⚠️ You must join <b>@{FSUB_CHANNEL}</b> first.", reply_markup=get_fsub_markup())
        return

    args = message.text.split()[1:]
    if args:
        first_link = args[0]
        count = int(args[1]) if len(args) > 1 and args[1].isdigit() else 1
        count = max(count, 1)
        is_private = is_telegram_link_private(first_link)
        session_str = get_user_session(user_id)
        if is_private and not session_str:
            await message.reply_text("🔒 <b>Private Channel Link Detected!</b>\n\nPrivate posts require a connected Pyrogram session. Use /addsession first.")
            return
        await execute_batch_job(message, session_str, first_link, count)
    else:
        PROMPT_STATES[user_id] = {"step": "AWAIT_LINK", "chat_id": message.chat.id, "timestamp": time.time()}
        await message.reply_text(
            "📌 <b>Batch Download Setup</b>\n\n"
            "Please send the starting Telegram post link.\n"
            "<i>(Send /cancel to abort)</i>"
        )

