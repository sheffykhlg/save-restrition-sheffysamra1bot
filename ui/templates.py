from core.config import FSUB_CHANNEL

def welcome_template() -> str:
    return (
        "<b>⚡ NITRO CONTENT FORWARDER & DOWNLOADER</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Download and save restricted media, posts, and multi-file batches at maximum MTProto speeds!\n\n"
        "<b>📌 Quick Commands:</b>\n"
        "• 🔐 <code>/addsession</code> — Bind your Pyrogram String Session\n"
        "• 🔀 <code>/replace</code> — Set custom word/link replacement rules\n"
        "• 📦 <code>/batch</code> — Download batch range of posts\n"
        "• 🗑️ <code>/delsession</code> — Remove saved session string\n"
        "• 🛑 <code>/cancel</code> — Stop any active download or setup\n"
        "• 📊 <code>/stats</code> — System health & storage usage\n\n"
        "<i>💡 Simply send any public or private Telegram link to start!</i>"
    )

def pm_denied_template() -> str:
    return (
        "⚠️ <b>THIS BOT DOES NOT WORK IN PM!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "To download restricted content and protect your privacy, please add me to your <b>Group</b> or <b>Channel</b> as Admin using the buttons below.\n\n"
        "⚡ <i>All commands and high-speed multi-stream downloading run seamlessly inside your Group/Channel!</i>"
    )

def fsub_denied_template(mention: str = None) -> str:
    greeting = f"Hello {mention}!\n\n" if mention else ""
    return (
        "⛔ <b>ACCESS RESTRICTED — JOIN CHANNEL</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"{greeting}"
        f"You must join our official update channel <b>@{FSUB_CHANNEL}</b> to use this bot.\n\n"
        "👉 Join using the button below, then click <b>'🔄 Joined / Try Again'</b>."
    )

def session_success_pm_template(user_first_name: str) -> str:
    return (
        "✅ <b>SESSION CONNECTED SUCCESSFULLY!</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👤 <b>Account Name:</b> <code>{user_first_name}</code>\n"
        f"⚡ <b>Status:</b> <code>Active & Authenticated</code>\n\n"
        "⚠️ <b>Note:</b> This bot does not download in PM.\n"
        "Please add me to your <b>Group</b> or <b>Channel</b> using the buttons below to start downloading!"
    )

def session_success_group_template(user_first_name: str) -> str:
    return (
        f"✅ <b>Session Connected Successfully for {user_first_name}!</b>\n"
        "<i>(Your session string message was automatically deleted for privacy)</i>"
    )

def batch_summary_template(
    range_count: int,
    success_count: int,
    deleted_count: int,
    failed_count: int,
    time_str: str
) -> str:
    lines = [
        "📊 <b>BATCH PROCESS COMPLETED</b>",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━",
        f"🎯 <b>Total Requested:</b> <code>{range_count}</code>",
        f"✅ <b>Successfully Saved:</b> <code>{success_count}</code>"
    ]
    if deleted_count > 0:
        lines.append(f"🗑️ <b>Deleted on Telegram:</b> <code>{deleted_count}</code>")
    if failed_count > 0:
        lines.append(f"⚠️ <b>Failed / Errors:</b> <code>{failed_count}</code>")
    lines.append(f"⏱️ <b>Time Elapsed:</b> <code>{time_str}</code>")
    lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━")
    return "\n".join(lines)

def stats_template(stats: dict, total_gb: float, used_gb: float, free_gb: float, active_conns: int) -> str:
    return (
        "📊 <b>SYSTEM & DATABASE METRICS</b>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"👥 <b>Total Users:</b> <code>{stats.get('total_users', 0)}</code>\n"
        f"🔐 <b>Saved Sessions:</b> <code>{stats.get('total_sessions', 0)}</code>\n"
        f"📢 <b>Connected Chats:</b> <code>{stats.get('total_chats', 0)}</code>\n"
        f"⚡ <b>Active User Clients:</b> <code>{active_conns}</code>\n\n"
        "💾 <b>Storage Allocation:</b>\n"
        f"• <b>Total:</b> <code>{total_gb:.2f} GB</code>\n"
        f"• <b>Used:</b> <code>{used_gb:.2f} GB</code>\n"
        f"• <b>Free:</b> <code>{free_gb:.2f} GB</code>\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━"
    )

