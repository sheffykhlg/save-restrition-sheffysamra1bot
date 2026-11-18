from pyrogram import filters
from pyrogram.handlers import MessageHandler, CallbackQueryHandler, ChatMemberUpdatedHandler
from handlers.commands import (
    start_cmd,
    add_session_cmd,
    replace_cmd,
    del_session_cmd,
    cancel_cmd,
    stats_cmd,
    clear_disk_cmd,
    broadcast_cmd,
    batch_cmd
)
from handlers.callbacks import fsub_callback
from handlers.events import on_bot_chat_member_updated, on_new_chat_members
from handlers.listeners import text_and_batch_listener

COMMAND_EXCLUSIONS = [
    "start", "addsession", "replace", "delsession",
    "batch", "cancel", "forcecancel", "stats",
    "broadcast", "bcast", "clear", "cleandisk", "clean"
]

def register_all_handlers(app):
    # Command handlers
    app.add_handler(MessageHandler(start_cmd, filters.command("start")))
    app.add_handler(MessageHandler(add_session_cmd, filters.command("addsession")))
    app.add_handler(MessageHandler(replace_cmd, filters.command("replace")))
    app.add_handler(MessageHandler(del_session_cmd, filters.command("delsession")))
    app.add_handler(MessageHandler(cancel_cmd, filters.command(["cancel", "forcecancel"])))
    app.add_handler(MessageHandler(stats_cmd, filters.command("stats")))
    app.add_handler(MessageHandler(clear_disk_cmd, filters.command(["clear", "cleandisk", "clean"])))
    app.add_handler(MessageHandler(broadcast_cmd, filters.command(["broadcast", "bcast"])))
    app.add_handler(MessageHandler(batch_cmd, filters.command("batch")))

    # Callback Query handlers
    app.add_handler(CallbackQueryHandler(fsub_callback, filters.regex("^check_fsub$")))

    # Event handlers
    app.add_handler(ChatMemberUpdatedHandler(on_bot_chat_member_updated))
    app.add_handler(MessageHandler(on_new_chat_members, filters.new_chat_members))

    # General Text & Link listener
    app.add_handler(MessageHandler(
        text_and_batch_listener,
        filters.text & ~filters.command(COMMAND_EXCLUSIONS)
    ))

