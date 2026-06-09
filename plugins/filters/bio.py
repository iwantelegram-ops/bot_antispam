"""
plugins/filters/bio.py
──────────────────────
Filter deteksi link di bio Telegram user.
Berjalan di group=1 (sebelum antispam.py di group=2).

PINTU BERURUTAN:
  Jika bio mengandung link → mark_message_handled(cid, mid) sebelum
  memasukkan ke delete_queue, sehingga antispam & nexus tidak memproses ulang.

VIP:
  User yang terdaftar di free_per_group sepenuhnya dilewati.

HUKUMAN:
  Setiap penghapusan bio dihitung sebagai 1 pelanggaran spam.
  Sistem mute eskalasi (core/punishment.py) berlaku.
"""

import os
import re
import time
from datetime import datetime
from pyrogram import Client, filters
from pyrogram.types import Message
from pyrogram.raw import functions
from pyrogram.enums import ParseMode

from database import (
    auto_delete_reply, is_admin, delete_queue, get_config,
    update_config, db, TZ_WIB,
    mark_message_handled, is_message_handled, insert_group_action_log,
)
from core.punishment import check_and_punish

free_col    = db["free_per_group"]
LOG_CHANNEL = int(os.environ.get("LOG_CHANNEL", 0))

LINK_PATTERN = re.compile(
    r"(@\S+|https?://\S+|t\.me/\S+|bit\.ly/\S+|linktr\.ee/\S+)",
    re.IGNORECASE,
)

_bio_cache: dict[int, tuple[bool, float]] = {}
BIO_TTL = 3600  # 1 jam


@Client.on_message(filters.group & ~filters.service, group=1)
async def bio_filter(client: Client, message: Message):
    if not message.from_user or message.from_user.is_bot:
        return

    cid = message.chat.id
    uid = message.from_user.id
    mid = message.id

    if is_message_handled(cid, mid):
        return

    cfg = await get_config(cid)
    if cfg["bio_check"] is not True:
        return

    if await is_admin(client, cid, uid):
        return

    if await free_col.find_one({"user_id": uid, "chat_id": cid}):
        return

    now = time.monotonic()
    hit = _bio_cache.get(uid)

    if hit and (now - hit[1]) < BIO_TTL:
        if hit[0]:
            mark_message_handled(cid, mid)
            await delete_queue.put((cid, [mid]))
            # Hitung pelanggaran bio link sebagai spam
            import asyncio
            asyncio.create_task(check_and_punish(client, message, "link di bio profil", ""))
        return

    try:
        full_user = await client.invoke(
            functions.users.GetFullUser(id=await client.resolve_peer(uid))
        )
        bio      = full_user.full_user.about or ""
        has_link = bool(LINK_PATTERN.search(bio))
        _bio_cache[uid] = (has_link, now)

        if has_link:
            mark_message_handled(cid, mid)
            await delete_queue.put((cid, [mid]))
            await _log_bio_deletion(client, message, bio)
            try:
                await insert_group_action_log(
                    cid, "HAPUS",
                    "Link ditemukan di profil bio",
                    uid,
                    message.from_user.first_name or str(uid),
                    (message.text or message.caption or "")[:100],
                )
            except Exception:
                pass
            # Hitung pelanggaran bio link sebagai spam (sistem hukuman terpusat)
            import asyncio
            asyncio.create_task(check_and_punish(client, message, "link di bio profil", bio[:100]))

    except Exception as e:
        print(f"⚠️  Bio-Error [chat={cid}]: {e}")


async def _log_bio_deletion(client: Client, message: Message, bio: str):
    if not LOG_CHANNEL:
        return

    uid          = message.from_user.id
    cid          = message.chat.id
    user_mention = f"<a href='tg://user?id={uid}'>{message.from_user.first_name}</a>"
    waktu        = datetime.now(TZ_WIB).strftime("%d/%m/%Y %H:%M:%S WIB")
    content      = (message.text or message.caption or "").strip()

    log_text = (
        "<b>❖ BIO LINK DETECTOR ❖</b>\n"
        "🔍 <b>Pesan Dihapus — Tautan di Bio</b>\n"
        "<blockquote>"
        f"◈ <b>User:</b> {user_mention} (<code>{uid}</code>)\n"
        f"◈ <b>Grup:</b> {message.chat.title} (<code>{cid}</code>)\n"
        f"◈ <b>Waktu:</b> {waktu}\n"
        f"◈ <b>Link di Bio:</b> <code>{bio[:200]}</code>\n\n"
        f"<b>Konten:</b> <code>{content[:500]}</code>"
        "</blockquote>"
    )
    try:
        await client.send_message(
            LOG_CHANNEL, log_text,
            parse_mode=ParseMode.HTML,
            disable_web_page_preview=True,
        )
    except Exception as e:
        print(f"[BIO LOG ERROR] {e}")
