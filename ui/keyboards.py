from pyrogram import enums
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from core.config import FSUB_CHANNEL, logger
from core.client import bot
from core.states import LAST_PM_NOTICES
from database.mongo import user_chats_col

async def get_add_buttons(user_id: int = None) -> InlineKeyboardMarkup:
    username = bot.me.username if getattr(bot, "me", None) and bot.me.username else ""
    admin_rights = "change_info+post_messages+edit_messages+delete_messages+restrict_members+invite_users+pin_messages+promote_members"
    group_url = f"https://t.me/{username}?startgroup=true&admin={admin_rights}"
    channel_url = f"https://t.me/{username}?startchannel=true&admin={admin_rights}"
    keyboard = []
    if user_id:
        try:
            cursor = user_chats_col.find({"user_id": user_id}).sort("updated_at", -1).limit(4)
            for c in cursor:
                link = c.get("link")
                if not link:
                    try:
                        link = await bot.export_chat_invite_link(c["chat_id"])
                        user_chats_col.update_one({"_id": c["_id"]}, {"$set": {"link": link}})
                    except Exception:
                        pass
                if link:
                    icon = "📢" if c.get("type") == "Channel" else "👥"
                    title = c.get("title", "Chat")
                    keyboard.append([InlineKeyboardButton(f"{icon} {title[:25]}", url=link)])
        except Exception as e:
            logger.warning(f"Error fetching user chats for dynamic buttons: {e}")

    keyboard.append([
        InlineKeyboardButton("➕ Add to Group", url=group_url),
        InlineKeyboardButton("📢 Add to Channel", url=channel_url)
    ])
    keyboard.append([
        InlineKeyboardButton("🤖 Support Channel", url=f"https://t.me/{FSUB_CHANNEL or 'desibotz'}")
    ])
    return InlineKeyboardMarkup(keyboard)

def get_fsub_markup() -> InlineKeyboardMarkup:
    channel_link = f"https://t.me/{FSUB_CHANNEL}"
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("📢 Join Update Channel", url=channel_link)],
        [InlineKeyboardButton("🔄 Joined / Try Again", callback_data="check_fsub")]
    ])

def get_start_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("📢 Update Channel", url=f"https://t.me/{FSUB_CHANNEL}"),
            InlineKeyboardButton("🤖 Support", url=f"https://t.me/{FSUB_CHANNEL}")
        ]
    ])

async def send_clean_pm_notice(chat_id: int, text: str, reply_markup=None):
    if chat_id in LAST_PM_NOTICES:
        try:
            await bot.delete_messages(chat_id, LAST_PM_NOTICES[chat_id])
        except Exception:
            pass
    try:
        msg = await bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup,
            parse_mode=enums.ParseMode.HTML
        )
        LAST_PM_NOTICES[chat_id] = msg.id
        return msg
    except Exception as e:
        logger.error(f"Failed sending clean PM notice to {chat_id}: {e}")
        return None

