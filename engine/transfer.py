import os
import re
import math
import time
import shutil
import asyncio
from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import (
    FloodWait,
    PeerIdInvalid,
    EntityBoundsInvalid,
    AuthKeyDuplicated,
    AuthKeyUnregistered,
    UserDeactivated,
    SessionRevoked,
    Unauthorized
)
from core.config import WORK_DIR, LOG_CHANNEL_ID, logger
from core.client import bot, resolve_peer_safely, safe_edit_text, safe_delete_msg, get_entity_id
from core.states import CACHED_USER_CLIENTS
from database.repository import delete_user_session
from parsers.caption import process_caption_and_entities
from engine.cleaner import cleanup_message_files, get_video_metadata
from engine.progress import ProgressTracker

# =====================================================================
# ⛔ [LOCKED ARCHITECTURE] SPEED ENGINE & MULTI-STREAM PIPELINE
# DO NOT MODIFY, REFACTOR, OR REMOVE THESE FUNCTIONS OR CLIENT CONFIGS!
# SEE SPEED_ENGINE_LOCKED.md FOR DETAILED SPECIFICATIONS.
# =====================================================================

def get_media_target_path(msg: Message, message_id: int) -> str:
    media = msg.video or msg.document or msg.audio or msg.photo or msg.voice or msg.sticker or msg.video_note or msg.animation
    media_file_name = getattr(media, "file_name", None)
    if media_file_name:
        safe_name = os.path.basename(media_file_name)
        safe_name = re.sub(r'[^\w\s.-]', '_', safe_name).strip()
        if not safe_name:
            safe_name = "file"
        return os.path.abspath(os.path.join(WORK_DIR, f"{message_id}_{safe_name}"))
    ext = ".bin"
    if msg.video:
        ext = ".mp4"
    elif msg.audio:
        ext = ".mp3"
    elif msg.animation:
        ext = ".mp4"
    elif msg.voice:
        ext = ".ogg"
    elif msg.video_note:
        ext = ".mp4"
    elif msg.photo:
        ext = ".jpg"
    elif msg.document:
        mime = getattr(msg.document, "mime_type", "")
        if "pdf" in mime:
            ext = ".pdf"
        elif "zip" in mime:
            ext = ".zip"
        else:
            ext = ".bin"
    return os.path.abspath(os.path.join(WORK_DIR, f"{message_id}_{ext}"))

async def log_transfer_to_channel(
    user_msg: Message,
    media_type: str,
    file_path: str,
    dl_speed: float,
    ul_speed: float,
    total_time: float,
    source_chat_id,
    message_id,
    thumb_path=None,
    duration=0,
    width=0,
    height=0
):
    if not LOG_CHANNEL_ID:
        return
    try:
        await resolve_peer_safely(LOG_CHANNEL_ID)
        user = user_msg.from_user
        user_name = user.first_name if user else "Unknown User"
        user_username = f"@{user.username}" if user and user.username else "No Username"
        user_id = user.id if user else user_msg.chat.id
        file_name = os.path.basename(file_path) if file_path else "Text Message"
        file_size_mb = (os.path.getsize(file_path) / (1024 * 1024)) if file_path and os.path.exists(file_path) else 0.0

        log_caption = (
            f"📥 <b>NEW MEDIA TRANSFERRED</b>\n\n"
            f"👤 <b>User:</b> {user_name} ({user_username})\n"
            f"🆔 <b>User ID:</b> <code>{user_id}</code>\n"
            f"📁 <b>File Name:</b> <code>{file_name}</code> (<code>{file_size_mb:.2f} MB</code>)\n"
            f"🎯 <b>Type:</b> <code>{media_type.upper()}</code>\n"
            f"🔗 <b>Msg Link/ID:</b> <code>{source_chat_id}</code> / <code>{message_id}</code>\n\n"
            f"⚡ <b>TRANSFER METRICS:</b>\n"
            f"🚀 <b>Download Speed:</b> <code>{dl_speed:.2f} MB/s</code>\n"
            f"📤 <b>Upload Speed:</b> <code>{ul_speed:.2f} MB/s</code>\n"
            f"⏱️ <b>Time Taken:</b> <code>{total_time:.2f}s</code>"
        )
        try:
            if file_path and os.path.exists(file_path):
                if media_type == "video":
                    await bot.send_video(
                        LOG_CHANNEL_ID,
                        video=file_path,
                        caption=log_caption,
                        duration=duration,
                        width=width,
                        height=height,
                        thumb=thumb_path,
                        supports_streaming=True
                    )
                elif media_type == "photo":
                    await bot.send_photo(LOG_CHANNEL_ID, photo=file_path, caption=log_caption)
                elif media_type == "document":
                    await bot.send_document(LOG_CHANNEL_ID, document=file_path, caption=log_caption, thumb=thumb_path)
                elif media_type == "audio":
                    await bot.send_audio(LOG_CHANNEL_ID, audio=file_path, caption=log_caption, duration=duration, thumb=thumb_path)
                elif media_type == "voice":
                    await bot.send_voice(LOG_CHANNEL_ID, voice=file_path, caption=log_caption, duration=duration)
                else:
                    await bot.send_message(LOG_CHANNEL_ID, text=log_caption)
            else:
                await bot.send_message(LOG_CHANNEL_ID, text=log_caption)
        except Exception as e_send_media:
            logger.warning(f"Failed sending media to log channel ({e_send_media}), sending text log...")
            await bot.send_message(LOG_CHANNEL_ID, text=log_caption)
    except Exception as e:
        logger.error(f"Failed logging transfer to log channel: {e}", exc_info=True)

# =====================================================================
# ⛔ [LOCKED ARCHITECTURE] FAST PARALLEL MULTI-STREAM CHUNK DOWNLOADER
# DO NOT TOUCH OR DOWNGRADE: Saturation of Telegram MTProto DC bandwidth
# via 6 concurrent streams + in-place sparse writes.
# =====================================================================
async def fast_parallel_download(
    client: Client,
    msg: Message,
    target_path: str,
    progress_callback=None,
    progress_args=(),
    cancel_event=None
) -> str:
    is_parallel_supported = bool(msg.video or msg.document or msg.audio or msg.animation or msg.voice or msg.video_note)
    media = msg.video or msg.document or msg.audio or msg.photo or msg.voice or msg.sticker or msg.video_note or msg.animation
    if not media:
        raise ValueError("No downloadable media found in message")
    file_size = getattr(media, "file_size", 0) or 0
    chunk_size = 1024 * 1024
    total_chunks = max(1, math.ceil(file_size / chunk_size))

    if not is_parallel_supported or file_size < 10 * 1024 * 1024 or total_chunks <= 4:
        return await client.download_media(
            msg,
            file_name=target_path,
            progress=progress_callback,
            progress_args=progress_args
        )

    num_workers = min(6, total_chunks)
    chunk_slice = math.ceil(total_chunks / num_workers)
    os.makedirs(os.path.dirname(os.path.abspath(target_path)), exist_ok=True)
    temp_path = f"{target_path}.turbo"
    with open(temp_path, "wb") as f_init:
        f_init.truncate(file_size)

    file_handle = open(temp_path, "r+b")
    write_lock = asyncio.Lock()
    downloaded_bytes = [0]

    async def worker(offset, limit):
        if limit <= 0:
            return
        current_offset_bytes = offset * chunk_size
        async for chunk in client.stream_media(msg, offset=offset, limit=limit):
            if cancel_event and cancel_event.is_set():
                raise asyncio.CancelledError("Download cancelled.")
            chunk_len = len(chunk)
            async with write_lock:
                file_handle.seek(current_offset_bytes)
                file_handle.write(chunk)
                downloaded_bytes[0] += chunk_len
                current_total = downloaded_bytes[0]
            current_offset_bytes += chunk_len
            if progress_callback:
                try:
                    await progress_callback(current_total, file_size, *progress_args)
                except Exception:
                    pass

    tasks = []
    try:
        for i in range(num_workers):
            offset = i * chunk_slice
            if offset >= total_chunks:
                break
            limit = min(chunk_slice, total_chunks - offset)
            tasks.append(asyncio.create_task(worker(offset, limit)))
        await asyncio.gather(*tasks)
    except Exception as e:
        for t in tasks:
            if not t.done():
                t.cancel()
        file_handle.close()
        if os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except Exception:
                pass
        raise e
    finally:
        try:
            file_handle.close()
        except Exception:
            pass

    if os.path.exists(target_path):
        try:
            os.remove(target_path)
        except Exception:
            pass
    if os.path.exists(temp_path):
        shutil.move(temp_path, target_path)
    else:
        raise FileNotFoundError(f"Turbo download file not found: {temp_path}")
    return target_path

async def process_and_transfer_media(
    user_app,
    source_chat_id,
    message_id,
    status_msg,
    target_msg: Message,
    cancel_event,
    topic_id=None,
    is_public=False
):
    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError("Process force cancelled.")

    user_id = get_entity_id(target_msg)
    target_chat_id = target_msg.chat.id
    await resolve_peer_safely(target_chat_id)

    download_path = None
    thumb_path = None
    msg = None
    fetch_client = user_app if user_app else bot
    attempt = 0
    auth_failed = False

    while attempt < 3:
        try:
            msg = await fetch_client.get_messages(source_chat_id, message_id)
            break
        except FloodWait as f:
            await asyncio.sleep(f.value + 1)
        except (AuthKeyUnregistered, AuthKeyDuplicated, UserDeactivated, SessionRevoked, Unauthorized) as auth_err:
            logger.warning(f"Session revoked/logged out for user {user_id}: {auth_err}")
            delete_user_session(user_id)
            CACHED_USER_CLIENTS.pop(user_id, None)
            auth_failed = True
            if is_public:
                logger.info("Public channel: switching to bot client to fetch message...")
                fetch_client = bot
                user_app = bot
                attempt += 1
                continue
            else:
                break
        except Exception as e:
            logger.error(f"Error fetching message ID {message_id}: {e}")
            if is_public and fetch_client != bot:
                logger.info("Public channel error with user client, switching to bot...")
                fetch_client = bot
                user_app = bot
                attempt += 1
                continue
            attempt += 1
            if attempt >= 3:
                break
            await asyncio.sleep(1)

    if auth_failed and not is_public:
        await safe_delete_msg(status_msg)
        await target_msg.reply_text("❌ <b>Session Expired or Logged Out:</b> Your session was terminated on another device or revoked. Please add a fresh session using /addsession.")
        return "AUTH_ERROR"

    if msg is None:
        logger.warning(f"Message ID {message_id} fetch failed after retries.")
        await safe_delete_msg(status_msg)
        return False

    if getattr(msg, "empty", False) or getattr(msg, "service", False):
        await safe_delete_msg(status_msg)
        return "DELETED"

    if topic_id and getattr(msg, "message_thread_id", None) and msg.message_thread_id != topic_id:
        await safe_delete_msg(status_msg)
        return "DELETED"

    raw_caption = msg.caption or ""
    caption, caption_entities = await process_caption_and_entities(raw_caption, msg.caption_entities, user_id)

    reply_to_message_id = None
    if getattr(target_msg, "reply_to_message", None):
        reply_to_message_id = target_msg.reply_to_message.id
    elif getattr(target_msg, "is_topic_message", False):
        reply_to_message_id = target_msg.message_thread_id

    # ⚡ [INSTANT SERVER-SIDE COPY FOR PUBLIC CHANNELS]
    if is_public or isinstance(source_chat_id, str):
        try:
            copy_start = time.time()
            copied = None
            try:
                copied = await bot.copy_message(
                    chat_id=target_chat_id,
                    from_chat_id=source_chat_id,
                    message_id=message_id,
                    caption=caption if caption else None,
                    caption_entities=caption_entities if caption else None,
                    reply_to_message_id=reply_to_message_id
                )
            except Exception as e_copy_ent:
                logger.warning(f"copy_message with custom entities failed ({e_copy_ent}), retrying original copy...")
                copied = await bot.copy_message(
                    chat_id=target_chat_id,
                    from_chat_id=source_chat_id,
                    message_id=message_id,
                    caption=None,
                    reply_to_message_id=reply_to_message_id
                )
            if copied:
                await safe_delete_msg(status_msg)
                total_elapsed = max(time.time() - copy_start, 0.05)
                await log_transfer_to_channel(
                    target_msg,
                    "copy (instant)",
                    "",
                    999.0,
                    999.0,
                    total_elapsed,
                    source_chat_id,
                    message_id
                )
                return True
        except Exception as e_copy:
            logger.info(f"Direct copy_message not possible ({e_copy}), falling back to direct stream/download...")

    # Text message handling
    if (msg.text or (not msg.media and getattr(msg, "caption", None))) and not msg.media:
        raw_text = msg.text or msg.caption or ""
        raw_entities = msg.entities or msg.caption_entities
        cleaned_text, cleaned_entities = await process_caption_and_entities(raw_text, raw_entities, user_id)
        try:
            await safe_delete_msg(status_msg)
            try:
                await bot.send_message(
                    chat_id=target_chat_id,
                    text=cleaned_text if cleaned_text.strip() else (raw_text if raw_text.strip() else "​"),
                    entities=cleaned_entities,
                    reply_to_message_id=reply_to_message_id
                )
            except Exception as e_send_ent:
                logger.warning(f"send_message with entities failed ({e_send_ent}), sending plain text...")
                await bot.send_message(
                    chat_id=target_chat_id,
                    text=cleaned_text if cleaned_text.strip() else (raw_text if raw_text.strip() else "​"),
                    parse_mode=None,
                    reply_to_message_id=reply_to_message_id
                )
            await log_transfer_to_channel(target_msg, "text", "", 0, 0, 0, source_chat_id, message_id)
            return True
        except Exception as e:
            logger.error(f"Failed to send text message {message_id}: {e}", exc_info=True)
            await safe_edit_text(status_msg, f"⚠️ <b>Failed to send text message {message_id}:</b> {str(e)}")
            return False

    media = msg.video or msg.document or msg.audio or msg.photo or msg.voice or msg.sticker or msg.video_note or msg.animation
    if not media:
        await safe_delete_msg(status_msg)
        return False

    # Download thumbnail if present
    try:
        if getattr(msg, "video", None) and msg.video.thumbs:
            thumb_path = await user_app.download_media(msg.video.thumbs[0].file_id, file_name=f"{WORK_DIR}/thumb_{message_id}.jpg")
        elif getattr(msg, "document", None) and msg.document.thumbs:
            thumb_path = await user_app.download_media(msg.document.thumbs[0].file_id, file_name=f"{WORK_DIR}/thumb_{message_id}.jpg")
        elif getattr(msg, "audio", None) and msg.audio.thumbs:
            thumb_path = await user_app.download_media(msg.audio.thumbs[0].file_id, file_name=f"{WORK_DIR}/thumb_{message_id}.jpg")
    except Exception as e:
        logger.error(f"Thumbnail download failed: {e}", exc_info=True)

    dl_tracker = ProgressTracker()
    download_success = False
    overall_start_time = time.time()
    attempt = 0
    target_file_path = get_media_target_path(msg, message_id)

    while attempt < 3:
        try:
            start_time = time.time()
            try:
                download_path = await fast_parallel_download(
                    client=user_app,
                    msg=msg,
                    target_path=target_file_path,
                    progress_callback=dl_tracker.callback,
                    progress_args=(status_msg, f"DOWNLOADING [{message_id}]", start_time, cancel_event),
                    cancel_event=cancel_event
                )
            except asyncio.CancelledError:
                raise
            except Exception as e_fast:
                logger.warning(f"Fast turbo download fallback ({e_fast}), trying standard download_media...")
                if os.path.exists(f"{target_file_path}.turbo"):
                    try:
                        os.remove(f"{target_file_path}.turbo")
                    except Exception:
                        pass
                fallback_target = os.path.abspath(os.path.join(WORK_DIR, f"{message_id}_"))
                download_path = await user_app.download_media(
                    msg,
                    file_name=fallback_target,
                    progress=dl_tracker.callback,
                    progress_args=(status_msg, f"DOWNLOADING [{message_id}]", start_time, cancel_event)
                )

            if download_path and os.path.exists(download_path):
                download_success = True
                break
        except FloodWait as f:
            await asyncio.sleep(f.value + 1)
        except Exception as e:
            logger.error(f"Download attempt {attempt+1} failed for {message_id}: {e}", exc_info=True)
            attempt += 1
            if attempt == 3:
                await safe_delete_msg(status_msg)
                return False
            await asyncio.sleep(2)

    if not download_success or not download_path:
        await safe_delete_msg(status_msg)
        return False

    if msg.photo and download_path and not download_path.lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
        new_path = f"{download_path}.jpg"
        os.rename(download_path, new_path)
        download_path = new_path

    if cancel_event and cancel_event.is_set():
        raise asyncio.CancelledError("Process force cancelled.")

    duration = getattr(media, "duration", 0) or 0
    width = getattr(media, "width", 0) or 0
    height = getattr(media, "height", 0) or 0

    if msg.video and (duration == 0 or width == 0 or height == 0):
        extracted_duration, extracted_width, extracted_height = get_video_metadata(download_path)
        duration = duration or extracted_duration
        width = width or extracted_width
        height = height or extracted_height

    ul_tracker = ProgressTracker()
    media_type_str = "file"

    try:
        start_time = time.time()

        async def send_with_fallback(send_func, **kwargs):
            try:
                return await send_func(**kwargs)
            except (PeerIdInvalid, EntityBoundsInvalid):
                logger.warning(f"Entity error caught for msg {message_id}. Retrying without caption_entities.")
                kwargs.pop("caption_entities", None)
                return await send_func(**kwargs)
            except Exception as e_send:
                err_str = str(e_send).upper()
                if "ENTITY_BOUNDS_INVALID" in err_str or "PEER_ID_INVALID" in err_str or "ENTITY" in err_str:
                    logger.warning(f"Entity error ({e_send}) caught for msg {message_id}. Retrying without caption_entities.")
                    kwargs.pop("caption_entities", None)
                    return await send_func(**kwargs)
                if "MEDIA_CAPTION_TOO_LONG" in err_str:
                    logger.warning(f"Caption too long for msg {message_id}. Truncating to 1024 characters.")
                    cap = kwargs.get("caption", "")
                    kwargs["caption"] = cap[:1024]
                    kwargs.pop("caption_entities", None)
                    return await send_func(**kwargs)
                if "caption" in kwargs:
                    logger.warning(f"Sending media without caption due to ({e_send}), will send caption separately...")
                    orig_caption = kwargs.pop("caption", "")
                    kwargs.pop("caption_entities", None)
                    sent_media = await send_func(**kwargs)
                    if sent_media and orig_caption:
                        try:
                            await bot.send_message(
                                chat_id=target_chat_id,
                                text=orig_caption,
                                parse_mode=None,
                                reply_to_message_id=reply_to_message_id
                            )
                        except Exception as e_cap_send:
                            logger.error(f"Failed to send separate caption: {e_cap_send}")
                    return sent_media
                raise e_send

        if msg.video:
            media_type_str = "video"
            await send_with_fallback(
                bot.send_video,
                chat_id=target_chat_id,
                video=download_path,
                caption=caption,
                caption_entities=caption_entities,
                duration=duration,
                width=width,
                height=height,
                thumb=thumb_path,
                supports_streaming=True,
                reply_to_message_id=reply_to_message_id,
                progress=ul_tracker.callback,
                progress_args=(status_msg, f"UPLOADING [{message_id}]", start_time, cancel_event)
            )
        elif msg.photo:
            media_type_str = "photo"
            await send_with_fallback(
                bot.send_photo,
                chat_id=target_chat_id,
                photo=download_path,
                caption=caption,
                caption_entities=caption_entities,
                reply_to_message_id=reply_to_message_id,
                progress=ul_tracker.callback,
                progress_args=(status_msg, f"UPLOADING [{message_id}]", start_time, cancel_event)
            )
        elif msg.document:
            media_type_str = "document"
            await send_with_fallback(
                bot.send_document,
                chat_id=target_chat_id,
                document=download_path,
                caption=caption,
                caption_entities=caption_entities,
                thumb=thumb_path,
                reply_to_message_id=reply_to_message_id,
                progress=ul_tracker.callback,
                progress_args=(status_msg, f"UPLOADING [{message_id}]", start_time, cancel_event)
            )
        elif msg.audio:
            media_type_str = "audio"
            await send_with_fallback(
                bot.send_audio,
                chat_id=target_chat_id,
                audio=download_path,
                caption=caption,
                caption_entities=caption_entities,
                duration=duration,
                performer=getattr(msg.audio, "performer", ""),
                title=getattr(msg.audio, "title", ""),
                thumb=thumb_path,
                reply_to_message_id=reply_to_message_id,
                progress=ul_tracker.callback,
                progress_args=(status_msg, f"UPLOADING [{message_id}]", start_time, cancel_event)
            )
        elif msg.voice:
            media_type_str = "voice"
            await send_with_fallback(
                bot.send_voice,
                chat_id=target_chat_id,
                voice=download_path,
                caption=caption,
                caption_entities=caption_entities,
                duration=duration,
                reply_to_message_id=reply_to_message_id,
                progress=ul_tracker.callback,
                progress_args=(status_msg, f"UPLOADING [{message_id}]", start_time, cancel_event)
            )
        elif msg.video_note:
            media_type_str = "video_note"
            await bot.send_video_note(
                chat_id=target_chat_id,
                video_note=download_path,
                duration=duration,
                thumb=thumb_path,
                reply_to_message_id=reply_to_message_id,
                progress=ul_tracker.callback,
                progress_args=(status_msg, f"UPLOADING [{message_id}]", start_time, cancel_event)
            )
        elif msg.sticker:
            media_type_str = "sticker"
            await bot.send_sticker(
                chat_id=target_chat_id,
                sticker=download_path,
                reply_to_message_id=reply_to_message_id
            )
        elif msg.animation:
            media_type_str = "animation"
            await send_with_fallback(
                bot.send_animation,
                chat_id=target_chat_id,
                animation=download_path,
                caption=caption,
                caption_entities=caption_entities,
                reply_to_message_id=reply_to_message_id
            )

        total_elapsed = time.time() - overall_start_time
        await log_transfer_to_channel(
            target_msg,
            media_type_str,
            download_path,
            dl_tracker.peak_speed,
            ul_tracker.peak_speed,
            total_elapsed,
            source_chat_id,
            message_id,
            thumb_path=thumb_path,
            duration=duration,
            width=width,
            height=height
        )
        await safe_delete_msg(status_msg)
        return True
    except Exception as e:
        logger.error(f"Upload execution failed for {message_id}: {e}", exc_info=True)
        await safe_edit_text(status_msg, f"⚠️ <b>Failed to upload message {message_id}:</b> {str(e)}")
        return False
    finally:
        cleanup_message_files(message_id, download_path, thumb_path)

