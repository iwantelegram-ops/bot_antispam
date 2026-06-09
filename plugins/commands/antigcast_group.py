"""
plugins/commands/antigcast_group.py
─────────────────────────────────────
Handler /antigcast yang dikirim di dalam GRUP.
Mengirim panel kontrol ke DM user, dengan cooldown per grup.
"""

import asyncio
import time
from pyrogram import Client, filters
from pyrogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from pyrogram.enums import ParseMode
from pyrogram.errors import UserIsBlocked, PeerIdInvalid, InputUserDeactivated

_antigcast_cooldown: dict[int, float] = {}
COOLDOWN_SECONDS = 15


async def _auto_delete(*messages: Message, delay: int = 15):
    await asyncio.sleep(delay)
    for msg in messages:
        try:
            await msg.delete()
        except Exception:
            pass


@Client.on_message(filters.command("antigcast") & filters.group)
async def antigcast_group_handler(client: Client, message: Message):
    chat_id = message.chat.id
    user    = message.from_user
    if not user:
        return

    now            = time.monotonic()
    cooldown_until = _antigcast_cooldown.get(chat_id, 0)
    if now < cooldown_until:
        try:
            await message.delete()
        except Exception:
            pass
        return

    try:
        # Gunakan page_start() yang sama dengan /start & /antigcast di DM
        # agar konten seragam dan nama owner + channel selalu tampil.
        from plugins.ui.pages import page_start
        text, keyboard = await page_start(client)

        await client.send_message(
            chat_id=user.id,
            text=text,
            reply_markup=keyboard,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
        notif = await message.reply(
            "📬 <b>Control Panel dikirim ke DM kamu!</b>\n"
            "<i>Cek pesan pribadi dari bot untuk membuka pengaturan grup.</i>",
            parse_mode=ParseMode.HTML,
        )
        asyncio.create_task(_auto_delete(notif, message, delay=10))

    except (UserIsBlocked, PeerIdInvalid, InputUserDeactivated):
        _antigcast_cooldown[chat_id] = time.monotonic() + COOLDOWN_SECONDS

        me        = await client.get_me()
        start_url = f"https://t.me/{me.username}?start=true"

        fallback = await message.reply(
            "🤖 <b>AntiGcast — Anti-Spam Bot</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━\n\n"
            "Untuk membuka <b>Control Panel</b>, kamu perlu memulai\n"
            "percakapan dengan bot ini di chat pribadi terlebih dahulu.\n\n"
            "Klik tombol di bawah → tekan <b>START</b> → ketik /antigcast lagi.\n\n"
            "<i>⏳ Pesan ini terhapus otomatis dalam 15 detik.</i>",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("🚀  Buka & Start Bot", url=start_url)],
            ]),
            parse_mode=ParseMode.HTML,
        )
        asyncio.create_task(_auto_delete(fallback, message, delay=COOLDOWN_SECONDS))

        async def _reset_cooldown():
            await asyncio.sleep(COOLDOWN_SECONDS)
            _antigcast_cooldown.pop(chat_id, None)

        asyncio.create_task(_reset_cooldown())

    except Exception as e:
        print(f"[antigcast_group] Error: {e}")
        try:
            await message.delete()
        except Exception:
            pass
