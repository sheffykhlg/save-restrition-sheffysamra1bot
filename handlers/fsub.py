from pyrogram import Client, enums
from pyrogram.errors import UserNotParticipant
from core.config import FSUB_CHANNEL, ADMIN_ID, logger
from core.states import VERIFIED_FSUB_USERS

async def is_user_fsub_member(client: Client, user_id: int) -> bool:
    if not FSUB_CHANNEL:
        return True
    if not user_id or user_id <= 0:
        return True
    if ADMIN_ID and user_id == ADMIN_ID:
        return True
    if user_id in VERIFIED_FSUB_USERS:
        return True
    try:
        member = await client.get_chat_member(FSUB_CHANNEL, user_id)
        if member.status not in [enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED]:
            VERIFIED_FSUB_USERS.add(user_id)
            return True
        return False
    except UserNotParticipant:
        return False
    except Exception as e:
        logger.warning(f"FSUB check warning for user {user_id}: {e}")
        return True

