import time
import asyncio
from pyrogram.types import Message
from pyrogram.errors import (
    AuthKeyDuplicated,
    AuthKeyUnregistered,
    UserDeactivated,
    SessionRevoked,
    Unauthorized
)
from core.config import logger
from core.client import (
    bot,
    get_or_create_user_client,
    get_entity_id,
    resolve_peer_safely,
    safe_delete_msg
)
from core.states import ACTIVE_TASKS
from database.mongo import batch_jobs_col
from database.repository import get_user_session
from parsers.link import parse_telegram_link
from engine.transfer import process_and_transfer_media
from engine.cleaner import cleanup_ram_and_disk
from ui.templates import batch_summary_template

async def execute_batch_job(
    target_msg: Message,
    session_str: str,
    start_link: str,
    range_count: int,
    resume_offset: int = 0,
    initial_counts: tuple = (0, 0, 0),
    job_id: str = None
):
    parsed = parse_telegram_link(start_link)
    if not parsed:
        await target_msg.reply_text("❌ <b>Invalid Telegram link format.</b>")
        return

    chat_identifier, topic_id, start_message_id, is_private = parsed
    user_id = get_entity_id(target_msg)
    cancel_event = asyncio.Event()
    ACTIVE_TASKS[user_id] = cancel_event

    user_app = None
    if session_str:
        try:
            user_app = await get_or_create_user_client(user_id, session_str)
        except (AuthKeyDuplicated, AuthKeyUnregistered, UserDeactivated, SessionRevoked, Unauthorized):
            if is_private:
                await target_msg.reply_text("❌ <b>Session Expired or Logged Out:</b> Your session was terminated on another device or revoked. Please add a fresh session using /addsession.")
                return
            else:
                user_app = None
        except Exception as e:
            if is_private:
                await target_msg.reply_text(f"❌ <b>Connection Failed:</b> <code>{str(e)}</code>")
                return
            else:
                user_app = None

    if is_private and not user_app:
        await target_msg.reply_text("🔒 <b>Private channel links require a valid Pyrogram session. Use /addsession first.</b>")
        return

    client_app = user_app if user_app else bot
    success_count, deleted_count, failed_count = initial_counts
    batch_start_time = time.time()

    if not job_id and range_count > 1:
        job_id = f"{user_id}_{chat_identifier}_{start_message_id}"

    if range_count > 1 and job_id:
        batch_jobs_col.update_one(
            {"_id": job_id},
            {"$set": {
                "user_id": user_id,
                "target_chat_id": target_msg.chat.id,
                "start_link": start_link,
                "chat_identifier": str(chat_identifier),
                "start_message_id": start_message_id,
                "range_count": range_count,
                "current_offset": resume_offset,
                "topic_id": topic_id,
                "status": "RUNNING",
                "success_count": success_count,
                "deleted_count": deleted_count,
                "failed_count": failed_count,
                "updated_at": time.time()
            }},
            upsert=True
        )

    try:
        for i in range(resume_offset, range_count):
            if cancel_event.is_set():
                break
            current_msg_id = start_message_id + i
            if range_count > 1:
                status_msg = await target_msg.reply_text(f"⏳ <b>Downloading [{i+1}/{range_count}] (ID: {current_msg_id})...</b>")
            else:
                status_msg = await target_msg.reply_text("⏳ <b>Processing post...</b>")

            try:
                res = await process_and_transfer_media(
                    user_app=client_app,
                    source_chat_id=chat_identifier,
                    message_id=current_msg_id,
                    status_msg=status_msg,
                    target_msg=target_msg,
                    cancel_event=cancel_event,
                    topic_id=topic_id,
                    is_public=(not is_private)
                )
                if res == "AUTH_ERROR":
                    break
                elif res == "SUCCESS" or res is True:
                    success_count += 1
                elif res == "DELETED":
                    deleted_count += 1
                    if range_count == 1:
                        await target_msg.reply_text("⚠️ <b>This post has been deleted from Telegram.</b>")
                else:
                    failed_count += 1
                    if range_count == 1:
                        await target_msg.reply_text(f"⚠️ <b>Failed to process post (ID: {current_msg_id}).</b>")
            except asyncio.CancelledError:
                await safe_delete_msg(status_msg)
                if range_count > 1:
                    await target_msg.reply_text("🛑 <b>Batch download cancelled.</b>")
                break
            except Exception as e:
                logger.error(f"Error processing item {i} (MSG ID: {current_msg_id}): {e}", exc_info=True)
                await safe_delete_msg(status_msg)
                failed_count += 1

            if range_count > 1 and job_id:
                batch_jobs_col.update_one(
                    {"_id": job_id},
                    {"$set": {
                        "current_offset": i + 1,
                        "success_count": success_count,
                        "deleted_count": deleted_count,
                        "failed_count": failed_count,
                        "updated_at": time.time()
                    }}
                )

            if range_count > 1:
                # 0.3s interval per SPEED_ENGINE_LOCKED.md
                await asyncio.sleep(0.3)

        if range_count > 1:
            total_time = max(time.time() - batch_start_time, 0.1)
            m, s = divmod(int(total_time), 60)
            time_str = f"{m}m {s}s" if m > 0 else f"{s}s"
            summary_card = batch_summary_template(range_count, success_count, deleted_count, failed_count, time_str)
            await target_msg.reply_text(summary_card)

    finally:
        if range_count > 1 and job_id:
            batch_jobs_col.delete_one({"_id": job_id})
        if user_id in ACTIVE_TASKS:
            del ACTIVE_TASKS[user_id]
        cleanup_ram_and_disk(force_all=False)

async def resume_all_pending_batch_jobs():
    """
    Auto-Resumes interrupted batch jobs on bot restart across 100+ users.
    Throttled via asyncio.Semaphore(2) and safe interval to avoid FloodWait.
    """
    await asyncio.sleep(6)
    try:
        pending_jobs = list(batch_jobs_col.find({"status": "RUNNING"}))
    except Exception as e:
        logger.error(f"Error querying pending batch jobs: {e}")
        return

    if not pending_jobs:
        return

    logger.info(f"🔄 Auto-Resume: Found {len(pending_jobs)} unfinished batch jobs.")
    resume_semaphore = asyncio.Semaphore(2)

    async def _worker(job):
        async with resume_semaphore:
            job_id = job.get("_id")
            try:
                user_id = job.get("user_id")
                target_chat_id = job.get("target_chat_id")
                start_link = job.get("start_link")
                range_count = job.get("range_count", 1)
                current_offset = job.get("current_offset", 0)
                initial_counts = (
                    job.get("success_count", 0),
                    job.get("deleted_count", 0),
                    job.get("failed_count", 0)
                )

                if time.time() - job.get("updated_at", 0) > 172800 or current_offset >= range_count:
                    batch_jobs_col.delete_one({"_id": job_id})
                    return

                start_msg_id = job.get("start_message_id", 0)
                next_id = start_msg_id + current_offset

                try:
                    await resolve_peer_safely(target_chat_id)
                    notice_msg = await bot.send_message(
                        chat_id=target_chat_id,
                        text=(
                            f"🔄 <b>Server Restart Recovery Active</b>\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"⚡ Resuming batch download from item <code>[{current_offset + 1}/{range_count}]</code> (ID: <code>{next_id}</code>)...\n"
                            f"<i>(Continuing automatically without losing previous progress)</i>"
                        )
                    )
                except Exception as e_notify:
                    logger.warning(f"Could not send resume notice to {target_chat_id}: {e_notify}")
                    batch_jobs_col.delete_one({"_id": job_id})
                    return

                session_str = get_user_session(user_id)
                await execute_batch_job(
                    target_msg=notice_msg,
                    session_str=session_str,
                    start_link=start_link,
                    range_count=range_count,
                    resume_offset=current_offset,
                    initial_counts=initial_counts,
                    job_id=job_id
                )
            except Exception as e_proc:
                logger.error(f"Error processing resumed job {job_id}: {e_proc}", exc_info=True)
                batch_jobs_col.delete_one({"_id": job_id})

    for job in pending_jobs:
        asyncio.create_task(_worker(job))
        await asyncio.sleep(3)

