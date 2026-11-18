from pyrogram import Client, enums
from pyrogram.types import CallbackQuery
from core.config import FSUB_CHANNEL
from ui.keyboards import get_add_buttons, send_clean_pm_notice
from handlers.fsub import is_user_fsub_member

async def fsub_callback(client: Client, callback_query: CallbackQuery):
    user_id = callback_query.from_user.id
    if await is_user_fsub_member(client, user_id):
        await callback_query.answer("✅ Verified! You have joined the channel. You can now use the bot.", show_alert=True)
        try:
            await callback_query.message.delete()
        except Exception:
            pass
        if callback_query.message.chat.type == enums.ChatType.PRIVATE:
            notice_text = (
                "🎉 <b>Membership Verified Successfully!</b>\n\n"
                "⚠️ <b>Note: This bot does not download inside PM.</b>\n\n"
                "Please add me to your <b>Group</b> or <b>Channel</b> as Admin using the buttons below to start high-speed downloading!"
            )
            buttons = await get_add_buttons(user_id)
            await send_clean_pm_notice(callback_query.message.chat.id, notice_text, reply_markup=buttons)
        else:
            await callback_query.message.reply_text(
                f"✅ <b>Verified for {callback_query.from_user.mention}!</b> You can now use the bot here."
            )
    else:
        await callback_query.answer(f"❌ You have not joined @{FSUB_CHANNEL} yet! Please join first.", show_alert=True)

