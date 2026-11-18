import asyncio
from pyrogram.types import BotCommand
from core.config import LOG_GROUP_ID, logger, encrypt_session, start_aria2_daemon
from core.client import bot, resolve_peer_safely
from database.mongo import bot_meta_col
from engine.cleaner import cleanup_ram_and_disk
from services.batch_service import resume_all_pending_batch_jobs
from handlers import register_all_handlers

# Start high-speed Aria2c daemon
start_aria2_daemon()

# Register all bot handlers
register_all_handlers(bot)

async def main():
    # Initial disk & memory purge on startup
    cleanup_ram_and_disk(force_all=True)

    # Start main bot client
    await bot.start()

    # Cache bot session string to database and local disk
    try:
        exported_str = await bot.export_session_string()
        if exported_str:
            bot_meta_col.update_one(
                {"_id": "main_bot_session"},
                {"$set": {"session_string": encrypt_session(exported_str)}},
                upsert=True
            )
            try:
                with open(".botsession", "w", encoding="utf-8") as f:
                    f.write(exported_str)
            except Exception:
                pass
    except Exception as e:
        logger.warning(f"Failed to cache bot session: {e}")

    # Set Telegram bot command menu
    await bot.set_bot_commands([
        BotCommand("start", "🚀 Start the bot & guide"),
        BotCommand("addsession", "🔐 Bind Pyrogram String Session"),
        BotCommand("replace", "🔀 Set word replace & link filter"),
        BotCommand("delsession", "🗑️ Delete saved session"),
        BotCommand("batch", "📦 Download range of messages"),
        BotCommand("cancel", "🛑 Cancel ongoing task or prompt"),
        BotCommand("stats", "📊 Check database & system storage"),
        BotCommand("broadcast", "📢 Broadcast announcement (Admin only)"),
        BotCommand("clear", "🧹 Empty bot downloads & clear disk (Admin only)")
    ])

    # Send restart alert to admin log group if configured
    if LOG_GROUP_ID:
        try:
            await resolve_peer_safely(LOG_GROUP_ID)
            await bot.send_message(LOG_GROUP_ID, "🔄 <b>Service Restarted: High-Speed Engine Online</b>")
            logger.info("Sent restart service message to group successfully.")
        except Exception as e:
            logger.warning(f"Could not send restart alert to log group: {e}")

    logger.info("🚀 ARIA2 HIGH SPEED BOT ONLINE & READY!")

    # Auto-resume any interrupted jobs from previous run
    asyncio.create_task(resume_all_pending_batch_jobs())

    # Keep bot running indefinitely
    await asyncio.Event().wait()

if __name__ == "__main__":
    try:
        import uvloop
        uvloop.install()
    except Exception:
        pass

    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    loop.run_until_complete(main())
