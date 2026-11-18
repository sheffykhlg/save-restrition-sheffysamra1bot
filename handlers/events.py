import time
from pyrogram import Client, enums
from pyrogram.types import ChatMemberUpdated, Message
from core.config import logger
from database.mongo import user_chats_col

async def on_bot_chat_member_updated(client: Client, chat_member_updated: ChatMemberUpdated):
    try:
        new_member = chat_member_updated.new_chat_member
        old_member = chat_member_updated.old_chat_member
        bot_id = client.me.id if getattr(client, "me", None) else 0
        if not new_member or not new_member.user or new_member.user.id != bot_id:
            return

        was_in = old_member and old_member.status in [
            enums.ChatMemberStatus.MEMBER,
            enums.ChatMemberStatus.ADMINISTRATOR,
            enums.ChatMemberStatus.OWNER
        ]
        is_in = new_member.status in [
            enums.ChatMemberStatus.MEMBER,
            enums.ChatMemberStatus.ADMINISTRATOR
        ]

        if is_in:
            chat = chat_member_updated.chat
            chat_title = chat.title or "this chat"
            chat_type = "Channel" if chat.type == enums.ChatType.CHANNEL else "Group"
            added_by = chat_member_updated.from_user.id if chat_member_updated.from_user else None
            chat_link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
            if not chat_link:
                try:
                    chat_link = await client.export_chat_invite_link(chat.id)
                except Exception:
                    pass

            if added_by:
                user_chats_col.update_one(
                    {"user_id": added_by, "chat_id": chat.id},
                    {
                        "$set": {
                            "chat_id": chat.id,
                            "title": chat_title,
                            "type": chat_type,
                            "link": chat_link,
                            "updated_at": time.time()
                        }
                    },
                    upsert=True
                )

            if not was_in:
                notification_text = (
                    f"🎉 <b>Bot Successfully Added to {chat_title}!</b>\n\n"
                    f"⚡ <b>High-Speed Content Downloader is now ACTIVE in this {chat_type}!</b>\n\n"
                    f"📌 <b>Available Commands:</b>\n"
                    f"• Send any public or private Telegram post link directly here\n"
                    f"• <code>/batch &lt;link&gt; &lt;count&gt;</code> - Download multiple posts\n"
                    f"• <code>/replace &lt;old&gt; &lt;new&gt;</code> - Word replacement rule\n"
                    f"• <code>/cancel</code> - Cancel ongoing task\n"
                    f"• <code>/stats</code> - Database & storage stats\n\n"
                    f"<i>Make sure your session is connected via /addsession!</i>"
                )
                await client.send_message(chat.id, notification_text)
    except Exception as e:
        logger.warning(f"Error in on_bot_chat_member_updated: {e}")

async def on_new_chat_members(client: Client, message: Message):
    try:
        bot_id = client.me.id if getattr(client, "me", None) else 0
        for member in message.new_chat_members:
            if member.id == bot_id:
                chat = message.chat
                chat_title = chat.title or "this chat"
                added_by = message.from_user.id if message.from_user else None
                chat_link = f"https://t.me/{chat.username}" if getattr(chat, "username", None) else None
                if not chat_link:
                    try:
                        chat_link = await client.export_chat_invite_link(chat.id)
                    except Exception:
                        pass
                if added_by:
                    user_chats_col.update_one(
                        {"user_id": added_by, "chat_id": chat.id},
                        {
                            "$set": {
                                "chat_id": chat.id,
                                "title": chat_title,
                                "type": "Group",
                                "link": chat_link,
                                "updated_at": time.time()
                            }
                        },
                        upsert=True
                    )
                notification_text = (
                    f"🎉 <b>Bot Successfully Added to {chat_title}!</b>\n\n"
                    f"⚡ <b>High-Speed Content Downloader is now ACTIVE in this group!</b>\n\n"
                    f"📌 <b>Available Commands:</b>\n"
                    f"• Send any public or private Telegram post link directly here\n"
                    f"• <code>/batch &lt;link&gt; &lt;count&gt;</code> - Download multiple posts\n"
                    f"• <code>/replace &lt;old&gt; &lt;new&gt;</code> - Word replacement rule\n"
                    f"• <code>/cancel</code> - Cancel ongoing task\n"
                    f"• <code>/stats</code> - Database & storage stats\n\n"
                    f"<i>Make sure your session is connected via /addsession!</i>"
                )
                await message.reply_text(notification_text)
                break
    except Exception as e:
        logger.warning(f"Error in on_new_chat_members: {e}")

