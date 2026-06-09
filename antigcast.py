"""
antigcast.py — Entry Point Bot Antispam + Nexus AI
Jalankan: python antigcast.py

Sistem yang berjalan:
  [REFACTOR] plugins/filters/    → antispam, bio, cas  (group filter)
  [REFACTOR] plugins/commands/   → settings, regex, free, log, antigcast_group
  [REFACTOR] plugins/ui/         → DM panel interaktif (pages, handlers_dm, handlers_fsm)
  [NEXUS]    plugins/nexus/      → nexus_group.py, nexus_handlers.py
             core/               → engine.py (komputasi AI)

Database (otomatis dipilih saat startup):
  1. MongoDB  — jika MONGO_URL ada di .env dan bisa tersambung
  2. SQLite   — fallback ke penyimpanan internal HP (Termux)
"""

import os
import asyncio
import threading
import dns.resolver
from pyrogram import Client, idle
from pyrogram.types import BotCommand, BotCommandScopeAllPrivateChats, BotCommandScopeAllGroupChats
from http.server import BaseHTTPRequestHandler, HTTPServer
from database import setup_db, delete_worker, close_db

# ── Termux: ambil OWNER_ID ────────────────────────────────────────────────────
OWNER_ID = int(os.environ.get("OWNER_ID", 0))

# ── Fix DNS Termux ────────────────────────────────────────────────────────────
dns.resolver.default_resolver = dns.resolver.Resolver(configure=False)
dns.resolver.default_resolver.nameservers = ['223.5.5.5', '223.6.6.6']

# ── Env ───────────────────────────────────────────────────────────────────────
API_ID    = int(os.environ.get("API_ID", 0))
API_HASH  = os.environ.get("API_HASH", "")
BOT_TOKEN = os.environ.get("BOT_TOKEN", "")
CODE_BOT  = os.environ.get("CODE_BOT", "").strip()


def _print_startup_banner():
    """Tampilkan banner info bot saat startup di Termux."""
    sep = "═" * 40
    print(f"\n")
    print(f"{'  BOT ANTISPAM + NEXUS AI  ':^52}")
  
   # Sensor token: tampilkan hanya 8 karakter pertama
    token_display = (BOT_TOKEN[:8] + "…" + BOT_TOKEN[-4:]) if len(BOT_TOKEN) > 12 else "(tidak diset)"
    print(f"  API_ID    : {str(API_ID) if API_ID else '(tidak diset)':<39}")
    print(f"  BOT_TOKEN : {token_display:<39}")
    print(f"  OWNER_ID  : {str(OWNER_ID) if OWNER_ID else '(tidak diset)':<39}")
    if CODE_BOT:
        print(f"  CODE_BOT  : [{CODE_BOT}]{'':>{39 - len(CODE_BOT) - 2}}")
        print(f"  Namespace : aktif — data dipisah per CODE_BOT  ")
    else:
        print(f"  CODE_BOT  : (kosong — tidak ada isolasi)        ")
        print(f"  ⚠️  Set CODE_BOT di .env agar data tidak campur ")

    print(f"  Info backend database menyusul di bawah...      ")
    print(f"\n")

# ── Client ────────────────────────────────────────────────────────────────────
app = Client(
    "antispam_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    plugins=dict(root="plugins"),
)


# ── Health Check ──────────────────────────────────────────────────────────────
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"Bot Antispam + Nexus AI Online 2026")

    def log_message(self, *args):
        pass


def run_health_check():
    try:
        port = int(os.environ.get("PORT", 8000))
        server = HTTPServer(('0.0.0.0', port), HealthCheckHandler)
        server.serve_forever()
    except Exception as e:
        print(f"[HealthCheck] Error: {e}")


# ── Set Bot Commands ──────────────────────────────────────────────────────────
async def _setup_commands():
    try:
        await app.set_bot_commands(
            commands=[
                BotCommand("spam",      "balas pesan n masukin ke database AI"),
                BotCommand("antigcast", "anti spam cerdas"),
            ],
            scope=BotCommandScopeAllGroupChats(),
        )
        await app.set_bot_commands(
            commands=[
                BotCommand("antigcast", "anti spam cerdas"),
            ],
            scope=BotCommandScopeAllPrivateChats(),
        )
        print("✅ Bot commands berhasil diset (grup & DM).")
    except Exception as e:
        print(f"⚠️  Gagal set bot commands: {e}")


# ── Graceful Shutdown ─────────────────────────────────────────────────────────
async def _notify_owner():
    """Kirim notif ke owner lalu return. Dibatasi timeout 8 detik."""
    if not OWNER_ID:
        return
    try:
        await asyncio.wait_for(
            app.send_message(OWNER_ID, "⚠️ Bot offline — shutdown/maintenance."),
            timeout=8.0,
        )
        print("📢 Notifikasi shutdown terkirim ke owner.")
    except Exception as e:
        print(f"[Shutdown] Gagal kirim notif owner: {e}")


async def graceful_shutdown():
    """
    Tutup bot dengan bersih. Urutan:
      1. Kirim notif ke owner (timeout 8 detik)
      2. Cancel semua background task
      3. Tutup koneksi database
      4. Stop Pyrogram (timeout 5 detik)
    """
    print("\n🛑 Memulai prosedur shutdown...")

    await _notify_owner()

    current = asyncio.current_task()
    tasks   = [t for t in asyncio.all_tasks() if t is not current]
    if tasks:
        print(f"🔄 Membatalkan {len(tasks)} background task...")
        for t in tasks:
            t.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        print("✅ Semua task dibatalkan.")

    await close_db()

    try:
        if app.is_connected:
            await asyncio.wait_for(app.stop(), timeout=5.0)
            print("✅ Koneksi Telegram berhasil diputus.")
    except asyncio.TimeoutError:
        print("⚠️  app.stop() timeout — paksa keluar.")
    except Exception as e:
        print(f"[Shutdown] app.stop error (diabaikan): {e}")

    print("🛑 Bot berhasil dimatikan dengan bersih.")


# ── Main ──────────────────────────────────────────────────────────────────────
async def main():
    # Banner startup — tampil sebelum apapun
    _print_startup_banner()

    # Health check thread (daemon)
    threading.Thread(target=run_health_check, daemon=True).start()

    # Setup database (auto-pilih MongoDB atau SQLite)
    await setup_db()

    # Background tasks
    asyncio.create_task(delete_worker(app))

    # Nexus midnight scheduler
    from plugins.nexus.engine import cron_midnight_scheduler
    asyncio.create_task(cron_midnight_scheduler())

    # Jalankan bot
    try:
        await app.start()
        await _setup_commands()
        print("🚀 Bot Antispam + Nexus AI aktif! Tekan Ctrl+C untuk berhenti.")
        await idle()
    except (KeyboardInterrupt, asyncio.CancelledError):
        await graceful_shutdown()
    finally:
        try:
            if app.is_connected:
                await app.stop()
        except Exception:
            pass

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        # 1. Ambil semua task yang masih menggantung/pending
        pending_tasks = asyncio.all_tasks(loop)
        
        # 2. Batalkan semua task tersebut
        for task in pending_tasks:
            task.cancel()
            
        # 3. Berikan waktu sejenak agar sistem memproses pembatalan task
        if pending_tasks:
            try:
                loop.run_until_complete(asyncio.gather(*pending_tasks, return_exceptions=True))
            except Exception:
                pass
                
        # 4. Baru setelah itu tutup loop dengan aman
        try:
            loop.close()
        except Exception:
            pass
            
        print("🛑 Bot berhasil dimatikan dengan bersih.")

